"""Pruebas funcionales DETERMINISTAS contra la base real (sin LLM): recuperación, consultas, reglas y lógica difusa.

Se ejecutan solo con la base configurada:  SITA_TEST_NEO4J=1 python -m pytest tests/test_integracion_neo4j.py -v
Los valores esperados son los de PG2 y los PI4 del grupo.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(os.getenv("SITA_TEST_NEO4J") != "1", reason="requiere Neo4j (SITA_TEST_NEO4J=1)")


@pytest.fixture(scope="module")
def kb():
    from sita.config import Config
    from sita.kb import BaseConocimiento
    b = BaseConocimiento(Config.desde_entorno())
    yield b
    b.cerrar()


def test_recuperacion_catalogos(kb):
    from sita.catalogo import Catalogo
    cat = Catalogo.desde_kb(kb)
    assert len(cat.estudiantes) == 7 and len(cat.asignaturas) == 37
    assert cat.resolver_asignatura("Simu")[0]["codigo"] == 28 and cat.resolver_asignatura("IA")[0]["codigo"] == 31


def test_regla_H08_bloqueo_heredado_lucia_sistemas_de_gestion(kb):
    from sita.modulos import m1
    s = m1.ejecutar(kb, "dictamen_asignatura", {"legajo": "48115", "codigo": 33, "alcance": "cursar"})
    d = s.resultado["dictamen"]
    assert d["tipo"] == "BloqueoHeredado" and d["profundidad"] == 2
    assert [c["asignatura"] for c in d["causa_raiz"]] == ["Análisis Numérico"]
    assert {"H-04", "H-08"} <= {r["id"] for r in d["reglas"]}


def test_reglas_H03_H04_lucia_ia(kb):
    from sita.modulos import m1
    d = m1.ejecutar(kb, "dictamen_asignatura", {"legajo": "48115", "codigo": 31, "alcance": "cursar"}).resultado["dictamen"]
    assert d["tipo"] == "BloqueoDirecto"
    assert {c["asignatura"] for c in d["causas"]} == {"Simulación", "Análisis Numérico"}


def test_regla_H05_martina_habilitada_y_excluida_del_plan(kb):
    from sita.modulos import m1, m4
    assert m1.ejecutar(kb, "dictamen_asignatura", {"legajo": "48520", "codigo": 22}).resultado["dictamen"]["tipo"] \
        == "HabilitacionCursar"
    item = m4.ejecutar(kb, "decision_plan_asignatura", {"legajo": "48520", "codigo": 22}).resultado["items"][0]
    assert item["decision"] == "excluida" and item["empate_persistente"]


def test_regla_X01_corte_sofia(kb):
    from sita.modulos import transversal
    ctx = transversal.contexto(kb, "48301")
    assert ctx["estado"] == "cortada" and ctx["corte_en"] == "M1"
    assert abs(ctx["confiabilidad"]["valor"] - 0.244) < 0.001


def test_m2_capacidad_juan(kb):
    from sita.modulos import m2
    r = m2.ejecutar(kb, "capacidad", {"legajo": "47890"}).resultado
    assert (r["carga_h"], r["capacidad_h"], r["holgura_h"]) == (31, 25, -6)
    assert (r["tamano_base"], r["tamano_admisible"]) == (4, 3) and r["riesgo_sobrecarga"]["etiqueta"] == "alto"


def test_m4_plan_juan(kb):
    from sita.modulos import m4
    r = m4.ejecutar(kb, "plan", {"legajo": "47890"}).resultado
    assert [i["asignatura"] for i in r["plan"]][:1] == ["Simulación"]
    assert any(x["asignatura"] == "Ciencia de Datos" and x["causa"] == "capacidad" for x in r["excluidos"])


def test_logica_difusa_q5_reproduce_pg2_y_pi3(kb):
    from sita.modulos.m3 import verificar_difuso
    filas = verificar_difuso(kb)
    assert len(filas) == 4 and all(f["ok"] for f in filas), filas


def test_escenario_hipotetico_9_horas(kb):
    from sita.modulos import m3
    r = m3.ejecutar(kb, "riesgo_atraso", {"legajo": "47890", "horas_hipoteticas": 9}).resultado
    assert r["riesgo_atraso"]["etiqueta"] == "alto" and abs(r["riesgo_atraso"]["valor"] - 0.664) < 0.001
