"""M3 — Riesgo de atraso y estructura del plan (Suárez, C.).

Plantillas Q1–Q5 de PI4 sin cambios. Q5 re-ejecuta dentro de Neo4j la inferencia Mamdani de
SD-M3-RIESGO con los términos del grafo (escenarios hipotéticos de capacidad); verificar_difuso()
la compara con el valor almacenado en PG2 y con el motor de referencia de PI3 (prueba funcional
de la lógica difusa).
"""
from __future__ import annotations

import json
import math

from ..textos import fmt_num, sin_acentos
from .base import ESTRUCTURA_M3, RIESGO_M3, Seccion, sin_datos


# ------------------------------------------------------------------ funciones difusas como expresiones Cypher
def MU(t: str, x: str) -> str:
    """Pertenencia según TerminoLinguistico {funcion, centro, sigma} del grafo PG2."""
    return (f"(CASE WHEN {t}.funcion = 'crisp' THEN (CASE WHEN {x} = {t}.centro THEN 1.0 ELSE 0.0 END) "
            f"WHEN ({t}.funcion = 'gauss_hombro_izq' AND {x} <= {t}.centro) OR ({t}.funcion = 'gauss_hombro_der' "
            f"AND {x} >= {t}.centro) THEN 1.0 "
            f"ELSE exp(-(({x} - {t}.centro)^2) / (2.0 * {t}.sigma^2)) END)")


def MIN(*v: str) -> str:  # t-norma estándar (AND = MIN)
    return "reduce(mn = 1.0, v IN [" + ", ".join(v) + "] | CASE WHEN v < mn THEN v ELSE mn END)"


def MAX(*v: str) -> str:  # t-conorma estándar (OR = MAX)
    return "reduce(mx = 0.0, v IN [" + ", ".join(v) + "] | CASE WHEN v > mx THEN v ELSE mx END)"


_F_CONSULTA = """
MATCH (e:Estudiante {legajo: $legajo})<-[:SOLICITADA_POR]-(q:Consulta)-[:REFERIDA_A]->(per:Periodo)
WITH e, q, per ORDER BY q.fecha DESC LIMIT 1
OPTIONAL MATCH (q)-[:PRODUCE]->(rr:ResultadoRiesgo)
OPTIONAL MATCH (rr)-[:ESTIMA]->(rk:RiesgoAtraso)
OPTIONAL MATCH (q)-[:PRODUCE]->(sol:SolicitudDatos)
OPTIONAL MATCH (e)-[:POSEE]->(h:HistoriaAcademica)
OPTIONAL MATCH (h)-[:TIENE_CONFIABILIDAD]->(conf:ConfiabilidadDato)
MATCH (pl:ParametroModelo {id: 'corte_alfa_llave'}), (pu:ParametroModelo {id: 'corte_alfa_urgencia'})"""

_R_BASE = """
  estudiante: e {.legajo, .nombre, .anio_ingreso},
  consulta: q.id, periodo: per.id, fecha_referencia: toString(per.fecha_inicio),
  estado_consulta: q.estado, corte_en: q.corte_en,
  solicitud_de_datos: CASE WHEN sol IS NULL THEN null ELSE {ambito: sol.ambito, motivo: sol.motivo, faltantes: sol.faltantes,
                      reglas: coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r.id], [])} END,
  confiabilidad_del_dato: CASE WHEN conf IS NULL THEN null ELSE {etiqueta: conf.etiqueta, valor: conf.valor} END"""

