"""M1 — Habilitación normativa y diagnóstico de bloqueos (Espínola, F. N.).

Plantillas de PI4 sin cambios (validadas con el linter oficial de Cypher y contra la base).
Nuevo en PG3: M1_RECORRIDO, que reconstruye el camino del grafo que justifica cada condición de un
dictamen (respuesta a la devolución de PI1–PI4: mostrar el recorrido, no solo la respuesta final).
"""
from __future__ import annotations

from .base import (CALIDAD_DATO_M1, HABILITACION_M1, VIGENCIA_M1, Seccion, sin_datos)

_CONTEXTO_M1 = """
  contexto_m1: {
    consulta: q.id, estado_consulta: q.estado, corte_en: q.corte_en,
    confiabilidad: [(q)-[:PRODUCE]->(cf:ConfiabilidadDato) |
                    {etiqueta: cf.etiqueta, valor: round(cf.valor, 3)}][0],
    reserva: size([(q)-[:PRODUCE]->(rv:Advertencia) WHERE rv.tipo = 'juicio_con_reserva' | rv]) > 0
  }"""

M1_DICTAMEN = """
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
MATCH (a:Asignatura {codigo: $codigo})
OPTIONAL MATCH (q)-[:PRODUCE]->(d:Dictamen {alcance: $alcance})-[:SOBRE]->(a)
WITH q, e, a, d,
     [(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)-[:REFIERE_A]->(a) | s.valor] AS est
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  asignatura: {codigo: a.codigo, nombre: a.nombre,
               estado_en_historia: coalesce(est[0], 'pendiente (sin registro)')},
  alcance_consultado: $alcance,
  dictamen: CASE WHEN d IS NULL THEN null ELSE {
    id: d.id,
    tipo: CASE WHEN d:BloqueoHeredado THEN 'BloqueoHeredado' WHEN d:Bloqueo THEN 'BloqueoDirecto'
               WHEN d:HabilitacionRendir THEN 'HabilitacionRendir' ELSE 'HabilitacionCursar' END,
    condicionado: d.condicionado,
    profundidad: d.profundidad,
    causas: [(d)-[o:ORIGINADO_POR]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
             {correlatividad: c.id, tipo: c.tipo, asignatura: y.nombre,
              estado_encontrado: o.estado_encontrado, condicionada: o.condicionado, causa: o.causa}],
    condiciones_verificadas: [(d)-[:VERIFICA]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
             {correlatividad: c.id, tipo: c.tipo, asignatura: y.nombre}],
    hereda_de: [(d)-[:HEREDA_DE]->(p:Dictamen)-[:SOBRE]->(pa:Asignatura) |
             {asignatura: pa.nombre, dictamen: p.id}],
    causa_raiz: [(d)-[:CAUSA_RAIZ]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
             {correlatividad: c.id, tipo: c.tipo, asignatura: y.nombre}],
    reglas: [(d)-[:JUSTIFICADO_POR]->(r:Regla) |
             {id: r.id, enunciado: r.enunciado, estado: r.estado}]
  } END,
  correlativas_de_la_asignatura: [(a)-[:EXIGE]->(c:Correlatividad)-[:APUNTA_A]->(y:Asignatura) |
    {tipo: c.tipo, asignatura: y.nombre,
     estado_estudiante: coalesce(
       [(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s2:EstadoAcademico)-[:REFIERE_A]->(y) | s2.valor][0],
       'pendiente (sin registro)')}],
  advertencias: [(q)-[:PRODUCE]->(w:Advertencia)-[:SOBRE]->(a) |
    {tipo: w.tipo, mensaje: w.mensaje,
     reglas: [(w)-[:JUSTIFICADO_POR]->(r:Regla) | {id: r.id, enunciado: r.enunciado, estado: r.estado}]}],
""" + _CONTEXTO_M1 + """
} AS resultado
"""

