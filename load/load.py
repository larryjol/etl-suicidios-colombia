"""
LOAD
Carga la tabla integrada en un data warehouse SQLite con esquema estrella
(1 tabla de hechos + 3 dimensiones), más dos tablas de apoyo, y valida la carga con SQL.
Modo de carga: reemplazo completo (cada ejecución reconstruye el DW).

Entrada: data/processed/*.csv
Salida:  data/warehouse/dw_suicidios.db
         data/processed/validaciones_carga.json

Uso:  python load/load.py
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

REGION = {**dict.fromkeys(["08", "13", "20", "23", "44", "47", "70"], "Caribe"),
          **dict.fromkeys(["19", "27", "52", "76"], "Pacífica"),
          **dict.fromkeys(["05", "11", "15", "17", "25", "41", "54", "63", "66", "68", "73"], "Andina"),
          **dict.fromkeys(["50", "81", "85", "99"], "Orinoquía"),
          **dict.fromkeys(["18", "86", "91", "94", "95", "97"], "Amazonía"),
          "88": "Insular"}

DDL = """
DROP TABLE IF EXISTS hechos_suicidio;
DROP TABLE IF EXISTS dim_departamento;
DROP TABLE IF EXISTS dim_tiempo;
DROP TABLE IF EXISTS dim_demografia;
DROP TABLE IF EXISTS casos_inmlcf;
DROP TABLE IF EXISTS tasas_departamento;

CREATE TABLE dim_departamento (
  cod_dpto  TEXT PRIMARY KEY,
  nombre    TEXT NOT NULL,
  region    TEXT NOT NULL
);

CREATE TABLE dim_tiempo (
  anio              INTEGER PRIMARY KEY,
  serie_poblacion   TEXT NOT NULL,
  anio_provisional  INTEGER NOT NULL,
  anio_pandemia     INTEGER NOT NULL
);

CREATE TABLE dim_demografia (
  id_demografia  INTEGER PRIMARY KEY,
  sexo           TEXT NOT NULL,
  grupo_edad     TEXT NOT NULL,
  ciclo_vida     TEXT NOT NULL,
  mayor_de_edad  INTEGER NOT NULL
);