M3_Q1_RIESGO = _F_CONSULTA + """
RETURN {""" + _R_BASE + """,
  nivel_nominal: rr.nivel_nominal, nivel_alcanzado: rr.nivel_alcanzado,
  riesgo_atraso: CASE WHEN rk IS NULL THEN null ELSE {
    valor: rk.valor, etiqueta: rk.etiqueta, salvedad_E13: rk.salvedad, antecedentes_sin_dato: rk.antecedentes_sin_dato,
    grados: [(rk)-[a:ACTIVA]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: a.grado}],
    sistema_difuso: head([(rk)-[:CALCULADA_CON]->(sd:SistemaDifuso) |
                          sd {.id, .metodo, .op_and, .op_or, .implicacion, .agregacion, .defuzzificacion}])} END,
  reglas_difusas: [(rk)-[j:JUSTIFICADO_POR]->(r:Regla) | {id: r.id, enunciado: r.enunciado, estado: r.estado, alfa: j.alfa,
                   consecuente: head([(r)-[:CONSECUENTE]->(t:TerminoLinguistico) | t.nombre])}],
  arrastres: [(rr)-[:IDENTIFICA]->(f:Arrastre)-[:AFECTA_A]->(a:Asignatura) | {asignatura: a.nombre, estado: f.estado_asignatura,
              descendientes: a.cant_descendientes, grado_llave: a.grado_llave, peso: f.peso,
              reglas: [(f)-[:JUSTIFICADO_POR]->(r:Regla) | r.id]}],
  urgencias: [(rr)-[:IDENTIFICA]->(f:UrgenciaVencimiento)-[:AFECTA_A]->(a:Asignatura) | {asignatura: a.nombre,
              meses_para_vencer: f.meses, grado_urgencia: f.grado, severidad: f.severidad, a_confirmar: f.a_confirmar,
              vencimiento: head([(rg:Regularidad)-[:GENERA]->(f) | toString(rg.fecha_vencimiento)]),
              reglas: [(f)-[:JUSTIFICADO_POR]->(r:Regla) | r.id]}],
  cuellos_de_botella: [(rr)-[:IDENTIFICA]->(f:CuelloDeBotella) | {asignatura: f.asignatura, nivel_comprometido: f.nivel,
                       proporcion: f.proporcion}],
  ruta_critica: head([(rr)-[:IDENTIFICA]->(rc:RutaCritica) | rc.asignaturas]),
  asignaturas_llave: [(rr)-[l:IDENTIFICA_LLAVE]->(a:Asignatura) | {asignatura: a.nombre, grado_llave: l.grado}],
  capacidad_disponible: head([(m:Medicion)-[:MODULA]->(rk) | {horas_semanales: m.valor, etiqueta: m.etiqueta,
                        mu_baja: head([(m)-[p:PERTENECE]->(t:TerminoLinguistico {nombre: 'baja'}) | p.mu])}]),
  corte_alfa_llave: pl.valor,
  reglas: coalesce([(rr)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
        + coalesce([(rr)-[:IDENTIFICA]->()-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
        + coalesce([(rk)-[:JUSTIFICADO_POR]->(r:Regla) WHERE NOT r:ReglaDifusa | r {.id, .enunciado, .estado}], [])
        + coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
} AS resultado"""

M3_Q2_URGENCIAS = _F_CONSULTA + """
RETURN {""" + _R_BASE + """,
  horizonte_meses: $horizonte_meses,
  regularidades: [(h)-[:REGISTRA]->(ea:EstadoAcademico)-[:SUSTENTADO_POR]->(rg:Regularidad)
                  WHERE $horizonte_meses IS NULL OR coalesce(rg.meses_para_vencer, 0) <= $horizonte_meses |
                  {asignatura: head([(ea)-[:REFIERE_A]->(a:Asignatura) | a.nombre]), vencimiento: toString(rg.fecha_vencimiento),
                   vigente: rg.vigente, final_rendido: rg.final_rendido, meses_para_vencer: rg.meses_para_vencer,
                   proximidad: head([(m:Medicion)-[:SOBRE]->(rg) | [(m)-[p:PERTENECE]->(t:TerminoLinguistico) |
                                     {etiqueta: t.nombre, mu: p.mu}]]),
                   urgencia: head([(rg)-[:GENERA]->(u:UrgenciaVencimiento) | {grado: u.grado, severidad: u.severidad,
                                   a_confirmar: u.a_confirmar}]),
                   vencida_por: head([(ev:VencimientoRegularidad)-[:INVALIDA]->(rg) | {fecha: toString(ev.fecha),
                                      regla: head([(ev)-[:JUSTIFICADO_POR]->(r:Regla) | r.id])}])}],
  advertencias: [(q)-[:PRODUCE]->(adv:Advertencia) WHERE adv.tipo = 'perdida_regularidad' | {tipo: adv.tipo,
                 mensaje: adv.mensaje, severidad: adv.severidad,
                 asignatura: head([(adv)-[:SOBRE]->(a:Asignatura) | a.nombre])}],
  corte_alfa_urgencia: pu.valor,
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['H-01', 'E-07d'] RETURN r {.id, .enunciado, .estado} }
        + coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
} AS resultado"""