M1_HABILITACIONES = """
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH (q)-[:PRODUCE]->(d:Dictamen {alcance: 'cursar'})-[:SOBRE]->(a:Asignatura)
WITH q, e, d, a ORDER BY a.codigo
WITH q, e, [x IN collect(CASE WHEN d IS NULL THEN null ELSE {
    asignatura: a.nombre, codigo: a.codigo,
    dictamen: CASE WHEN d:Bloqueo THEN 'bloqueada' ELSE 'habilitada' END,
    heredado: d:BloqueoHeredado,
    condicionado: coalesce(d.condicionado, false),
    causas: [(d)-[o:ORIGINADO_POR]->(:Correlatividad) | o.causa],
    sin_oferta: coalesce(d.sin_oferta, false)
                OR size([(q)-[:PRODUCE]->(w:Advertencia)-[:SOBRE]->(a) WHERE w.tipo = 'sin_oferta' | w]) > 0,
    reglas: [(d)-[:JUSTIFICADO_POR]->(r:Regla) | r.id]
  } END) WHERE $filtro = 'todas'
            OR ($filtro = 'habilitadas' AND x.dictamen = 'habilitada')
            OR ($filtro = 'bloqueadas' AND x.dictamen = 'bloqueada')] AS dictamenes
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo), filtro: $filtro,
  periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | p.id][0],
  total_habilitadas: size([x IN dictamenes WHERE x.dictamen = 'habilitada']),
  total_bloqueadas: size([x IN dictamenes WHERE x.dictamen = 'bloqueada']),
  dictamenes: dictamenes,
  glosario_reglas: [r IN reduce(acc = [], x IN [(q)-[:PRODUCE]->(:Dictamen)-[:JUSTIFICADO_POR]->(r0:Regla) | r0] |
                     CASE WHEN x IN acc THEN acc ELSE acc + x END) |
                   {id: r.id, enunciado: r.enunciado, estado: r.estado}],
""" + _CONTEXTO_M1 + """
} AS resultado
"""

M1_REGULARIDADES = """
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH (e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)-[:REFIERE_A]->(a:Asignatura),
               (s)-[:SUSTENTADO_POR]->(g:Regularidad)
WITH q, e, collect(CASE WHEN g IS NULL OR ($codigo IS NOT NULL AND a.codigo <> $codigo) THEN null ELSE {
    asignatura: a.nombre, codigo: a.codigo, estado_actual: s.valor,
    fecha_obtencion: toString(g.fecha_obtencion),
    fecha_vencimiento: toString(g.fecha_vencimiento),
    vigente: g.vigente, meses_para_vencer: round(g.meses_para_vencer, 1),
    final_rendido: g.final_rendido,
    vencimiento_registrado: size([(v:VencimientoRegularidad)-[:INVALIDA]->(g) | v]) > 0
  } END) AS regularidades
OPTIONAL MATCH (h01:Regla {id: 'H-01'})
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  asignatura_consultada: $codigo,
  inicio_periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | toString(p.fecha_inicio)][0],
  regularidades: regularidades,
  regla: {id: h01.id, enunciado: h01.enunciado, estado: h01.estado},
""" + _CONTEXTO_M1 + """
} AS resultado
"""

M1_HISTORIA = """
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH (e)-[:POSEE]->(h:HistoriaAcademica)
OPTIONAL MATCH (q)-[:PRODUCE]->(cf:ConfiabilidadDato)
OPTIONAL MATCH (x01:Regla {id: 'X-01'})
RETURN {
  estudiante: e.nombre, legajo: toString(e.legajo),
  historia: {fecha_actualizacion: toString(h.fecha_actualizacion),
             inconsistencias: h.inconsistencias,
             antiguedad_meses: round(h.antiguedad_meses, 2),
             completitud: round(h.completitud, 3)},
  mediciones_m1: [(q)-[:MIDE]->(m:Medicion) WHERE m.contexto = 'M1' |
                  {variable: m.variable, valor: round(m.valor, 3), etiqueta: m.etiqueta}],
  confiabilidad: CASE WHEN cf IS NULL THEN null ELSE {
    etiqueta: cf.etiqueta, valor: round(cf.valor, 3),
    antecedentes_sin_dato: cf.antecedentes_sin_dato,
    reglas_activadas: [(cf)-[j:JUSTIFICADO_POR]->(r:Regla) |
                       {id: r.id, alfa: round(j.alfa, 3), enunciado: r.enunciado, estado: r.estado}]
  } END,
  advertencias_m1: [(q)-[:PRODUCE]->(w:Advertencia) WHERE w.tipo = 'juicio_con_reserva' |
                    {tipo: w.tipo, mensaje: w.mensaje}],
  solicitudes_de_datos: [(q)-[:PRODUCE]->(sd:SolicitudDatos) |
                         {ambito: sd.ambito, motivo: sd.motivo, faltantes: sd.faltantes}] +
                        [(h)-[:ORIGINA]->(sd:SolicitudDatos) WHERE NOT (q)-[:PRODUCE]->(sd) |
                         {ambito: sd.ambito, motivo: sd.motivo, faltantes: sd.faltantes}],
  regla_corte: {id: x01.id, enunciado: x01.enunciado, estado: x01.estado},
""" + _CONTEXTO_M1 + """
} AS resultado
"""

