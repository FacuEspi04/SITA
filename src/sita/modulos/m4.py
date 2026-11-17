"""M4 — Planificación, priorización y explicación (Ferreyra, P.).

M4_PLAN unifica las dos ampliaciones de la consulta 12.1 de PG2 que se hicieron en PI4:
  - M4 (Ferreyra): antecedentes_sin_dato y, en cada excluido, la habilitación de M1 que conserva
    (una exclusión del plan no es un bloqueo);
  - M2 (Manuel): tamaño base, ajustes (nodos Ajuste) y riesgo de sobrecarga, para ver cómo M2 limitó el plan.
M4_PLAN_ASIGNATURA es la consulta auxiliar de M4: qué decidió el plan sobre UNA asignatura.
"""
from __future__ import annotations

from .base import PLANIFICACION_M4, Seccion, sin_datos

M4_PLAN = """
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:REFERIDA_A]->(per:Periodo)
OPTIONAL MATCH (q)-[:PRODUCE]->(pc:PlanCursado)
OPTIONAL MATCH (q)-[:PRODUCE]->(cd:ConfiabilidadDato)
OPTIONAL MATCH (q)-[:PRODUCE]->(rk:RiesgoAtraso)
OPTIONAL MATCH (q)-[:PRODUCE]->(ad:AdecuacionPlan)
OPTIONAL MATCH (q)-[:PRODUCE]->(ev:EvaluacionCarga)-[:DETERMINA]->(ta:TamanioAdmisible)
OPTIONAL MATCH (q)-[:PRODUCE]->(rs:RiesgoSobrecarga)
RETURN {
  estudiante: e.nombre, legajo: e.legajo, periodo: per.id, estado_consulta: q.estado, corte_en: q.corte_en,
  confiabilidad: {etiqueta: cd.etiqueta, valor: round(cd.valor, 2), antecedentes_sin_dato: cd.antecedentes_sin_dato},
  capacidad: {carga_h: round(ev.carga_horas, 1), capacidad_h: ev.capacidad_horas, holgura_h: round(ev.holgura_horas, 1),
              tamano_base: ta.base, tamano_admisible: ta.valor, tope: ta.tope_declarado,
              ajustes: [(aj:Ajuste)-[:REDUCE]->(ta) | {tipo: [l IN labels(aj) WHERE l STARTS WITH 'AjustePor'][0],
                                                      unidades: aj.unidades, causa: aj.causa}],
              riesgo_sobrecarga: {etiqueta: rs.etiqueta, valor: round(rs.valor, 2),
                                  reglas: [(rs)-[j:JUSTIFICADO_POR]->(r:ReglaDifusa) | {regla: r.id, alfa: round(j.alfa, 2)}]}},
  plan: COLLECT {
    MATCH (pc)-[x:INCLUYE]->(i:ItemCandidato)
    RETURN {
          orden: x.orden, alcance: i.alcance, asignatura: i.asignatura, rango: i.rango,
          criterio: [(i)-[:TIENE_PRIORIDAD]->(pr) | pr.criterio][0],
          reglas: [(i)-[:TIENE_PRIORIDAD]->(:Prioridad)-[:JUSTIFICADO_POR]->(r) | r.id]
                  + [(d:Habilitacion)-[:ALIMENTA]->(i) | [(d)-[:JUSTIFICADO_POR]->(r2) | r2.id]][0],
          fundamentos: [(f:FactorDeRiesgo)-[:FUNDAMENTA]->(:Prioridad)<-[:TIENE_PRIORIDAD]-(i) |
                        {factor: f.id, grado: round(f.grado, 2)}]} AS item
    ORDER BY x.orden},
  excluidos: [(pc)-[x:EXCLUYE]->(i:ItemCandidato) | {asignatura: i.asignatura, alcance: i.alcance, causa: x.causa,
              empate_persistente: i.empate_persistente, regla_desempate: i.regla_desempate,
              habilitada_por: [(d:Habilitacion)-[:ALIMENTA]->(i) | [(d)-[:JUSTIFICADO_POR]->(r2) | r2.id]][0],
              reglas: [(pc)-[:JUSTIFICADO_POR]->(r3) | r3.id]}],
  advertencias: [(q)-[:PRODUCE]->(a:Advertencia) | {tipo: a.tipo, mensaje: a.mensaje,
                 reglas: [(a)-[:JUSTIFICADO_POR]->(r) | r.id]}],
  riesgo: {etiqueta: rk.etiqueta, valor: round(rk.valor, 2), salvedad: rk.salvedad,
           antecedentes_sin_dato: rk.antecedentes_sin_dato,
           reglas: [(rk)-[j:JUSTIFICADO_POR]->(r:ReglaDifusa) | {regla: r.id, alfa: round(j.alfa, 2)}]},
  adecuacion: {etiqueta: ad.etiqueta, valor: round(ad.valor, 2), antecedentes_sin_dato: ad.antecedentes_sin_dato},
  glosario_reglas: COLLECT {
    MATCH (q)-[:PRODUCE]->(:Conclusion)-[:JUSTIFICADO_POR]->(r:Regla)
    RETURN DISTINCT {id: r.id, enunciado: r.enunciado, estado: r.estado} AS regla
    ORDER BY regla.id}
} AS traza
"""