M3_Q3_ARRASTRES = _F_CONSULTA + """
RETURN {""" + _R_BASE + """,
  nivel_nominal: rr.nivel_nominal, nivel_alcanzado: rr.nivel_alcanzado, corte_alfa_llave: pl.valor,
  arrastres: [(rr)-[:IDENTIFICA]->(f:Arrastre)-[:AFECTA_A]->(a:Asignatura) | {asignatura: a.nombre, estado: f.estado_asignatura,
              nivel: head([(a)-[:PERTENECE_A]->(n:Nivel) | n.numero]),
              descendientes: a.cant_descendientes, grado_llave: a.grado_llave, es_llave: a.grado_llave >= pl.valor,
              criticidad: head([(m:Medicion)-[:SOBRE]->(a) WHERE m.variable = 'criticidad_estructural' |
                                [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}]])}],
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['E-01', 'E-02', 'E-03', 'E-04'] RETURN r {.id, .enunciado, .estado} }
        + coalesce([(sol)-[:JUSTIFICADO_POR]->(r:Regla) | r {.id, .enunciado, .estado}], [])
} AS resultado"""

M3_Q4_CRITICIDAD = """
MATCH (pl:ParametroModelo {id: 'corte_alfa_llave'})
UNWIND $codigos AS c
MATCH (a:Asignatura {codigo: c})
OPTIONAL MATCH (m:Medicion {variable: 'criticidad_estructural'})-[:SOBRE]->(a)
WITH pl, a, m ORDER BY a.codigo
WITH pl, collect({
  asignatura: a.nombre, codigo: a.codigo, sigla: a.sigla, dictado: a.dictado,
  nivel: head([(a)-[:PERTENECE_A]->(n:Nivel) | n.numero]),
  descendientes: a.cant_descendientes, grado_llave: a.grado_llave, es_llave: a.grado_llave >= pl.valor,
  criticidad: [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}],
  habilita_directamente: [(d:Asignatura)-[:EXIGE]->(k:Correlatividad)-[:APUNTA_A]->(a) | d.nombre + ' (exige ' + k.tipo + ')'],
  requiere: [(a)-[:EXIGE]->(k:Correlatividad)-[:APUNTA_A]->(r:Asignatura) | r.nombre + ' (' + k.tipo + ')'],
  llave_con_umbral_nitido_PG1: a.cant_descendientes >= 3}) AS asignaturas
RETURN {
  asignaturas: asignaturas,
  corte_alfa_llave: pl.valor,
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['E-03', 'E-04'] RETURN r {.id, .enunciado, .estado} }
} AS resultado"""

