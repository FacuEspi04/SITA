"""M2 — Carga académica y capacidad del estudiante (Manuel, F. N.).

Plantilla CAPACIDAD_M2 de PI4 sin cambios. Se conserva la «lectura guiada» de M2: frases
generadas con reglas fijas de Python sobre los MISMOS valores de la traza (no agrega datos), que
evita que el modelo invierta el signo de la holgura o confunda sobrecarga con atraso.
"""
from __future__ import annotations

from ..textos import fmt_num
from .base import CAPACIDAD_M2, Seccion, sin_datos

M2_CAPACIDAD = """
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)
OPTIONAL MATCH (e)-[:DECLARA_CONTEXTO]->(ctx:ContextoEstudiante)
OPTIONAL MATCH (q)-[:PRODUCE]->(ev:EvaluacionCarga)
OPTIONAL MATCH (ev)-[:DETERMINA]->(ta:TamanioAdmisible)
OPTIONAL MATCH (q)-[:PRODUCE]->(rs:RiesgoSobrecarga)
RETURN {
  estudiante: e.nombre, legajo: e.legajo, estado_consulta: q.estado, corte_en: q.corte_en,
  periodo: [(q)-[:REFERIDA_A]->(p:Periodo) | p.id][0],
  horas_trabajo_semanales: ctx.horas_trabajo_semanales,
  carga_h: round(ev.carga_horas, 2), capacidad_h: ev.capacidad_horas, holgura_h: round(ev.holgura_horas, 2),
  carga_anuales_en_curso_h: ev.carga_anuales_en_curso,
  riesgo_sobrecarga: {etiqueta: rs.etiqueta, valor: round(rs.valor, 2),
                      reglas: [(rs)-[j:JUSTIFICADO_POR]->(r:ReglaDifusa) | {regla: r.id, alfa: round(j.alfa, 2)}],
                      sin_dato: rs.antecedentes_sin_dato},
  tamano_base: ta.base, tamano_admisible: ta.valor, tope_declarado: ta.tope_declarado,
  ajustes: [(aj:Ajuste)-[:REDUCE]->(ta) | {tipo: [l IN labels(aj) WHERE l STARTS WITH 'AjustePor'][0],
                                           unidades: aj.unidades, causa: aj.causa,
                                           reglas: [(aj)-[:JUSTIFICADO_POR]->(r:Regla) |
                                                    {id: r.id, enunciado: r.enunciado, estado: r.estado}]}],
  items_evaluados: [(ev)-[:EVALUA]->(:ConjuntoCandidato)-[:CONTIENE]->(i:ItemCandidato) |
                    {asignatura: i.asignatura, alcance: i.alcance, horas_semanales: round(i.horas_dedicacion, 2)}],
  advertencias_m2: [(q)-[:PRODUCE]->(a:Advertencia) WHERE a.tipo IN ['margen_estrecho', 'sobrecarga_concentracion', 'discrepancia_tope']
                    | {tipo: a.tipo, mensaje: a.mensaje, reglas: [(a)-[:JUSTIFICADO_POR]->(r) | r.id]}],
  glosario_reglas: COLLECT {
    MATCH (q)-[:PRODUCE]->(:Conclusion)-[:JUSTIFICADO_POR]->(r:Regla)
    WHERE r.id STARTS WITH 'C-' OR r.id STARTS WITH 'RS' OR r.id = 'X-02'
    RETURN DISTINCT {id: r.id, enunciado: r.enunciado, estado: r.estado} AS regla
    ORDER BY regla.id}
} AS traza_m2
"""

PLANTILLAS = {"M2_CAPACIDAD": M2_CAPACIDAD}


# ------------------------------------------------------------------ lectura guiada (PI4 de M2)
def _unidades(n) -> str:
    return f"{n} unidad" if n == 1 else f"{n} unidades"


def pistas_carga(c, cap, h, base=None, adm=None, ajustes=None, tope=None) -> list[str]:
    pistas = []
    if None not in (c, cap, h):
        if h < 0:
            pistas.append(f"La holgura es negativa ({fmt_num(h)} h): la carga ({fmt_num(c)} h) supera a la capacidad "
                          f"({fmt_num(cap)} h). Hay un déficit de {fmt_num(abs(h))} h semanales.")
        elif h == 0:
            pistas.append(f"La holgura es cero: la carga ({fmt_num(c)} h) iguala a la capacidad ({fmt_num(cap)} h).")
        else:
            pistas.append(f"La holgura es positiva ({fmt_num(h)} h): la capacidad ({fmt_num(cap)} h) supera a la "
                          f"carga ({fmt_num(c)} h).")
    if base is not None and adm is not None:
        if adm < base:
            causas = [f"{a.get('causa')} ({_unidades(a.get('unidades'))})" for a in (ajustes or [])]
            pistas.append(f"El plan se recortó de {base} a {adm} materias por estos ajustes: "
                          + (", ".join(causas) or "sin causa registrada") + ".")
        else:
            pistas.append(f"El tamaño admisible ({adm}) es igual al base ({base}): no hubo recorte.")
    elif adm is not None:
        pistas.append(f"El tamaño admisible del plan es {adm} materias.")
    if tope is not None and adm is not None and tope < adm:
        pistas.append(f"El estudiante declaró un tope de {tope} materias, menor que el tamaño admisible ({adm}); "
                      "el tope no modifica el tamaño admisible: se informan los dos valores.")
    return pistas


