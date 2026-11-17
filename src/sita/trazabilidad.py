"""Trazabilidad del conocimiento (sección 7 de PG3 y devolución de la cátedra sobre M1).

Para cada conclusión de una respuesta reconstruye los cinco elementos que pide la consigna:
  fuente del conocimiento · regla utilizada · evidencia considerada · consulta ejecutada · explicación generada
y, para los dictámenes de M1, el RECORRIDO del grafo que justifica cada condición (M1_RECORRIDO),
más la consulta lista para pegar en Neo4j Browser/Aura y ver el subgrafo.
"""
from __future__ import annotations

from .modulos import m1, todas_las_plantillas
from .textos import a_json, fmt_num

FUENTES = {
    "M1": "Régimen de correlatividades del Plan 2023 (Ord. 1877) y reglas H- / X-01 del Cuaderno de Conocimiento (PG1)",
    "M2": "Reglas C- de carga y capacidad y sistema difuso de sobrecarga RS1–RS3 (PI3 de M2, implementado en PG2)",
    "M3": "Reglas E- de estructura y sistema difuso SD-M3-RIESGO (PI3 de M3, implementado en PG2)",
    "M4": "Criterios de priorización del experto, reglas P- (PI1–PI3 de M4, implementado en PG2)",
    "X": "Reglas de corte X-01 a X-03 del modelo integrado (PG1)",
}


