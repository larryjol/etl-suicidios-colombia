"""Configuración común del pipeline: rutas, nombres de archivos y constantes."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Las rutas se pueden cambiar con variables de entorno (ver .env.example)
DATA_DIR = Path(os.getenv("ETL_DATA_DIR", RAIZ / "data"))
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
DB_PATH = Path(os.getenv("ETL_DB_PATH", WAREHOUSE_DIR / "dw_suicidios.db"))

# Archivos fuente. El de casos puede estar en CSV (datos.gov.co) o en XLSX.
PATRON_CASOS_CSV = "Presuntos_Suicidios*.csv"   # nombre del CSV descargado de datos.gov.co
ARCHIVO_CASOS_XLSX = RAW_DIR / "Presuntos_Suicidios._Colombia_2015_a_2024._Cifras_definitivas_20260904.xlsx"
ARCHIVO_POB_2005 = RAW_DIR / "DCD-area-sexo-edad-proypoblacion-dep-2005-2017_VP_2005-2017_1.xlsx"
ARCHIVO_POB_2018 = RAW_DIR / "DCD-area-sexo-edad-proypoblacion-dep-2005-2017_VP_2018-2050_1.xlsx"

# Periodo de estudio y años que aporta cada archivo de población
ANIO_INICIO, ANIO_FIN = 2015, 2024
ANIOS_SERIE_2005 = (2015, 2017)
ANIOS_SERIE_2018 = (2018, 2024)
ANIO_PROVISIONAL = 2024          # patrón de faltantes distinto: se marca como provisional
ANIO_ESTANDAR = 2020             # población estándar para la tasa ajustada (método directo)

# Mismos 17 grupos de edad del INMLCF (separa 15-17 y 18-19). 0-4 años no entra al
# denominador porque el INMLCF no registra casos en ese grupo.
GRUPOS_EDAD = ["05-09", "10-14", "15-17", "18-19", "20-24", "25-29", "30-34", "35-39",
               "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]
BORDES_EDAD = [5, 10, 15, 18, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 200]

UMBRAL_BAJA_CONFIABILIDAD = 5    # celdas con menos de 5 casos
UMBRAL_MECANISMO_OTROS = 20      # mecanismos con menos de 20 casos se agrupan en "Otros"

for carpeta in (INTERIM_DIR, PROCESSED_DIR, WAREHOUSE_DIR):
    carpeta.mkdir(parents=True, exist_ok=True)
