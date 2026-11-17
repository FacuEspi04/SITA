"""Consultas transversales: estado de la consulta del estudiante y traza de corte (reglas X-).

X_CONTEXTO se ejecuta siempre antes de los submódulos: decide si la consulta está cortada y dónde,
y aporta la confiabilidad del dato (M1) que condiciona cualquier respuesta (X-01, reserva).
X_CORTE es la consulta 12.3 de PG2 en la versión ampliada de M2 (también encuentra la solicitud
originada por la historia académica y la confiabilidad).
"""
from __future__ import annotations

from .base import SOLICITUD_DATOS, Seccion, sin_datos

X_CONTEXTO = """
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  consulta: q.id, estado: q.estado, corte_en: q.corte_en,
  periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | p.id][0],
  confiabilidad: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) | {etiqueta: cf.etiqueta, valor: round(cf.valor, 3)}][0],
  reserva: [(q)-[:PRODUCE]->(rv:Advertencia) WHERE rv.tipo = 'juicio_con_reserva' | rv.mensaje][0]
} AS contexto
LIMIT 1
"""

X_CORTE = """
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)
WITH e, q, [(q)-[:PRODUCE]->(s:SolicitudDatos) | s]
           + [(e)-[:POSEE]->(:HistoriaAcademica)-[:ORIGINA]->(s:SolicitudDatos) | s] AS solicitudes
WHERE size(solicitudes) > 0
WITH e, q, solicitudes[0] AS s
RETURN {estudiante: e.nombre, estado_consulta: q.estado, corte_en: q.corte_en, ambito: s.ambito, motivo: s.motivo,
        faltantes: s.faltantes,
        reglas: [(s)-[:JUSTIFICADO_POR]->(r:Regla) | {id: r.id, enunciado: r.enunciado, estado: r.estado}],
        confiabilidad_del_dato_M1: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) | {etiqueta: cf.etiqueta, valor: round(cf.valor, 2)}][0],
        dictamenes_conservados: COUNT { (q)-[:PRODUCE]->(:Dictamen) }} AS traza_corte
"""

PLANTILLAS = {"X_CONTEXTO": X_CONTEXTO, "X_CORTE": X_CORTE}


def contexto(kb, legajo: str) -> dict | None:
    return kb.valor("X_CONTEXTO", X_CONTEXTO, legajo=legajo)


def corte(kb, legajo: str, motivo: str) -> Seccion:
    params = {"legajo": legajo}
    r = kb.valor("X_CORTE", X_CORTE, **params)
    if r is None:
        s = sin_datos("X", "corte", SOLICITUD_DATOS, "X_CORTE", params,
                      "La consulta quedó detenida antes de evaluarse, pero el sistema no registra qué datos faltan.")
    else:
        s = Seccion("X", "corte", SOLICITUD_DATOS, "X_CORTE", params, r, resultado_crudo=r)
    s.origen, s.motivo = "contexto", motivo
    return s