# PG3 (devolución de la cátedra): recorrido del grafo que justifica cada condición de un dictamen.
# Para cada correlatividad, muestra la relación recorrida, el requisito, el estado registrado en la
# historia y el estado con que lo evaluó la regla. Se usa en la auditoría (--auditar, GET /auditar).
M1_RECORRIDO = """
MATCH (q:Consulta)-[:SOLICITADA_POR]->(e:Estudiante)
WHERE toString(e.legajo) = $legajo
MATCH (q)-[:PRODUCE]->(d:Dictamen {alcance: $alcance})-[:SOBRE]->(a:Asignatura {codigo: $codigo})
RETURN {
  camino: '(Estudiante)<-[:SOLICITADA_POR]-(Consulta)-[:PRODUCE]->(Dictamen)-[:SOBRE]->(Asignatura)',
  consulta: q.id, dictamen: d.id, asignatura: a.nombre, alcance: d.alcance,
  clase: [l IN labels(d) WHERE l IN ['HabilitacionCursar', 'HabilitacionRendir', 'BloqueoDirecto',
                                     'BloqueoHeredado', 'Bloqueo']],
  originado_por: [(d)-[o:ORIGINADO_POR]->(c:Correlatividad)-[:APUNTA_A]->(req:Asignatura) |
    {relacion: '(Dictamen)-[:ORIGINADO_POR]->(Correlatividad)-[:APUNTA_A]->(Asignatura)',
     correlatividad: c.id, exige: c.tipo, requisito: req.nombre,
     estado_en_historia: coalesce([(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)
                                   -[:REFIERE_A]->(req) | s.valor][0], 'sin registro'),
     estado_evaluado: o.estado_encontrado, condicionada: o.condicionado, causa: o.causa}],
  verifica: [(d)-[:VERIFICA]->(c:Correlatividad)-[:APUNTA_A]->(req:Asignatura) |
    {relacion: '(Dictamen)-[:VERIFICA]->(Correlatividad)-[:APUNTA_A]->(Asignatura)',
     correlatividad: c.id, exige: c.tipo, requisito: req.nombre,
     estado_en_historia: coalesce([(e)-[:POSEE]->(:HistoriaAcademica)-[:REGISTRA]->(s:EstadoAcademico)
                                   -[:REFIERE_A]->(req) | s.valor][0], 'sin registro')}],
  hereda_de: [(d)-[:HEREDA_DE]->(p:Dictamen)-[:SOBRE]->(pa:Asignatura) |
    {relacion: '(Dictamen)-[:HEREDA_DE]->(Dictamen)-[:SOBRE]->(Asignatura)', dictamen: p.id, asignatura: pa.nombre}],
  causa_raiz: [(d)-[:CAUSA_RAIZ]->(c:Correlatividad)-[:APUNTA_A]->(req:Asignatura) |
    {relacion: '(Dictamen)-[:CAUSA_RAIZ]->(Correlatividad)-[:APUNTA_A]->(Asignatura)',
     correlatividad: c.id, exige: c.tipo, requisito: req.nombre}],
  reglas: [(d)-[:JUSTIFICADO_POR]->(r:Regla) |
    {relacion: '(Dictamen)-[:JUSTIFICADO_POR]->(Regla)', id: r.id, estado: r.estado, enunciado: r.enunciado}]
} AS recorrido
"""

# Consulta para ver el subgrafo en Neo4j Browser / Aura (captura del video). No la ejecuta el asistente.
M1_RECORRIDO_VISUAL = """
MATCH (e:Estudiante)<-[:SOLICITADA_POR]-(q:Consulta)-[:PRODUCE]->(d:Dictamen {alcance: $alcance})
      -[:SOBRE]->(a:Asignatura {codigo: $codigo})
WHERE toString(e.legajo) = $legajo
OPTIONAL MATCH p1 = (d)-[:ORIGINADO_POR|VERIFICA|CAUSA_RAIZ]->(:Correlatividad)-[:APUNTA_A]->(:Asignatura)
OPTIONAL MATCH p2 = (d)-[:JUSTIFICADO_POR]->(:Regla)
OPTIONAL MATCH p3 = (d)-[:HEREDA_DE]->(:Dictamen)-[:SOBRE]->(:Asignatura)
RETURN e, q, d, a, p1, p2, p3
"""