M4_PLAN_ASIGNATURA = """
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:PRODUCE]->(pc:PlanCursado)
RETURN {
  periodo: pc.periodo, tamano_efectivo: pc.tamano_efectivo,
  tamano_admisible: [(ta:TamanioAdmisible)-[:LIMITA]->(pc) | ta.valor][0],
  tope_declarado: [(ta:TamanioAdmisible)-[:LIMITA]->(pc) | ta.tope_declarado][0],
  items: [(pc)-[x:INCLUYE|EXCLUYE]->(i:ItemCandidato)-[:SOBRE]->(:Asignatura {codigo: $codigo}) |
          {decision: CASE type(x) WHEN 'INCLUYE' THEN 'incluida' ELSE 'excluida' END,
           asignatura: i.asignatura, alcance: i.alcance, orden: i.orden, causa: x.causa, rango: i.rango,
           criterio: [(i)-[:TIENE_PRIORIDAD]->(pr) | pr.criterio][0],
           empate_persistente: i.empate_persistente, regla_desempate: i.regla_desempate}],
  reglas: [(pc)-[:JUSTIFICADO_POR]->(r) | {id: r.id, enunciado: r.enunciado, estado: r.estado}]
          + COLLECT {
              MATCH (pc)-[:INCLUYE|EXCLUYE]->(i2:ItemCandidato)-[:SOBRE]->(:Asignatura {codigo: $codigo})
              MATCH (r4:Regla {id: i2.regla_desempate})
              RETURN DISTINCT {id: r4.id, enunciado: r4.enunciado, estado: r4.estado} AS regla}
} AS traza
"""

PLANTILLAS = {"M4_PLAN": M4_PLAN, "M4_PLAN_ASIGNATURA": M4_PLAN_ASIGNATURA}


def _renombrar_magnitudes(t: dict) -> dict:
    """Claves explícitas por submódulo (lectura guiada de M2): evita que el modelo confunda la
    confiabilidad del dato (M1), la sobrecarga (M2), el riesgo de atraso (M3) y la adecuación (M4)."""
    t = dict(t)
    t["capacidad_y_carga_M2"] = t.pop("capacidad", None)
    t["confiabilidad_del_dato_M1"] = t.pop("confiabilidad", None)
    t["riesgo_de_atraso_M3"] = t.pop("riesgo", None)
    t["adecuacion_del_plan_M4"] = t.pop("adecuacion", None)
    return t


def ejecutar(kb, intencion: str, p: dict) -> Seccion:
    if intencion == "plan":
        params = {"legajo": p["legajo"]}
        r = kb.valor("M4_PLAN", M4_PLAN, **params)
        if r is None:
            return sin_datos("M4", intencion, PLANIFICACION_M4, "M4_PLAN", params, "Todavía no hay un plan registrado para vos.")
        return Seccion("M4", intencion, PLANIFICACION_M4, "M4_PLAN", params, _renombrar_magnitudes(r), resultado_crudo=r)
    if intencion == "decision_plan_asignatura":
        params = {"legajo": p["legajo"], "codigo": p["codigo"]}
        r = kb.valor("M4_PLAN_ASIGNATURA", M4_PLAN_ASIGNATURA, **params)
        if not r or not r.get("items"):
            return sin_datos("M4", intencion, PLANIFICACION_M4, "M4_PLAN_ASIGNATURA", params,
                             f"{p.get('nombre_asignatura', 'Esa asignatura')} no fue candidata del plan de este período "
                             "(el plan solo ordena asignaturas habilitadas que se dictan en el período).")
        return Seccion("M4", intencion, PLANIFICACION_M4, "M4_PLAN_ASIGNATURA", params, r, resultado_crudo=r)
    raise ValueError(f"M4 no atiende la intención {intencion}")
