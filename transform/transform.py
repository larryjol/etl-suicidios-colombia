"""
TRANSFORM
Aplica el plan de transformaciones de la Entrega 2, organizado por etapas:
limpieza -> normalización -> reducción -> integración -> enriquecimiento.

Entrada: data/interim/*.csv (salida de extract)
Salida:  data/processed/
    casos_limpios.csv          un registro por caso, limpio y homologado
    tabla_integrada.csv        departamento x año x sexo x grupo de edad: casos, población, tasa
    tasas_departamento.csv     tasa cruda, tasa ajustada (método directo) y SMR por departamento
    reporte_calidad.json       conteos antes / después de cada etapa

Uso:  python transform/transform.py
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

ETIQUETAS_FALTANTE = {"sin informacion", "no habia sido implementada", "no sabe / no informa", "por determinar"}

# Variables excluidas del análisis principal (Entrega 2, Tabla 6 - Reducción de dimensiones)
VARIABLES_EXCLUIDAS = ["Razón del Suicidio", "Rango de Hora del Hecho X 3 Horas", "Localidad del Hecho",
                       "Orientación Sexual", "Identidad de Género", "Transgénero", "Pertenencia Étnica"]

# Equivalencias semánticas que no se resuelven solo con mayúsculas o espacios
HOMOLOGACION = {
    "Grupo Mayor Menor de Edad": {
        "a) menor de edad(<18 anos)": "Menor de edad", "a) menores de edad(<18 anos)": "Menor de edad",
        "b) mayor de edad(>18 anos)": "Mayor de edad", "b) mayores de edad(>18 anos)": "Mayor de edad"},
    "Escolaridad": {
        "ninguna": "Sin escolaridad", "sin escolaridad": "Sin escolaridad",
        "preescolar": "Preescolar", "educacion inicial y educacion preescolar": "Preescolar",
        "basica primaria": "Primaria", "educacion basica primaria": "Primaria",
        "basica secundaria": "Secundaria", "educacion basica secundaria o secundaria baja": "Secundaria",
        "educacion media o secundaria alta": "Media",
        "tecnologica": "Técnica o tecnológica", "educacion tecnica profesional y tecnologica": "Técnica o tecnológica",
        "profesional": "Universitaria", "universitario": "Universitaria",
        "especializacion, maestria o equivalente": "Posgrado", "maestria": "Posgrado",
        "doctorado o equivalente": "Posgrado"},
    "Mecanismo Causal de la Lesión Fatal": {
        "corto contundente": "Cortocontundente", "corto punzante": "Cortopunzante",
        "agente o mecanismo explosivo": "Explosivo", "agentes y mecanismo explosivo": "Explosivo",
        "mecanismo o agente explosivo": "Explosivo"},
}


# ----------------------------------------------------------------------------- utilidades
def corregir_codificacion(x):
    """Repara texto UTF-8 leído como Latin-1 ('BogotÃ¡' -> 'Bogotá') y los códigos
    _x00HH_ que deja Excel. Si el texto ya está bien, lo devuelve igual."""
    if not isinstance(x, str):
        return x
    x = re.sub(r"_x00([0-9A-Fa-f]{2})_", lambda m: chr(int(m.group(1), 16)), x)
    try:
        return x.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return x


def normalizar(x):
    """Clave de comparación: minúsculas, sin tildes, sin espacios repetidos ni antes de '('."""
    if not isinstance(x, str):
        return x
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode()
    x = re.sub(r"\s+\(", "(", x.strip().lower())
    return re.sub(r"\s+", " ", x)


def columnas_texto(df):
    return df.select_dtypes(include=["object", "string"]).columns


def edad_a_grupo(edad):
    """Edad simple del DANE -> grupo del INMLCF. Menores de 5 años -> '00-04'."""
    if edad < 5:
        return "00-04"
    for limite, grupo in zip(config.BORDES_EDAD[1:], config.GRUPOS_EDAD):
        if edad < limite:
            return grupo


def grupo_edad_inmlcf(texto):
    """'(15 a 17)' -> '15-17', '(80 y más)' -> '80+'."""
    if pd.isna(texto):
        return np.nan
    if "80" in texto:
        return "80+"
    ini, fin = re.findall(r"\d+", texto)[:2]
    return f"{int(ini):02d}-{int(fin):02d}"


# ----------------------------------------------------------------------------- casos
def limpiar_casos(df, reporte):
    df = df.copy()
    reporte["casos_registros_entrada"] = len(df)
    reporte["casos_columnas_entrada"] = df.shape[1]

    # 1. Codificación de texto (solo actúa si el archivo viene con caracteres corruptos)
    celdas_corruptas = int(df[columnas_texto(df)].apply(lambda s: s.astype(str).str.contains("Ã")).sum().sum())
    df.columns = [corregir_codificacion(c).replace("﻿", "") for c in df.columns]
    for c in columnas_texto(df):
        df[c] = df[c].map(corregir_codificacion)
    reporte["celdas_texto_corrupto_antes"] = celdas_corruptas
    reporte["celdas_texto_corrupto_despues"] = int(
        df[columnas_texto(df)].apply(lambda s: s.astype(str).str.contains("Ã")).sum().sum())

    # 2. Espacios en nombres de columna (p. ej. 'Grupo de Edad Quinquenal ')
    reporte["columnas_con_espacios"] = sum(c != c.strip() for c in df.columns)
    df.columns = [c.strip() for c in df.columns]

    # 3. Etiquetas de faltante -> nulo
    antes = int(df.isna().sum().sum())
    for c in columnas_texto(df):
        df[c] = df[c].where(~df[c].map(normalizar).isin(ETIQUETAS_FALTANTE), np.nan)
    reporte["etiquetas_faltante_convertidas_a_nulo"] = int(df.isna().sum().sum()) - antes

    # 4. Casos sin departamento (código 999)
    sin_dpto = df["Código Dane Departamento"] == 999
    reporte["casos_sin_departamento_excluidos"] = int(sin_dpto.sum())
    df = df[~sin_dpto].copy()

    # 5. Columnas constantes
    constantes = [c for c in df.columns if df[c].nunique(dropna=False) <= 1]
    reporte["columnas_constantes_eliminadas"] = constantes
    df = df.drop(columns=constantes)

    # Control: duplicados exactos sin contar el ID (se reportan; no se eliminan porque
    # cada registro tiene ID propio y puede tratarse de víctimas distintas)
    reporte["registros_identicos_sin_id"] = int(df.drop(columns="ID").duplicated().sum())
    reporte["ids_duplicados"] = int(df["ID"].duplicated().sum())
    return df


def normalizar_casos(df, reporte):
    df = df.copy()
    categoricas = [c for c in columnas_texto(df) if c != "Municipio del hecho DANE"]
    reporte["categorias_antes"] = {c: int(df[c].nunique()) for c in categoricas}

    for c in categoricas:
        clave = df[c].map(normalizar)
        if c in HOMOLOGACION:
            # equivalencias semánticas explícitas
            df[c] = clave.map(HOMOLOGACION[c]).fillna(df[c])
            clave = df[c].map(normalizar)
        # variantes de escritura: cada clave toma su forma más frecuente
        forma = df.groupby(clave)[c].agg(lambda s: s.value_counts().index[0])
        df[c] = clave.map(forma)

    # Mes y día con mayúscula inicial para todos los años
    for c in ["Mes del hecho", "Dia del hecho"]:
        if c in df.columns:
            df[c] = df[c].str.capitalize()

    reporte["categorias_despues"] = {c: int(df[c].nunique()) for c in categoricas}
    return df


def reducir_casos(df, reporte):
    df = df.copy()
    excluidas = [c for c in VARIABLES_EXCLUIDAS if c in df.columns]
    df = df.drop(columns=excluidas)
    reporte["variables_excluidas"] = excluidas

    col = "Mecanismo Causal de la Lesión Fatal"
    conteo = df[col].value_counts()
    raros = conteo[conteo < config.UMBRAL_MECANISMO_OTROS].index.tolist()
    df[col] = df[col].where(~df[col].isin(raros), "Otros")
    reporte["mecanismos_agrupados_en_otros"] = raros
    reporte["casos_columnas_salida"] = df.shape[1]
    return df


# ----------------------------------------------------------------------------- población
def poblacion_larga(df, anios, serie):
    """Homologa columnas del archivo DANE y lo pasa de formato ancho a largo."""
    df = df[pd.to_numeric(df["AÑO"], errors="coerce").notna()].copy()       # quita notas al pie
    df["AÑO"] = df["AÑO"].astype(int)
    df["ÁREA GEOGRÁFICA"] = df["ÁREA GEOGRÁFICA"].replace({"Cabecera Municipal": "Cabecera"})
    df = df[(df["ÁREA GEOGRÁFICA"] == "Total") & df["AÑO"].between(*anios)]

    # 'Hombres_23' (2005-2017) y 'Hombres 23 años' (2018-2050) -> sexo, edad
    patron = r"^(Hombres|Mujeres)[_ ](\d+)"
    cols = [c for c in df.columns if re.match(patron, str(c))]
    largo = df.melt(id_vars=["DP", "DPNOM", "AÑO"], value_vars=cols, var_name="col", value_name="poblacion")
    partes = largo["col"].str.extract(patron)
    largo["sexo"] = partes[0].map({"Hombres": "Hombre", "Mujeres": "Mujer"})
    largo["edad"] = partes[1].astype(int)
    largo["cod_dpto"] = largo["DP"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
    largo["serie"] = serie
    return largo.rename(columns={"AÑO": "anio", "DPNOM": "dpto_nombre_dane"})


# ----------------------------------------------------------------------------- integración
def integrar(casos, pob_2005, pob_2018, reporte):
    pob = pd.concat([poblacion_larga(pob_2005, config.ANIOS_SERIE_2005, "2005-2017"),
                     poblacion_larga(pob_2018, config.ANIOS_SERIE_2018, "2018-2050")], ignore_index=True)
    reporte["poblacion_columnas_edad_por_archivo"] = int(pob.groupby("serie")["col"].nunique().iloc[0])

    # Nombre oficial: el del archivo más reciente (se cruza siempre por código)
    nombres = (pob[pob["serie"] == "2018-2050"].groupby("cod_dpto")["dpto_nombre_dane"].first()
               .replace({"Archipiélago de San Andrés, Providencia y Santa Catalina": "San Andrés y Providencia"}))

    pob["grupo_edad"] = pob["edad"].map(edad_a_grupo)
    pob = pob[pob["grupo_edad"] != "00-04"]                                  # población de 5 años o más
    pob = pob.groupby(["cod_dpto", "anio", "serie", "sexo", "grupo_edad"])["poblacion"].sum().reset_index()

    casos = casos.copy()
    casos["cod_dpto"] = casos["Código Dane Departamento"].astype(int).astype(str).str.zfill(2)
    casos["grupo_edad"] = casos["Grupo de Edad Quinquenal"].map(grupo_edad_inmlcf)
    conteo = (casos.groupby(["cod_dpto", "Año del hecho", "Sexo de la victima", "grupo_edad"]).size()
              .reset_index(name="casos")
              .rename(columns={"Año del hecho": "anio", "Sexo de la victima": "sexo"}))

    # Left join desde la rejilla poblacional: las combinaciones sin casos quedan en 0
    tabla = pob.merge(conteo, on=["cod_dpto", "anio", "sexo", "grupo_edad"], how="left")
    tabla["casos"] = tabla["casos"].fillna(0).astype(int)
    tabla.insert(1, "departamento", tabla["cod_dpto"].map(nombres))

    sin_poblacion = conteo.merge(pob, on=["cod_dpto", "anio", "sexo", "grupo_edad"], how="left")["poblacion"].isna()
    reporte["casos_sin_poblacion"] = int(conteo.loc[sin_poblacion.values, "casos"].sum())
    reporte["casos_en_tabla_integrada"] = int(tabla["casos"].sum())
    reporte["filas_tabla_integrada"] = len(tabla)

    casos["departamento"] = casos["cod_dpto"].map(nombres)
    return tabla, casos, nombres


# ----------------------------------------------------------------------------- enriquecimiento
def enriquecer(tabla, reporte):
    tabla = tabla.copy()
    tabla["poblacion"] = tabla["poblacion"].round().astype(int)
    tabla["tasa_100k"] = tabla["casos"] / tabla["poblacion"] * 1e5
    tabla["anio_provisional"] = (tabla["anio"] == config.ANIO_PROVISIONAL).astype(int)
    tabla["baja_confiabilidad"] = (tabla["casos"] < config.UMBRAL_BAJA_CONFIABILIDAD).astype(int)
    reporte["pct_celdas_cero"] = round(100 * (tabla["casos"] == 0).mean(), 1)
    reporte["pct_celdas_baja_confiabilidad"] = round(100 * tabla["baja_confiabilidad"].mean(), 1)
    return tabla


def tasas_por_departamento(tabla, reporte):
    """Tasa cruda, tasa ajustada por edad y sexo (método directo, población estándar
    Colombia 2020) y razón estandarizada de mortalidad (SMR, método indirecto)."""
    g = tabla.groupby(["cod_dpto", "departamento", "sexo", "grupo_edad"])[["casos", "poblacion"]].sum().reset_index()

    std = tabla[tabla["anio"] == config.ANIO_ESTANDAR].groupby(["sexo", "grupo_edad"])["poblacion"].sum()
    g["peso"] = g.set_index(["sexo", "grupo_edad"]).index.map(std / std.sum())
    nac = tabla.groupby(["sexo", "grupo_edad"])[["casos", "poblacion"]].sum()
    g["tasa_nacional"] = g.set_index(["sexo", "grupo_edad"]).index.map(nac["casos"] / nac["poblacion"])

    g["tasa_x_peso"] = g["casos"] / g["poblacion"] * g["peso"]
    g["esperados"] = g["poblacion"] * g["tasa_nacional"]

    dep = g.groupby(["cod_dpto", "departamento"]).agg(
        casos=("casos", "sum"), personas_anio=("poblacion", "sum"),
        tasa_ajustada=("tasa_x_peso", "sum"), esperados=("esperados", "sum")).reset_index()
    dep["tasa_cruda"] = dep["casos"] / dep["personas_anio"] * 1e5
    dep["tasa_ajustada"] = dep["tasa_ajustada"] * 1e5
    dep["smr"] = dep["casos"] / dep["esperados"]
    dep["puesto_casos"] = dep["casos"].rank(ascending=False, method="min").astype(int)
    dep["puesto_tasa_ajustada"] = dep["tasa_ajustada"].rank(ascending=False, method="min").astype(int)
    dep = dep.sort_values("tasa_ajustada", ascending=False)

    # Sobredispersión entre departamentos (índice de Pearson tras estandarizar)
    chi2 = (((dep["casos"] - dep["esperados"]) ** 2) / dep["esperados"]).sum()
    reporte["indice_dispersion_estandarizado"] = round(chi2 / (len(dep) - 1), 1)
    return dep.round({"tasa_cruda": 2, "tasa_ajustada": 2, "smr": 3, "esperados": 1})


# ----------------------------------------------------------------------------- ejecución
def leer_interim():
    casos = pd.read_csv(config.INTERIM_DIR / "casos_raw.csv", low_memory=False)
    pob_2005 = pd.read_csv(config.INTERIM_DIR / "poblacion_2005_2017_raw.csv", dtype={"DP": str}, low_memory=False)
    pob_2018 = pd.read_csv(config.INTERIM_DIR / "poblacion_2018_2050_raw.csv", dtype={"DP": str}, low_memory=False)
    return casos, pob_2005, pob_2018


def run(casos=None, pob_2005=None, pob_2018=None):
    if casos is None:
        casos, pob_2005, pob_2018 = leer_interim()
    reporte = {}

    casos = limpiar_casos(casos, reporte)
    casos = normalizar_casos(casos, reporte)
    casos = reducir_casos(casos, reporte)
    tabla, casos, nombres = integrar(casos, pob_2005, pob_2018, reporte)
    tabla = enriquecer(tabla, reporte)
    dep = tasas_por_departamento(tabla, reporte)

    tabla = tabla[["cod_dpto", "departamento", "anio", "serie", "sexo", "grupo_edad", "casos",
                   "poblacion", "tasa_100k", "anio_provisional", "baja_confiabilidad"]]
    casos.to_csv(config.PROCESSED_DIR / "casos_limpios.csv", index=False, encoding="utf-8")
    tabla.to_csv(config.PROCESSED_DIR / "tabla_integrada.csv", index=False, encoding="utf-8")
    dep.to_csv(config.PROCESSED_DIR / "tasas_departamento.csv", index=False, encoding="utf-8")
    nombres.rename("departamento").to_csv(config.PROCESSED_DIR / "departamentos.csv", encoding="utf-8")
    with open(config.PROCESSED_DIR / "reporte_calidad.json", "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2)

    print("[TRANSFORM]")
    print(f"  casos limpios        {len(casos):>7,} registros x {casos.shape[1]} columnas")
    print(f"  tabla integrada      {len(tabla):>7,} filas, {tabla['casos'].sum():,} casos")
    print(f"  casos sin población  {reporte['casos_sin_poblacion']:>7}")
    return casos, tabla, dep, reporte


if __name__ == "__main__":
    run()