# Q5: re-ejecuta la inferencia Mamdani de SD-M3-RIESGO dentro de Neo4j con los términos del grafo.
# Con $horas_hipoteticas = null reproduce el valor almacenado (verificación); con un valor, simula ese escenario.
M3_Q5_RIESGO_SIMULADO = _F_CONSULTA + """
MATCH (tr:TerminoLinguistico {variable: 'riesgo_atraso'})
WITH e, q, per, rr, rk, sol, conf, pl, pu, h, collect(tr {.nombre, .funcion, .centro, .sigma}) AS TR
MATCH (tb:TerminoLinguistico {id: 'capacidad_disponible:baja'})
MATCH (rd:ReglaDifusa)<-[:CONTIENE]-(:SistemaDifuso {id: 'SD-M3-RIESGO'}), (rd)-[:CONSECUENTE]->(tc:TerminoLinguistico)
WITH e, q, per, rr, rk, sol, conf, pl, pu, h, TR, tb,
     collect({id: rd.id, enunciado: rd.enunciado, estado: rd.estado, consecuente: tc.nombre}) AS RD
// Entradas medidas en PG2: arrastre (peor caso por descendientes), proximidad y capacidad
WITH *, coalesce([(rr)-[:IDENTIFICA]->(:Arrastre)-[:AFECTA_A]->(a:Asignatura) | a], []) AS arr
WITH *, reduce(b = null, a IN arr | CASE WHEN b IS NULL OR a.cant_descendientes > b.cant_descendientes THEN a ELSE b END) AS peor
WITH *, CASE WHEN size(arr) > 0 THEN 1.0 ELSE 0.0 END AS A,
     CASE WHEN peor IS NULL THEN [] ELSE head([(m:Medicion)-[:SOBRE]->(peor) WHERE m.variable = 'criticidad_estructural' |
       [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}]]) END AS CR,
     head([(q)-[:MIDE]->(m:Medicion {variable: 'proximidad_vencimiento'}) | {valor: m.valor,
       grados: [(m)-[p:PERTENECE]->(t:TerminoLinguistico) | {etiqueta: t.nombre, mu: p.mu}]}]) AS PX,
     head([(m:Medicion)-[:MODULA]->(rk) | {valor: m.valor,
       mu_baja: head([(m)-[p:PERTENECE]->(t:TerminoLinguistico {nombre: 'baja'}) | p.mu])}]) AS CAP
WITH *, coalesce(head([c IN CR WHERE c.etiqueta = 'alta' | c.mu]), 0.0) AS cA,
     reduce(mm = 0.0, c IN CR | CASE WHEN c.etiqueta IN ['baja', 'media'] AND c.mu > mm THEN c.mu ELSE mm END) AS cBM,
     coalesce(head([p IN PX.grados WHERE p.etiqueta = 'inminente' | p.mu]), 0.0) AS pin,
     coalesce(head([p IN PX.grados WHERE p.etiqueta = 'cercana' | p.mu]), 0.0) AS pce,
     coalesce(head([p IN PX.grados WHERE p.etiqueta = 'lejana' | p.mu]), 1.0) AS lej,
     CASE WHEN $horas_hipoteticas IS NULL THEN coalesce(CAP.mu_baja, 0.0)
          ELSE """ + MU("tb", "toFloat($horas_hipoteticas)") + """ END AS capb
WITH *, """ + MAX("pin", "pce") + """ AS urg
WITH *, [r IN RD | r {.*,
  alfa: CASE r.id
    WHEN 'E-08d' THEN """ + MIN("A", "cA") + """
    WHEN 'E-09d' THEN """ + MIN("A", "urg", "capb") + """
    WHEN 'E-10d' THEN """ + MIN("1.0 - A", "urg") + """
    WHEN 'E-11d' THEN """ + MIN("1.0 - A", "lej") + """
    WHEN 'E-12d' THEN """ + MIN("A", "cBM") + """
    ELSE 0.0 END,
  t: head([t IN TR WHERE t.nombre = r.consecuente])}] AS acts
// Implicación MIN (recorte), agregación MAX y centroide sobre 1001 puntos de [0, 1]
WITH *, [i IN range(0, 1000) | toFloat(i) / 1000.0] AS Y
WITH *, [y IN Y | reduce(m = 0.0, r IN acts |
  CASE WHEN """ + MIN("r.alfa", MU("r.t", "y")) + """ > m THEN """ + MIN("r.alfa", MU("r.t", "y")) + """ ELSE m END)] AS agg
WITH *, reduce(s = 0.0, i IN range(0, 1000) | s + agg[i] * Y[i]) AS num, reduce(s = 0.0, v IN agg | s + v) AS den
WITH *, CASE WHEN den > 0 THEN num / den ELSE null END AS yc
WITH *, [t IN TR | {etiqueta: t.nombre, mu: """ + MU("t", "yc") + """}] AS grados_salida
WITH *, reduce(b = null, g IN grados_salida | CASE WHEN b IS NULL OR g.mu > b.mu THEN g ELSE b END).etiqueta AS etiqueta_salida
RETURN {""" + _R_BASE + """,
  escenario_hipotetico: $horas_hipoteticas IS NOT NULL,
  capacidad_disponible: {horas_registradas: CAP.valor, mu_baja_registrada: CAP.mu_baja,
                         horas_hipoteticas: $horas_hipoteticas, mu_baja_usada: capb},
  entradas_inferencia: {arrastre: A, peor_arrastre: peor.nombre, descendientes_peor_arrastre: peor.cant_descendientes,
                        criticidad_alta: cA, criticidad_baja_o_media: cBM, meses_regularidad_mas_proxima: PX.valor,
                        urgencia: urg, proximidad_lejana: lej, capacidad_baja: capb},
  reglas_difusas: [r IN acts | {id: r.id, enunciado: r.enunciado, estado: r.estado, consecuente: r.consecuente, alfa: r.alfa}],
  riesgo_atraso: CASE WHEN rk IS NULL OR yc IS NULL THEN null ELSE {valor: yc, etiqueta: etiqueta_salida, grados: grados_salida} END,
  riesgo_registrado_en_PG2: CASE WHEN rk IS NULL THEN null ELSE {valor: rk.valor, etiqueta: rk.etiqueta} END,
  reglas: COLLECT { MATCH (r:Regla) WHERE r.id IN ['E-07d', 'E-13'] RETURN r {.id, .enunciado, .estado} }
} AS resultado"""

