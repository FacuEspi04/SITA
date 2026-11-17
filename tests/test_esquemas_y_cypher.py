"""Contrato del enrutador y lista blanca de consultas Cypher."""
import re

import pytest
from pydantic import ValidationError

from sita.esquemas import INTENCIONES, Enrutamiento
from sita.modulos import todas_las_plantillas


def test_modulo_lo_fija_el_catalogo():
    e = Enrutamiento.model_validate({"legajo": "48.115", "pedidos": [
        {"modulo": "M2", "intencion": "dictamen_asignatura", "asignaturas": ["IA"]}]})
    assert e.legajo == "48115" and e.pedidos[0].modulo == "M1" and e.correcciones


def test_claves_extra_e_intenciones_desconocidas_se_rechazan():
    with pytest.raises(ValidationError):
        Enrutamiento.model_validate({"pedidos": [], "respuesta": "ya te respondo yo"})
    with pytest.raises(ValidationError):
        Enrutamiento.model_validate({"pedidos": [{"intencion": "aprobar_todo"}]})


def test_cada_intencion_tiene_un_unico_duenio():
    assert {i.modulo for i in INTENCIONES.values()} == {"M1", "M2", "M3", "M4"}
    assert INTENCIONES["dictamen_asignatura"].modulo == "M1" and INTENCIONES["plan"].modulo == "M4"


PARAMS = {"legajo", "codigo", "codigos", "alcance", "filtro", "horizonte_meses", "horas_hipoteticas"}


@pytest.mark.parametrize("qid,cypher", list(todas_las_plantillas().items()))
def test_plantillas_solo_lectura_balanceadas_y_con_parametros_conocidos(qid, cypher):
    sin_textos = re.sub(r"'[^']*'", "''", cypher)
    sin_textos = re.sub(r"//[^\n]*", "", sin_textos)
    assert not re.search(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|LOAD\s+CSV)\b", sin_textos, re.I), qid
    for a, b in ("()", "[]", "{}"):
        assert sin_textos.count(a) == sin_textos.count(b), (qid, a)
    assert set(re.findall(r"\$(\w+)", cypher)) <= PARAMS, qid


RE_COMPRENSION_UN_NODO = re.compile(r"\[\s*\(\w*(:\w+)?(\s*\{[^}]*\})?\)\s*(WHERE|\|)")


@pytest.mark.parametrize("qid,cypher", list(todas_las_plantillas().items()))
def test_sin_comprension_de_patron_de_un_solo_nodo(qid, cypher):
    """Error real en Render (17/11): `[(pm:ParametroModelo) WHERE … | …]` da CypherSyntaxError. Una comprensión de
    patrón necesita al menos una relación; para nodos sueltos se usa COLLECT { MATCH … RETURN … }."""
    assert not RE_COMPRENSION_UN_NODO.search(cypher), qid