CREATE TABLE hechos_suicidio (
  cod_dpto            TEXT    NOT NULL,
  anio                INTEGER NOT NULL,
  id_demografia       INTEGER NOT NULL,
  casos               INTEGER NOT NULL,
  poblacion           INTEGER NOT NULL,
  tasa_100k           REAL    NOT NULL,
  baja_confiabilidad  INTEGER NOT NULL,
  PRIMARY KEY (cod_dpto, anio, id_demografia),
  FOREIGN KEY (cod_dpto)      REFERENCES dim_departamento(cod_dpto),
  FOREIGN KEY (anio)          REFERENCES dim_tiempo(anio),
  FOREIGN KEY (id_demografia) REFERENCES dim_demografia(id_demografia)
);
"""

VALIDACIONES = {
    "filas_hechos": "SELECT COUNT(*) FROM hechos_suicidio",
    "casos_en_dw": "SELECT SUM(casos) FROM hechos_suicidio",
    "duplicados_llave": """SELECT COUNT(*) FROM (SELECT cod_dpto, anio, id_demografia FROM hechos_suicidio
                           GROUP BY cod_dpto, anio, id_demografia HAVING COUNT(*) > 1)""",
    "huerfanos_departamento": """SELECT COUNT(*) FROM hechos_suicidio h
                                 LEFT JOIN dim_departamento d ON h.cod_dpto = d.cod_dpto WHERE d.cod_dpto IS NULL""",
    "huerfanos_tiempo": """SELECT COUNT(*) FROM hechos_suicidio h
                           LEFT JOIN dim_tiempo t ON h.anio = t.anio WHERE t.anio IS NULL""",
    "huerfanos_demografia": """SELECT COUNT(*) FROM hechos_suicidio h
                               LEFT JOIN dim_demografia m ON h.id_demografia = m.id_demografia WHERE m.id_demografia IS NULL""",
    "poblacion_no_positiva": "SELECT COUNT(*) FROM hechos_suicidio WHERE poblacion <= 0",
    "casos_negativos": "SELECT COUNT(*) FROM hechos_suicidio WHERE casos < 0",
    "registros_casos_inmlcf": "SELECT COUNT(*) FROM casos_inmlcf",
}


def ciclo_vida(grupo):
    ini = 80 if grupo == "80+" else int(grupo[:2])
    if ini < 10:
        return "Infancia"
    if ini < 18:
        return "Adolescencia"
    if ini < 29:
        return "Juventud"
    if ini < 60:
        return "Adultez"
    return "Adulto mayor"


def construir_dimensiones(tabla, departamentos):
    dim_departamento = departamentos.rename(columns={"departamento": "nombre"})
    dim_departamento["region"] = dim_departamento["cod_dpto"].map(REGION)

    dim_tiempo = tabla[["anio", "serie"]].drop_duplicates().sort_values("anio").rename(columns={"serie": "serie_poblacion"})
    dim_tiempo["anio_provisional"] = (dim_tiempo["anio"] == config.ANIO_PROVISIONAL).astype(int)
    dim_tiempo["anio_pandemia"] = (dim_tiempo["anio"] == 2020).astype(int)

    dim_demografia = pd.DataFrame([(s, g) for s in ["Hombre", "Mujer"] for g in config.GRUPOS_EDAD],
                                  columns=["sexo", "grupo_edad"])
    dim_demografia.insert(0, "id_demografia", range(1, len(dim_demografia) + 1))
    dim_demografia["ciclo_vida"] = dim_demografia["grupo_edad"].map(ciclo_vida)
    dim_demografia["mayor_de_edad"] = (~dim_demografia["grupo_edad"].isin(["05-09", "10-14", "15-17"])).astype(int)
    return dim_departamento, dim_tiempo, dim_demografia


def run():
    tabla = pd.read_csv(config.PROCESSED_DIR / "tabla_integrada.csv", dtype={"cod_dpto": str})
    casos = pd.read_csv(config.PROCESSED_DIR / "casos_limpios.csv", dtype={"cod_dpto": str}, low_memory=False)
    tasas = pd.read_csv(config.PROCESSED_DIR / "tasas_departamento.csv", dtype={"cod_dpto": str})
    departamentos = pd.read_csv(config.PROCESSED_DIR / "departamentos.csv", dtype={"cod_dpto": str})

    dim_departamento, dim_tiempo, dim_demografia = construir_dimensiones(tabla, departamentos)
    hechos = tabla.merge(dim_demografia[["id_demografia", "sexo", "grupo_edad"]], on=["sexo", "grupo_edad"])
    hechos = hechos[["cod_dpto", "anio", "id_demografia", "casos", "poblacion", "tasa_100k", "baja_confiabilidad"]]

    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(DDL)
    conn.execute("PRAGMA foreign_keys = ON;")
    dim_departamento.to_sql("dim_departamento", conn, if_exists="append", index=False)
    dim_tiempo.to_sql("dim_tiempo", conn, if_exists="append", index=False)
    dim_demografia.to_sql("dim_demografia", conn, if_exists="append", index=False)
    hechos.to_sql("hechos_suicidio", conn, if_exists="append", index=False)
    casos.to_sql("casos_inmlcf", conn, if_exists="replace", index=False)          # tabla de detalle
    tasas.to_sql("tasas_departamento", conn, if_exists="replace", index=False)    # tabla agregada
    conn.commit()

    resultados = {k: conn.execute(q).fetchone()[0] for k, q in VALIDACIONES.items()}
    resultados["casos_esperados"] = int(tabla["casos"].sum())
    resultados["cuadre_casos"] = "OK" if resultados["casos_en_dw"] == resultados["casos_esperados"] else "ERROR"
    conn.close()

    with open(config.PROCESSED_DIR / "validaciones_carga.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    print("[LOAD]")
    print(f"  destino              {config.DB_PATH.relative_to(config.RAIZ) if config.DB_PATH.is_relative_to(config.RAIZ) else config.DB_PATH}")
    for k, v in resultados.items():
        print(f"  {k:24s} {v}")

    fallas = [k for k in ["duplicados_llave", "huerfanos_departamento", "huerfanos_tiempo",
                          "huerfanos_demografia", "poblacion_no_positiva", "casos_negativos"] if resultados[k] != 0]
    if fallas or resultados["cuadre_casos"] != "OK":
        raise ValueError(f"La carga no pasó las validaciones: {fallas or 'cuadre de casos'}")
    return resultados


if __name__ == "__main__":
    run()