PLANTILLAS = {
    "M3_Q1_RIESGO": M3_Q1_RIESGO,
    "M3_Q2_URGENCIAS": M3_Q2_URGENCIAS,
    "M3_Q3_ARRASTRES": M3_Q3_ARRASTRES,
    "M3_Q4_CRITICIDAD": M3_Q4_CRITICIDAD,
    "M3_Q5_RIESGO_SIMULADO": M3_Q5_RIESGO_SIMULADO,
}


# ------------------------------------------------------------------ presentación de la evidencia (PI4 de M3)
def _r(x, n=3):
    if isinstance(x, float):
        return round(x, n)
    if isinstance(x, dict):
        return {k: _r(v, n) for k, v in x.items()}
    if isinstance(x, list):
        return [_r(v, n) for v in x]
    return x


def _grados(lista):
    return {g["etiqueta"]: round(g["mu"], 3) for g in (lista or []) if isinstance(g, dict) and g.get("mu") is not None}


CLAVES_GRADOS = {"grados", "criticidad", "proximidad"}


def _compactar(x):
    """Listas [{etiqueta, mu}] -> {etiqueta: mu}; recursivo."""
    if isinstance(x, dict):
        return {k: (_grados(v) if k in CLAVES_GRADOS and isinstance(v, list) else _compactar(v)) for k, v in x.items()}
    if isinstance(x, list):
        return [_compactar(v) for v in x]
    return x


def armar_evidencia(res: dict) -> dict:
    """Solo da formato (redondeo, grados compactos, sin duplicados ni activaciones < 0,05): no agrega conocimiento."""
    ev = _compactar(_r(json.loads(json.dumps(res, default=str))))
    if ev.get("reglas"):
        vistos, unicas = set(), []
        for r in ev["reglas"]:
            if r and r.get("id") not in vistos:
                vistos.add(r.get("id"))
                unicas.append(r)
        ev["reglas"] = unicas
    if ev.get("reglas_difusas"):
        ev["reglas_difusas"] = sorted([r for r in ev["reglas_difusas"] if (r.get("alfa") or 0) >= 0.05],
                                      key=lambda r: -r["alfa"])
    for lista in ("urgencias", "regularidades"):
        for u in ev.get(lista) or []:
            if isinstance(u.get("meses_para_vencer"), (int, float)):
                u["meses_para_vencer"] = round(u["meses_para_vencer"], 1)
    return ev


