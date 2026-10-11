"""
EXTRACT
Lee las tres fuentes desde data/raw sin modificar su contenido y deja una copia
tabular uniforme (CSV UTF-8) en data/interim para la etapa de transformación.

Uso:  python extract/extract.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402


def extraer_casos():
    """Casos de presuntos suicidios del INMLCF (un registro por caso).
    Usa el CSV de datos.gov.co si existe; si no, el XLSX."""
    csv = sorted(config.RAW_DIR.glob(config.PATRON_CASOS_CSV))
    if csv:
        df = pd.read_csv(csv[0], low_memory=False)
        origen = csv[0].name
    elif config.ARCHIVO_CASOS_XLSX.exists():
        df = pd.read_excel(config.ARCHIVO_CASOS_XLSX)
        origen = config.ARCHIVO_CASOS_XLSX.name
    else:
        raise FileNotFoundError("No se encontró el archivo de casos del INMLCF en data/raw (CSV o XLSX).")
    return df, origen


def extraer_poblacion_2005():
    """Proyecciones DANE 2005-2017. El encabezado real está en la fila 12."""
    if not config.ARCHIVO_POB_2005.exists():
        raise FileNotFoundError(f"No existe {config.ARCHIVO_POB_2005}")
    return pd.read_excel(config.ARCHIVO_POB_2005, header=11, dtype={"DP": str})


def extraer_poblacion_2018():
    """Proyecciones DANE 2018-2050. Encabezado en dos filas: las 4 primeras columnas
    quedan sin nombre y se renombran igual que en el archivo 2005-2017."""
    if not config.ARCHIVO_POB_2018.exists():
        raise FileNotFoundError(f"No existe {config.ARCHIVO_POB_2018}")
    df = pd.read_excel(config.ARCHIVO_POB_2018, sheet_name="PobDepartamentalxÁreaSexoEdad",
                       header=8, dtype={"Unnamed: 0": str})
    return df.rename(columns={"Unnamed: 0": "DP", "Unnamed: 1": "DPNOM",
                              "Unnamed: 2": "AÑO", "Unnamed: 3": "ÁREA GEOGRÁFICA"})


def run():
    casos, origen = extraer_casos()
    pob_2005 = extraer_poblacion_2005()
    pob_2018 = extraer_poblacion_2018()

    casos.to_csv(config.INTERIM_DIR / "casos_raw.csv", index=False, encoding="utf-8")
    pob_2005.to_csv(config.INTERIM_DIR / "poblacion_2005_2017_raw.csv", index=False, encoding="utf-8")
    pob_2018.to_csv(config.INTERIM_DIR / "poblacion_2018_2050_raw.csv", index=False, encoding="utf-8")

    resumen = {
        "casos": {"origen": origen, "filas": len(casos), "columnas": casos.shape[1]},
        "poblacion_2005_2017": {"filas": len(pob_2005), "columnas": pob_2005.shape[1]},
        "poblacion_2018_2050": {"filas": len(pob_2018), "columnas": pob_2018.shape[1]},
    }
    print("[EXTRACT]")
    for nombre, r in resumen.items():
        print(f"  {nombre:22s} {r['filas']:>7,} filas x {r['columnas']} columnas")
    return resumen


if __name__ == "__main__":
    run()