def pistas_riesgo_sobrecarga(rs) -> list[str]:
    if not isinstance(rs, dict):
        return []
    if rs.get("etiqueta") is None:
        return [f"No se pudo evaluar el riesgo de sobrecarga: faltó el dato {rs['sin_dato']}."] if rs.get("sin_dato") else []
    reglas = [r for r in (rs.get("reglas") or []) if r.get("regla")]
    txt = (f"Riesgo de sobrecarga: {rs['etiqueta']} (grado {fmt_num(rs.get('valor'))} entre 0 y 1, "
           "no es una probabilidad).")
    if reglas:
        dom = max(reglas, key=lambda r: r.get("alfa") or 0)
        txt += f" Se activaron {len(reglas)} reglas difusas, todas en algún grado; la de mayor activación es {dom['regla']}."
    if rs.get("sin_dato"):
        txt += f" Faltó el dato: {rs['sin_dato']}."
    return [txt]


def desglose_carga(t: dict) -> dict | None:
    """Componentes de la carga total (corrección de la cátedra, E2E-02/04): las horas de las asignaturas evaluadas
    para el período MÁS las de las anuales en curso. Sin este dato explícito, el LLM listaba las asignaturas
    (24,25 h) y saltaba al total (31 h). Solo se informa si los componentes suman el total registrado."""
    items, anuales, total = t.get("items_evaluados") or [], t.get("carga_anuales_en_curso_h") or 0, t.get("carga_h")
    if not items or not anuales or total is None:
        return None
    del_periodo = round(sum(i.get("horas_semanales") or 0 for i in items), 2)
    if abs(del_periodo + anuales - total) > 0.05:
        return None
    return {"asignaturas_del_periodo_h": del_periodo, "anuales_en_curso_h": anuales, "total_h": total}


def lectura_guiada(t: dict) -> list[str]:
    pistas = pistas_carga(t.get("carga_h"), t.get("capacidad_h"), t.get("holgura_h"), t.get("tamano_base"),
                          t.get("tamano_admisible"), t.get("ajustes"), t.get("tope_declarado"))
    d = t.get("desglose_carga")
    if d:
        pistas.append(f"La carga total de {fmt_num(d['total_h'])} h se compone de {fmt_num(d['asignaturas_del_periodo_h'])} h "
                      f"de las asignaturas evaluadas para el período más {fmt_num(d['anuales_en_curso_h'])} h semanales "
                      "de asignaturas anuales en curso; si se detallan horas por asignatura, hay que incluir las anuales.")
    elif t.get("carga_anuales_en_curso_h"):
        pistas.append(f"La carga incluye {fmt_num(t['carga_anuales_en_curso_h'])} h semanales de asignaturas "
                      "anuales en curso.")
    pistas += pistas_riesgo_sobrecarga(t.get("riesgo_sobrecarga"))
    advs = [a.get("mensaje") for a in (t.get("advertencias_m2") or []) if a.get("mensaje")]
    if advs:
        pistas.append("Advertencias (informan, pero no recortan el plan ni cambian el riesgo): " + "; ".join(advs) + ".")
    return pistas


def _completar_glosario(t: dict) -> list[dict]:
    glosario = list(t.get("glosario_reglas") or [])
    ids = {r.get("id") for r in glosario}
    for a in (t.get("ajustes") or []):
        for r in (a.get("reglas") or []):
            if r.get("id") and r["id"] not in ids:
                glosario.append(r)
                ids.add(r["id"])
    return sorted(glosario, key=lambda r: str(r.get("id")))


def ejecutar(kb, intencion: str, p: dict) -> Seccion:
    if intencion != "capacidad":
        raise ValueError(f"M2 no atiende la intención {intencion}")
    params = {"legajo": p["legajo"]}
    r = kb.valor("M2_CAPACIDAD", M2_CAPACIDAD, **params)
    if r is None:
        return sin_datos("M2", intencion, CAPACIDAD_M2, "M2_CAPACIDAD", params,
                         "Todavía no hay una evaluación de carga registrada para vos.")
    t = dict(r)
    t["glosario_reglas"] = _completar_glosario(t)
    if desglose_carga(t):
        t["desglose_carga"] = desglose_carga(t)
    t["lectura_guiada"] = lectura_guiada(t)
    return Seccion("M2", intencion, CAPACIDAD_M2, "M2_CAPACIDAD", params, t, resultado_crudo=r)
