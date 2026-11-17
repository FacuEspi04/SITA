"""Pruebas de extremo a extremo con Neo4j y LLM reales (al menos tres casos complejos que cruzan submódulos).

Ejecutar:  SITA_TEST_E2E=1 python -m pytest tests/test_e2e_llm.py -v
Como el LLM no es determinista, cada caso se puede repetir con SITA_E2E_REPETICIONES=3 y se informa la tasa.
"""
import os
import time

import pytest

from sita.casos import CASOS

pytestmark = pytest.mark.skipif(os.getenv("SITA_TEST_E2E") != "1", reason="requiere Neo4j + LLM (SITA_TEST_E2E=1)")
REPETICIONES = int(os.getenv("SITA_E2E_REPETICIONES", "1"))


@pytest.fixture(scope="module")
def orq():
    from sita.servicios import crear
    cfg, kb, o = crear()
    yield o
    kb.cerrar()


@pytest.mark.parametrize("caso", [c for c in CASOS if c["tipo"] == "integrado"], ids=lambda c: c["id"])
def test_caso_integrado(orq, caso):
    aciertos = 0
    for i in range(REPETICIONES):
        t = orq.procesar(caso["texto"], sesion_id=f"e2e-{caso['id']}-{i}")
        consultados = set(t.get("modulos_consultados") or [])
        no_eval = {n["intencion"] for n in t.get("no_evaluado") or []}
        ok = set(caso["modulos_minimos"]) <= consultados and set(caso.get("no_evaluados", [])) <= no_eval \
            and t["flujo"] == "sandwich completo"
        aciertos += ok
        time.sleep(float(os.getenv("LLM_PAUSA", "0")))
    assert aciertos == REPETICIONES, f"{caso['id']}: {aciertos}/{REPETICIONES} con los submódulos esperados"
