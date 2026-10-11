"""
Genera las figuras de resultados del README a partir del data warehouse.
Requiere haber ejecutado antes:  python pipeline.py

Uso:  python docs/generar_figuras.py
"""
import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

DOCS = Path(__file__).resolve().parent
conn = sqlite3.connect(config.DB_PATH)

# Figura 1: casos frente a tasa ajustada por departamento
dep = pd.read_sql("SELECT * FROM tasas_departamento ORDER BY tasa_ajustada", conn)
nacional = pd.read_sql("SELECT SUM(casos) * 100000.0 / SUM(poblacion) AS t FROM hechos_suicidio", conn)["t"][0]

fig, ax = plt.subplots(1, 2, figsize=(12, 8), sharey=True)
ax[0].barh(dep["departamento"], dep["casos"], color="gray")
ax[0].set_title("Casos 2015-2024")
ax[1].barh(dep["departamento"], dep["tasa_ajustada"], color="steelblue")
ax[1].axvline(nacional, color="red", linestyle="--", label=f"Tasa nacional ({nacional:.2f})")
ax[1].set_title("Tasa ajustada por edad y sexo (x 100.000, 5 años y más)")
ax[1].legend(loc="lower right")
plt.tight_layout()
plt.savefig(DOCS / "tasas_departamento.png", dpi=150)
plt.close()

# Figura 2: tasa por año y sexo, consultada desde el DW
anual = pd.read_sql("""
SELECT t.anio, m.sexo, SUM(h.casos) * 100000.0 / SUM(h.poblacion) AS tasa
FROM hechos_suicidio h
JOIN dim_tiempo t ON h.anio = t.anio
JOIN dim_demografia m ON h.id_demografia = m.id_demografia
GROUP BY t.anio, m.sexo""", conn).pivot(index="anio", columns="sexo", values="tasa")

plt.figure(figsize=(10, 4.5))
plt.plot(anual.index, anual["Hombre"], marker="o", label="Hombres")
plt.plot(anual.index, anual["Mujer"], marker="o", label="Mujeres")
plt.axvline(2017.5, color="gray", linestyle="--", linewidth=1)
plt.text(2017.6, anual.values.max() * 0.55, "cambio de serie\npoblacional", fontsize=8, color="gray")
plt.axvspan(2023.5, 2024.5, color="orange", alpha=0.15, label="Año provisional")
plt.xticks(anual.index)
plt.ylabel("Tasa por 100.000 (5 años y más)")
plt.title("Tasa de presuntos suicidios por año y sexo")
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(DOCS / "tasa_anual_sexo.png", dpi=150)
plt.close()

conn.close()
print("Figuras guardadas en docs/")