# ------------------------------------------------------------------ ejecución
def ejecutar(kb, intencion: str, p: dict) -> Seccion:
    if intencion == "criticidad_asignatura":
        params = {"codigos": list(p["codigos"])}
        r = kb.valor("M3_Q4_CRITICIDAD", M3_Q4_CRITICIDAD, **params)
        if not r or not r.get("asignaturas"):
            return sin_datos("M3", intencion, ESTRUCTURA_M3, "M3_Q4_CRITICIDAD", params,
                             "No encontré esas asignaturas en el plan de estudios.")
        return Seccion("M3", intencion, ESTRUCTURA_M3, "M3_Q4_CRITICIDAD", params, armar_evidencia(r), resultado_crudo=r)

    params = {"legajo": p["legajo"], "horas_hipoteticas": None, "horizonte_meses": None}
    if intencion == "riesgo_atraso":
        if p.get("horas_hipoteticas") is not None:
            params["horas_hipoteticas"] = float(p["horas_hipoteticas"])
            qid, cy = "M3_Q5_RIESGO_SIMULADO", M3_Q5_RIESGO_SIMULADO
        else:
            qid, cy = "M3_Q1_RIESGO", M3_Q1_RIESGO
        tipo = RIESGO_M3
    elif intencion == "urgencias_vencimiento":
        params["horizonte_meses"] = p.get("horizonte_meses")
        qid, cy, tipo = "M3_Q2_URGENCIAS", M3_Q2_URGENCIAS, RIESGO_M3
    elif intencion == "arrastres":
        qid, cy, tipo = "M3_Q3_ARRASTRES", M3_Q3_ARRASTRES, ESTRUCTURA_M3
    else:
        raise ValueError(f"M3 no atiende la intención {intencion}")
    r = kb.valor(qid, cy, **params)
    if r is None:
        return sin_datos("M3", intencion, tipo, qid, params, "No hay una consulta de riesgo registrada para ese legajo.")
    ev = armar_evidencia(r)
    if intencion == "riesgo_atraso":
        causa = causa_del_riesgo(ev)
        if causa:
            ev["causa_del_riesgo"] = causa
    return Seccion("M3", intencion, tipo, qid, params, ev, resultado_crudo=r)


# Entradas del sistema difuso SD-M3-RIESGO (E-08d a E-12d en la base): arrastre y su criticidad, proximidad de
# vencimiento y capacidad disponible. La ruta crítica y los cuellos de botella NO son entradas de ese cálculo.


def _entradas(antecedente: str, ev: dict, arrastres: list[str]) -> list[str]:
    """Describe con los datos del caso cada entrada que usa la regla. Error real (Render 18/11, Juan 9 h): E-09d usa
    «hay arrastre», no su criticidad, y decir «la criticidad del arrastre de Tecnología para la Automatización» (grado
    0,018 de criticidad alta) llevó al LLM a repetirlo."""
    ent = ev.get("entradas_inferencia") or {}
    cap = ev.get("capacidad_disponible") or {}
    de = f" de {_lista(arrastres)}" if arrastres else ""
    out = []
    if "criticidad del arrastre" in antecedente:
        out.append(f"la criticidad del arrastre{de}")
    elif "arrastre" in antecedente:
        out.append(f"que arrastrás {_lista(arrastres)}" if arrastres else "que tenés una materia en arrastre")
    if "proximidad" in antecedente:
        meses = ent.get("meses_regularidad_mas_proxima")
        out.append("la cercanía de tu próximo vencimiento"
                   + (f" ({fmt_num(round(meses, 1))} meses)" if isinstance(meses, (int, float)) else ""))
    if "capacidad" in antecedente:
        h = cap.get("horas_hipoteticas")
        out.append("tu capacidad disponible" + (f" ({fmt_num(h)} h semanales en la simulación)" if h is not None else ""))
    return out


def causa_del_riesgo(ev: dict) -> dict | None:
    """Qué produjo el riesgo de atraso (corrida en Render 17/11, Martina): la respuesta decía «ese riesgo se apoya en la
    ruta crítica… y en los cuellos de botella», cuando lo produce E-08d, la criticidad del arrastre de Sistemas
    Operativos (grado 0,641). Se toma la regla de mayor activación con el mismo consecuente que la etiqueta."""
    ra = ev.get("riesgo_atraso") or {}
    reglas = [x for x in ev.get("reglas_difusas") or []
              if isinstance(x, dict) and x.get("consecuente") == ra.get("etiqueta") and x.get("alfa")]
    if not reglas:
        return None
    dom = max(reglas, key=lambda x: x["alfa"])
    texto = sin_acentos(dom.get("enunciado", "")).split("entonces")[0]
    arrastres = [a.get("asignatura") for a in ev.get("arrastres") or [] if isinstance(a, dict) and a.get("asignatura")]
    if not arrastres and (ev.get("entradas_inferencia") or {}).get("peor_arrastre"):
        arrastres = [ev["entradas_inferencia"]["peor_arrastre"]]   # la simulación (Q5) trae solo el peor arrastre
    partes = _entradas(texto, ev, arrastres)
    explicacion = (f"El riesgo de atraso {ra.get('etiqueta')} sale sobre todo de {_lista(partes) or 'la regla activada'}: "
                   f"es la regla que más se activó, con grado {fmt_num(dom['alfa'])}.")
    entradas = partes
    if ev.get("ruta_critica") or ev.get("cuellos_de_botella"):
        explicacion += (" La ruta crítica y los cuellos de botella describen tu trayectoria, pero no son entradas de "
                        "este cálculo.")
    return {"entradas": entradas, "arrastres": arrastres, "grado": dom["alfa"], "explicacion": explicacion}


