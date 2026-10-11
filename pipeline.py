"""
Orquesta el pipeline completo: extract -> transform -> load.

Si Prefect está instalado (pip install prefect), cada etapa corre como una tarea
de Prefect dentro de un flujo; si no, el pipeline corre igual como script de Python.

Uso:  python pipeline.py
"""
import time

from extract import extract
from load import load
from transform import transform

try:
    from prefect import flow, task
    ORQUESTADOR = "Prefect"
except ImportError:
    ORQUESTADOR = "Python (sin Prefect)"

    def task(fn=None, **_):
        return fn if fn else (lambda f: f)

    def flow(fn=None, **_):
        return fn if fn else (lambda f: f)


@task(name="extract")
def tarea_extract():
    return extract.run()


@task(name="transform")
def tarea_transform():
    _, tabla, _, reporte = transform.run()
    return {"filas": len(tabla), "casos": int(tabla["casos"].sum()), **{k: reporte[k] for k in
            ["casos_sin_poblacion", "pct_celdas_cero", "indice_dispersion_estandarizado"]}}


@task(name="load")
def tarea_load():
    return load.run()


@flow(name="etl-suicidios-colombia")
def pipeline():
    inicio = time.time()
    print(f"Pipeline ETL - presuntos suicidios por departamento (orquestador: {ORQUESTADOR})\n")
    tarea_extract()
    tarea_transform()
    tarea_load()
    print(f"\nPipeline terminado en {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    pipeline()