PLANTILLAS = {
    "M1_DICTAMEN": M1_DICTAMEN,
    "M1_HABILITACIONES": M1_HABILITACIONES,
    "M1_REGULARIDADES": M1_REGULARIDADES,
    "M1_HISTORIA": M1_HISTORIA,
    "M1_RECORRIDO": M1_RECORRIDO,
}


def _sin_contexto(r: dict | None) -> dict | None:
    """El contexto de la consulta viaja una sola vez (global), no repetido en cada sección.

    PG3 (error real de la demo, caso Valentina): si NO hay dictamen, el sistema experto no emitió juicio sobre la
    asignatura. Se quitan las correlativas (con ellas el LLM «razonaba» un bloqueo inexistente) y se agrega una nota
    explícita con el estado registrado en la historia. Las advertencias se conservan (p. ej. cursa_sin_rendir)."""
    if isinstance(r, dict):
        r = dict(r)
        r.pop("contexto_m1", None)
        if "alcance_consultado" in r and not r.get("dictamen"):
            estado = (r.get("asignatura") or {}).get("estado_en_historia", "sin registro")
            r.pop("correlativas_de_la_asignatura", None)
            r["sin_dictamen"] = (f"El sistema no emitió un dictamen para {r.get('alcance_consultado')} esta asignatura: "
                                 f"en la historia figura como «{estado}». No hay juicio de habilitación ni de bloqueo; "
                                 "no lo deduzcas.")
    return r


def ejecutar(kb, intencion: str, p: dict) -> Seccion:
    leg = p["legajo"]
    if intencion == "dictamen_asignatura":
        params = {"legajo": leg, "codigo": p["codigo"], "alcance": p.get("alcance") or "cursar"}
        r = kb.valor("M1_DICTAMEN", M1_DICTAMEN, **params)
        if r is None:
            return sin_datos("M1", intencion, HABILITACION_M1, "M1_DICTAMEN", params,
                             "No hay una consulta registrada para ese estudiante.")
        return Seccion("M1", intencion, HABILITACION_M1, "M1_DICTAMEN", params, _sin_contexto(r), resultado_crudo=r)
    if intencion == "habilitaciones":
        params = {"legajo": leg, "filtro": p.get("filtro") or "todas"}
        r = kb.valor("M1_HABILITACIONES", M1_HABILITACIONES, **params)
        if r is None:
            return sin_datos("M1", intencion, HABILITACION_M1, "M1_HABILITACIONES", params,
                             "No hay una consulta registrada para ese estudiante.")
        return Seccion("M1", intencion, HABILITACION_M1, "M1_HABILITACIONES", params, _sin_contexto(r),
                       resultado_crudo=r)
    if intencion == "vigencia_regularidad":
        params = {"legajo": leg, "codigo": p.get("codigo")}
        r = kb.valor("M1_REGULARIDADES", M1_REGULARIDADES, **params)
        if r is None:
            return sin_datos("M1", intencion, VIGENCIA_M1, "M1_REGULARIDADES", params,
                             "No hay una consulta registrada para ese estudiante.")
        return Seccion("M1", intencion, VIGENCIA_M1, "M1_REGULARIDADES", params, _sin_contexto(r), resultado_crudo=r)
    if intencion == "estado_historia":
        params = {"legajo": leg}
        r = kb.valor("M1_HISTORIA", M1_HISTORIA, **params)
        if r is None:
            return sin_datos("M1", intencion, CALIDAD_DATO_M1, "M1_HISTORIA", params,
                             "No hay una consulta registrada para ese estudiante.")
        return Seccion("M1", intencion, CALIDAD_DATO_M1, "M1_HISTORIA", params, _sin_contexto(r), resultado_crudo=r)
    raise ValueError(f"M1 no atiende la intención {intencion}")


def recorrido(kb, legajo: str, codigo: int, alcance: str = "cursar") -> dict | None:
    return kb.valor("M1_RECORRIDO", M1_RECORRIDO, legajo=legajo, codigo=codigo, alcance=alcance)
