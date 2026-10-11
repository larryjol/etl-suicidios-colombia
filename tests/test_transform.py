"""
Pruebas unitarias de las funciones de transformación.

Uso:  python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transform import transform as t  # noqa: E402


class TestTextos(unittest.TestCase):
    def test_corrige_texto_mal_codificado(self):
        self.assertEqual(t.corregir_codificacion("BogotÃ¡, D.C."), "Bogotá, D.C.")
        self.assertEqual(t.corregir_codificacion("Ã_x0081_brego"), "Ábrego")

    def test_no_altera_texto_correcto(self):
        self.assertEqual(t.corregir_codificacion("Quindío"), "Quindío")
        self.assertEqual(t.corregir_codificacion(15), 15)

    def test_normalizar_variantes(self):
        self.assertEqual(t.normalizar("Soltero (a)"), t.normalizar("Soltero(a)"))
        self.assertEqual(t.normalizar("Sin Información"), "sin informacion")


class TestGruposEdad(unittest.TestCase):
    def test_grupos_inmlcf(self):
        self.assertEqual(t.grupo_edad_inmlcf("(15 a 17)"), "15-17")
        self.assertEqual(t.grupo_edad_inmlcf("(18 a 19)"), "18-19")
        self.assertEqual(t.grupo_edad_inmlcf("(80 y más)"), "80+")

    def test_edad_simple_dane(self):
        casos = {0: "00-04", 4: "00-04", 5: "05-09", 15: "15-17", 17: "15-17",
                 18: "18-19", 19: "18-19", 20: "20-24", 79: "75-79", 80: "80+", 100: "80+"}
        for edad, grupo in casos.items():
            self.assertEqual(t.edad_a_grupo(edad), grupo, edad)


class TestLimpieza(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "ID": [1, 2, 3],
            "Código Dane Departamento": [5, 999, 11],
            "Estado Civil": ["Soltero(a)", "Sin información", "Soltero (a)"],
            "Manera de Muerte": ["Suicidio"] * 3,
        })

    def test_limpieza(self):
        reporte = {}
        out = t.limpiar_casos(self.df, reporte)
        self.assertEqual(len(out), 2)                                   # excluye el 999
        self.assertNotIn("Manera de Muerte", out.columns)               # columna constante
        self.assertEqual(reporte["etiquetas_faltante_convertidas_a_nulo"], 1)

    def test_normalizacion_unifica_variantes(self):
        reporte = {}
        out = t.normalizar_casos(t.limpiar_casos(self.df, {}), reporte)
        self.assertEqual(out["Estado Civil"].nunique(), 1)


class TestSalidas(unittest.TestCase):
    """Se ejecuta solo si ya corrió el pipeline."""
    def test_tabla_integrada(self):
        ruta = Path(__file__).resolve().parents[1] / "data" / "processed" / "tabla_integrada.csv"
        if not ruta.exists():
            self.skipTest("Ejecute primero python pipeline.py")
        tabla = pd.read_csv(ruta, dtype={"cod_dpto": str})
        self.assertEqual(len(tabla), 33 * 10 * 2 * 17)
        self.assertFalse(tabla.duplicated(["cod_dpto", "anio", "sexo", "grupo_edad"]).any())
        self.assertTrue((tabla["poblacion"] > 0).all())
        self.assertFalse(tabla[["cod_dpto", "anio", "sexo", "grupo_edad"]].isna().any().any())
        self.assertTrue(np.isclose(tabla["tasa_100k"], tabla["casos"] / tabla["poblacion"] * 1e5).all())


if __name__ == "__main__":
    unittest.main()