def _lista(xs) -> str:
    xs = [str(x) for x in xs if x]
    return xs[0] if len(xs) == 1 else (", ".join(xs[:-1]) + " y " + xs[-1] if xs else "")


# ------------------------------------------------------------------ verificación de la inferencia difusa (PI4 de M3)
TERMINOS_PI3 = {
    "criticidad_estructural": {"baja": ("gauss_hombro_izq", 0.5, 0.85), "media": ("gauss", 2.5, 0.85),
                               "alta": ("gauss_hombro_der", 6.0, 2.12)},
    "proximidad_vencimiento": {"inminente": ("gauss_hombro_izq", 2.0, 0.85), "cercana": ("gauss", 6.0, 2.55),
                               "lejana": ("gauss_hombro_der", 12.0, 2.55)},
    "riesgo_atraso": {"bajo": ("gauss_hombro_izq", 0.25, 0.106), "medio": ("gauss", 0.50, 0.106),
                      "alto": ("gauss_hombro_der", 0.75, 0.106)},
    "capacidad_disponible": {"baja": ("gauss_hombro_izq", 8.0, 2.55)},
}
LEGAJOS_CON_RIESGO = ["47890", "48520", "48611", "48115"]  # Juan, Martina, Ana, Lucía


def _mu_ref(t: tuple, x: float) -> float:
    f, c, s = t
    if (f == "gauss_hombro_izq" and x <= c) or (f == "gauss_hombro_der" and x >= c):
        return 1.0
    return math.exp(-((x - c) ** 2) / (2 * s * s))


def motor_referencia(arrastre: bool, x1: float, x2: float, cap_baja: float) -> float:
    V = TERMINOS_PI3
    A = 1.0 if arrastre else 0.0
    C = {k: (_mu_ref(t, min(x1, 15)) if A else 0.0) for k, t in V["criticidad_estructural"].items()}
    P = {k: _mu_ref(t, min(x2, 24)) for k, t in V["proximidad_vencimiento"].items()}
    urg = max(P["inminente"], P["cercana"])
    reglas = [("alto", C["alta"]), ("alto", min(A, urg, cap_baja)), ("medio", min(1 - A, urg)),
              ("bajo", min(1 - A, P["lejana"])), ("medio", max(C["baja"], C["media"]))]
    Y = [i / 1000 for i in range(1001)]
    agg = [max(min(a, _mu_ref(V["riesgo_atraso"][lab], y)) for lab, a in reglas) for y in Y]
    return sum(m * y for m, y in zip(agg, Y)) / sum(agg)


def verificar_difuso(kb) -> list[dict]:
    """Q5 (inferencia ejecutada en Neo4j) vs. valor almacenado en PG2 vs. motor de PI3."""
    filas = []
    for leg in LEGAJOS_CON_RIESGO:
        r = kb.valor("M3_Q5_RIESGO_SIMULADO", M3_Q5_RIESGO_SIMULADO, legajo=leg, horas_hipoteticas=None,
                     horizonte_meses=None)
        if not r or not r.get("riesgo_atraso"):
            filas.append({"legajo": leg, "error": "sin resultado"})
            continue
        ei = r["entradas_inferencia"]
        cy, reg = r["riesgo_atraso"]["valor"], r["riesgo_registrado_en_PG2"]["valor"]
        meses = ei["meses_regularidad_mas_proxima"]
        ref = motor_referencia(ei["arrastre"] > 0, ei["descendientes_peor_arrastre"] or 0,
                               meses if meses is not None else 24.0, ei["capacidad_baja"])
        d = max(abs(cy - reg), abs(cy - ref))
        filas.append({"legajo": leg, "nombre": r["estudiante"]["nombre"], "neo4j_q5": cy, "pg2": reg,
                      "motor_pi3": ref, "delta_max": d, "ok": d < 0.005})
    return filas