def _reglas_con_enunciado(obj, acc: dict) -> dict:
    if isinstance(obj, dict):
        if "id" in obj and ("enunciado" in obj or "estado" in obj) and isinstance(obj.get("id"), str):
            acc.setdefault(obj["id"], {"id": obj["id"], "estado": obj.get("estado"), "enunciado": obj.get("enunciado")})
        for v in obj.values():
            _reglas_con_enunciado(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _reglas_con_enunciado(v, acc)
    return acc


def _evidencia(sec: dict) -> list[str]:
    """Hechos clave del resultado, por tipo de sección (lo que la regla tomó como premisa)."""
    r = sec.get("resultado") or {}
    ev: list[str] = []
    if sec["modulo"] == "M1" and isinstance(r.get("asignatura"), dict):
        a = r["asignatura"]
        ev.append(f"{a.get('nombre')}: estado en la historia = {a.get('estado_en_historia')}")
        d = r.get("dictamen") or {}
        if d:
            ev.append(f"dictamen {d.get('id')} ({d.get('tipo')}, profundidad {d.get('profundidad')})")
        for c in d.get("causas") or []:
            ev.append(f"correlatividad {c.get('correlatividad')} -> {c.get('asignatura')}: evaluada como "
                      f"«{c.get('estado_encontrado')}»" + (" (condicionada)" if c.get("condicionada") else ""))
        for c in d.get("causa_raiz") or []:
            ev.append(f"causa raíz: correlatividad {c.get('correlatividad')} -> {c.get('asignatura')}")
        for c in d.get("condiciones_verificadas") or []:
            ev.append(f"verificada: correlatividad {c.get('correlatividad')} -> {c.get('asignatura')}")
    elif sec["modulo"] == "M2":
        ev += [f"carga {fmt_num(r.get('carga_h'))} h, capacidad {fmt_num(r.get('capacidad_h'))} h, "
               f"holgura {fmt_num(r.get('holgura_h'))} h",
               f"tamaño base {r.get('tamano_base')} -> admisible {r.get('tamano_admisible')}, tope {r.get('tope_declarado')}"]
        rs = r.get("riesgo_sobrecarga") or {}
        if rs:
            ev.append("riesgo de sobrecarga " + str(rs.get("etiqueta")) + " (" + fmt_num(rs.get("valor")) + "); α: "
                      + ", ".join(f"{x.get('regla')}={fmt_num(x.get('alfa'))}" for x in rs.get("reglas") or []))
    elif sec["modulo"] == "M3":
        ra = r.get("riesgo_atraso") or {}
        if ra:
            ev.append(f"riesgo de atraso {ra.get('etiqueta')} ({fmt_num(ra.get('valor'))}), grados {ra.get('grados')}")
        for x in r.get("reglas_difusas") or []:
            ev.append(f"{x.get('id')} activada con α = {fmt_num(x.get('alfa'))}")
        for a in r.get("asignaturas") or []:
            ev.append(f"{a.get('asignatura')}: {a.get('descendientes')} descendientes, grado de llave "
                      f"{fmt_num(a.get('grado_llave'))} (corte α {fmt_num(r.get('corte_alfa_llave'))})")
        llaves = r.get("asignaturas_llave") or []
        if llaves:
            ev.append("asignaturas llave (IDENTIFICA_LLAVE): " + ", ".join(
                f"{a.get('asignatura')} ({fmt_num(a.get('grado_llave'))})" for a in llaves))
        for a in r.get("arrastres") or []:
            ev.append(f"arrastre {a.get('asignatura')} ({a.get('estado')})")
    elif sec["modulo"] == "M4":
        for i in r.get("plan") or []:
            ev.append(f"{i.get('orden')}. {i.get('alcance')} {i.get('asignatura')} (criterio {i.get('criterio')})")
        for x in r.get("excluidos") or []:
            ev.append(f"excluida {x.get('asignatura')}: causa {x.get('causa')}; habilitada por {x.get('habilitada_por')}")
        for i in r.get("items") or []:
            ev.append(f"{i.get('decision')} (causa {i.get('causa')}, criterio {i.get('criterio')})")
    elif sec["modulo"] == "X":
        ev.append(f"corte en {r.get('corte_en')}: {r.get('motivo')}; faltan {r.get('faltantes')}")
    if sec.get("estado") != "ok":
        ev.append(f"sin datos: {sec.get('mensaje')}")
    return ev


def _reproducir(consulta_id: str, params: dict) -> str:
    cypher = todas_las_plantillas().get(consulta_id, "")
    return f":params {a_json(params)}\n{cypher.strip()}"


def auditar(traza: dict, kb=None) -> dict:
    """Informe de trazabilidad de una respuesta. Con kb, agrega el recorrido del grafo de los dictámenes."""
    informe = {"traza_id": traza.get("traza_id"), "entrada": traza.get("entrada"),
               "modulos_consultados": traza.get("modulos_consultados"), "conclusiones": [],
               "no_evaluado": traza.get("no_evaluado", []), "explicacion": traza.get("respuesta"),
               "fundamento": traza.get("fundamento"), "verificacion": traza.get("verificacion")}
    for sec in traza.get("secciones", []):
        item = {
            "modulo": sec["modulo"], "intencion": sec["intencion"], "origen": sec["origen"],
            "motivo_origen": sec.get("motivo"), "tipo_decision": sec["tipo_decision"],
            "fuente": FUENTES.get(sec["modulo"]),
            "reglas": list(_reglas_con_enunciado(sec.get("resultado") or {}, {}).values()) or
                      [{"id": i} for i in sec.get("reglas", [])],
            "evidencia": _evidencia(sec),
            "consulta": {"id": sec["consulta_id"], "parametros": sec["parametros"],
                         "reproducir_en_neo4j_browser": _reproducir(sec["consulta_id"], sec["parametros"])},
        }
        if kb is not None and sec["consulta_id"] == "M1_DICTAMEN" and sec.get("estado") == "ok":
            p = sec["parametros"]
            item["recorrido_grafo"] = m1.recorrido(kb, p["legajo"], p["codigo"], p.get("alcance", "cursar"))
            item["ver_subgrafo"] = f":params {a_json(p)}\n{m1.M1_RECORRIDO_VISUAL.strip()}"
        informe["conclusiones"].append(item)
    return informe


def formatear(informe: dict) -> str:
    """Versión de texto para la terminal (modo --auditar)."""
    L = [f"AUDITORÍA DE LA RESPUESTA · traza {informe['traza_id']}", f"Entrada: {informe['entrada']}",
         f"Submódulos consultados: {', '.join(informe.get('modulos_consultados') or [])}"]
    for i, c in enumerate(informe["conclusiones"], 1):
        L.append(f"\n[{i}] {c['modulo']} · {c['intencion']} · {c['tipo_decision']} · {c['origen']}"
                 + (f" ({c['motivo_origen']})" if c.get("motivo_origen") else ""))
        L.append(f"  Fuente del conocimiento: {c['fuente']}")
        for r in c["reglas"]:
            L.append(f"  Regla: {r['id']}" + (f" [{r.get('estado')}]" if r.get("estado") else "")
                     + (f" — {r['enunciado']}" if r.get("enunciado") else ""))
        for e in c["evidencia"]:
            L.append(f"  Evidencia: {e}")
        L.append(f"  Consulta ejecutada: {c['consulta']['id']} {a_json(c['consulta']['parametros'])}")
        rec = c.get("recorrido_grafo")
        if rec:
            L.append(f"  Recorrido del grafo: {rec.get('camino')}")
            for clave in ("originado_por", "verifica", "hereda_de", "causa_raiz", "reglas"):
                for paso in rec.get(clave) or []:
                    datos = {k: v for k, v in paso.items() if k != "relacion"}
                    L.append(f"    {paso.get('relacion')}  {a_json(datos)}")
    for n in informe.get("no_evaluado") or []:
        L.append(f"\nNo evaluado: {n['descripcion']} — {n['motivo']}")
    L.append(f"\nExplicación generada:\n{informe['explicacion']}")
    if informe.get("fundamento"):
        L.append(informe["fundamento"])
    v = informe.get("verificacion") or {}
    if v:
        L.append(f"Verificación: {len(v.get('intentos', []))} intento(s); fallas finales: "
                 f"{(v.get('intentos') or [{}])[-1].get('fallas') or 'ninguna'}; "
                 f"respaldo determinístico: {'sí' if v.get('respaldo_deterministico') else 'no'}")
    return "\n".join(L)
