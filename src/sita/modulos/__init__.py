"""Registro de submódulos: módulo -> adaptador con ejecutar(kb, intencion, params) -> Seccion."""
from . import m1, m2, m3, m4, transversal
from ..catalogo import CAT_ASIGNATURAS, CAT_ESTUDIANTES

REGISTRO = {"M1": m1, "M2": m2, "M3": m3, "M4": m4}


def todas_las_plantillas() -> dict[str, str]:
    """Lista blanca completa de consultas Cypher del asistente (para exportar, lintear y verificar)."""
    plantillas = {"CAT_ESTUDIANTES": CAT_ESTUDIANTES, "CAT_ASIGNATURAS": CAT_ASIGNATURAS}
    for mod in (transversal, m1, m2, m3, m4):
        plantillas.update(mod.PLANTILLAS)
    return plantillas
