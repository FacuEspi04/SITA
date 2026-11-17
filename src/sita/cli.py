"""Interfaz de línea de comandos de SITA (punto de entrada único: python -m sita).

  python -m sita                          modo conversación (recuerda tu legajo en la sesión; «auditar» muestra la traza)
  python -m sita -q "texto" [--auditar]   una consulta
  python -m sita --demo [--casos E2E-01 ROB-02] [--auditar]   casos de prueba integrados y de robustez
  python -m sita --traza 8e8986b3e7c7 [--json]   audita una respuesta guardada en el log, sin llamar al LLM
  python -m sita --verificar              esquema del grafo + EXPLAIN de las 17 plantillas + resumen por estudiante (sin LLM)
  python -m sita --verificar-difuso       M3: inferencia Mamdani en Neo4j vs PG2 vs motor de PI3 (sin LLM)
  python -m sita --exportar               escribe cypher/consultas_pg3.cypher, cypher/auditoria.cypher y prompts/ (sin conexión)
  python -m sita --servidor [--puerto N]  levanta la API REST y la interfaz web (FastAPI + uvicorn)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .config import RAIZ
from .textos import a_json

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

if os.name == "nt":  # habilita los colores ANSI en CMD/PowerShell de Windows 10+ (si no, se ven como «←[1;36m»)
    os.system("")
_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def c(cod: str, s: str) -> str:
    return f"\033[{cod}m{s}\033[0m" if _COLOR else s


def titulo(n, s):
    print(c("1;36", f"\n[{n}] {s}"))


def mostrar(traza: dict, detalle: bool = True) -> None:
    titulo(1, "Consulta del estudiante")
    print("  " + traza["entrada"])
    if not detalle:
        print(c("1", "\n" + traza["respuesta_completa"]))
        return
    enr = traza.get("enrutamiento") or {}
    titulo(2, "Enrutamiento (LLM + prompt maestro -> JSON validado con Pydantic)")
    print("  " + a_json(enr.get("validado") or enr.get("error")))
    for corr in (enr.get("correcciones") or []) + (traza.get("correcciones") or []):
        print(c("33", f"  corrección: {corr}"))
    if traza.get("estudiante"):
        extra = " (de la sesión)" if traza.get("estudiante_de_sesion") else ""
        print(f"  estudiante: {traza['estudiante']['nombre']} ({traza['estudiante']['legajo']}){extra}")
    plan = traza.get("plan_ejecucion")
    if plan:
        titulo(3, "Plan de ejecución (orden M1 -> M4, cortes y enriquecimiento)")
        ctx = traza.get("contexto") or {}
        print(f"  consulta {ctx.get('consulta')} · estado {ctx.get('estado')}"
              + (f" · corte en {plan['corte_en']}" if plan.get("corte_en") else "")
              + f" · confiabilidad {(ctx.get('confiabilidad') or {}).get('etiqueta')}")
        print(f"  ejecutados: {plan['ejecutados']} · no evaluados: {plan['no_evaluados']}")
        print(f"  enriquecimiento: {traza.get('enriquecimiento') or 'ninguno'}")
    if traza.get("consultas_ejecutadas"):
        titulo(4, "Consultas Cypher ejecutadas (solo lectura)")
        for q in traza["consultas_ejecutadas"]:
            if not q["consulta"].startswith("CAT_"):
                print(f"  - {q['consulta']}  {a_json(q['parametros'])}")
    if traza.get("secciones"):
        titulo(5, "Conocimiento recuperado por submódulo")
        for s in traza["secciones"]:
            estado = "ok" if s["estado"] == "ok" else f"sin datos: {s['mensaje']}"
            print(f"  {s['modulo']} · {s['intencion']} · {s['tipo_decision']} · {s['origen']} · {estado}"
                  + (f" · reglas {', '.join(s['reglas'])}" if s.get("reglas") else ""))
    v = traza.get("verificacion")
    if v:
        titulo(6, "Verificación de la explicación")
        for i, it in enumerate(v["intentos"], 1):
            print(f"  intento {i}: " + ("OK" if not it["fallas"] else c("33", a_json(it["fallas"]))))
        if v.get("respaldo_deterministico"):
            print(c("33", "  se usó la respuesta de respaldo determinística"))
    titulo(7, f"Respuesta · {traza.get('segundos')} s · {traza.get('flujo')}")
    print(c("1", traza["respuesta_completa"]))


def _orq():
    from .servicios import crear
    cfg, kb, orq = crear()
    print(f"Neo4j: {cfg.neo4j_uri} ({kb.transporte}) · LLM: {orq.llm.nombre}")
    return cfg, kb, orq


def cmd_exportar() -> None:
    from .modulos import m1, todas_las_plantillas
    from .prompts import PROMPT_ENRUTADOR, prompt_explicacion
    d = RAIZ / "cypher"
    d.mkdir(exist_ok=True)
    with (d / "consultas_pg3.cypher").open("w", encoding="utf-8") as f:
        f.write("// SITA · PG3 · Grupo 19 — Lista blanca de consultas del asistente (solo lectura).\n"
                "// Parámetros: $legajo (texto), $codigo, $codigos, $alcance, $filtro, $horizonte_meses, $horas_hipoteticas.\n"
                "// Generado con: python -m sita --exportar\n\n")
        for qid, cy in todas_las_plantillas().items():
            f.write(f"// {'=' * 96}\n// {qid}\n// {'=' * 96}\n{cy.strip()}\n;\n\n")
    with (d / "auditoria.cypher").open("w", encoding="utf-8") as f:
        f.write("// Auditoría del dictamen de Lucía (48115) sobre Inteligencia Artificial (código 31), caso E2E-01.\n"
                "// Pegar en Neo4j Browser / Aura Query. Primero los parámetros, después cada consulta.\n\n"
                ":params {legajo: '48115', codigo: 31, alcance: 'cursar'}\n\n"
                "// 1) Recorrido tabular: qué relación se recorrió para cada condición y con qué estado\n"
                f"{m1.M1_RECORRIDO.strip()}\n;\n\n// 2) Subgrafo para la captura del video\n"
                f"{m1.M1_RECORRIDO_VISUAL.strip()}\n;\n")
    p = RAIZ / "prompts"
    p.mkdir(exist_ok=True)
    (p / "prompt_maestro_enrutador.txt").write_text(PROMPT_ENRUTADOR, encoding="utf-8")
    (p / "prompt_maestro_explicacion.txt").write_text(prompt_explicacion(False), encoding="utf-8")
    print(f"Exportado: {d / 'consultas_pg3.cypher'}, {d / 'auditoria.cypher'}, {p}/")


def cmd_verificar(kb) -> bool:
    from .modulos import todas_las_plantillas
    ok = True
    etiquetas = {r["label"] for r in kb.leer("diag", "CALL db.labels() YIELD label RETURN label")}
    rels = {r["t"] for r in kb.leer("diag", "CALL db.relationshipTypes() YIELD relationshipType AS t RETURN t")}
    requeridas_e = ["Estudiante", "Consulta", "Periodo", "Asignatura", "Correlatividad", "Dictamen", "Bloqueo",
                    "BloqueoHeredado", "HabilitacionCursar", "Regla", "ReglaDifusa",
                    "HistoriaAcademica", "EstadoAcademico", "Regularidad", "ConfiabilidadDato", "Advertencia",
                    "SolicitudDatos", "EvaluacionCarga", "TamanioAdmisible", "RiesgoSobrecarga", "Ajuste",
                    "ConjuntoCandidato", "ItemCandidato", "ResultadoRiesgo", "RiesgoAtraso", "TerminoLinguistico",
                    "SistemaDifuso", "Medicion", "ParametroModelo", "PlanCursado", "AdecuacionPlan", "Conclusion"]
    requeridas_r = ["SOLICITADA_POR", "PRODUCE", "SOBRE", "ORIGINADO_POR", "VERIFICA", "APUNTA_A", "HEREDA_DE",
                    "CAUSA_RAIZ", "JUSTIFICADO_POR", "POSEE", "REGISTRA", "REFIERE_A", "EXIGE", "REFERIDA_A",
                    "EVALUA", "CONTIENE", "DETERMINA", "REDUCE", "INCLUYE", "EXCLUYE", "TIENE_PRIORIDAD",
                    "ESTIMA", "IDENTIFICA", "ACTIVA", "PERTENECE", "ALIMENTA", "SUSTENTADO_POR", "INVALIDA", "MIDE"]
    print("Etiquetas y relaciones que usan las plantillas:")
    for nombre, presentes, req in (("etiquetas", etiquetas, requeridas_e), ("relaciones", rels, requeridas_r)):
        faltan = [x for x in req if x not in presentes]
        ok &= not faltan
        print(f"  {'OK   ' if not faltan else 'FALTA'} {len(req) - len(faltan)}/{len(req)} {nombre}"
              + (f" · faltan: {faltan}" if faltan else ""))
    print("Sintaxis y plan de cada plantilla (EXPLAIN contra la base):")
    params = {"legajo": "00000", "codigo": 0, "codigos": [0], "alcance": "cursar", "filtro": "todas",
              "horizonte_meses": None, "horas_hipoteticas": None}
    for qid, cy in todas_las_plantillas().items():
        try:
            kb.leer("EXPLAIN", "EXPLAIN " + cy, **params)
            print(f"  OK    {qid}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  ERROR {qid}: {str(exc)[:200]}")
    print("Estado de la consulta por estudiante:")
    from .modulos import transversal
    for e in kb.leer("CAT_ESTUDIANTES", "MATCH (e:Estudiante) RETURN toString(e.legajo) AS legajo, e.nombre AS nombre ORDER BY nombre"):
        ctx = transversal.contexto(kb, e["legajo"]) or {}
        print(f"  {e['legajo']} {e['nombre']:<20} {str(ctx.get('estado')):<10} corte={ctx.get('corte_en')} "
              f"confiabilidad={(ctx.get('confiabilidad') or {}).get('etiqueta')}")
    print("Resultado:", "OK" if ok else "HAY PROBLEMAS")
    return ok


def cmd_verificar_difuso(kb) -> bool:
    from .modulos.m3 import verificar_difuso
    filas = verificar_difuso(kb)
    print(f"{'Legajo / estudiante':28} {'Q5 en Neo4j':>11} {'PG2':>9} {'Motor PI3':>10} {'|Δ| máx':>9}")
    for f in filas:
        if f.get("error"):
            print(f"{f['legajo']:28} {f['error']}")
            continue
        print(f"{f['legajo'] + ' ' + f['nombre']:28} {f['neo4j_q5']:11.6f} {f['pg2']:9.6f} {f['motor_pi3']:10.6f} "
              f"{f['delta_max']:9.2e} {'✓' if f['ok'] else '✗'}")
    ok = all(f.get("ok") for f in filas)
    print("Resultado:", "la inferencia en Neo4j reproduce PG2 y el motor de PI3" if ok else "HAY DIFERENCIAS")
    (RAIZ / "logs").mkdir(exist_ok=True)
    (RAIZ / "logs" / "verificacion_difusa.json").write_text(a_json(filas, 1), encoding="utf-8")
    return ok


def cmd_traza(traza_id: str, como_json: bool) -> int:
    """Reproduce la auditoría de una respuesta guardada en el log JSONL: no vuelve a llamar al modelo de lenguaje."""
    from .config import Config
    from .servicios import crear
    from .trazabilidad import auditar as aud, formatear
    log = Config.desde_entorno().log_path
    traza = None
    if log.exists():
        with log.open(encoding="utf-8") as f:
            for linea in f:
                if traza_id in linea:
                    t = json.loads(linea)
                    if t.get("traza_id") == traza_id:
                        traza = t
    if traza is None:
        print(f"No encuentro la traza {traza_id} en {log}.")
        return 1
    if como_json:
        print(a_json(traza, 1))
        return 0
    if not traza.get("secciones"):
        print(f"Consulta: {traza.get('entrada')}\nRespuesta: {traza.get('respuesta')}\n"
              "Esta respuesta no consultó la base (mensaje fijo o aclaración).")
        return 0
    necesita_kb = any(s.get("consulta_id") == "M1_DICTAMEN" for s in traza["secciones"])
    kb = crear(con_llm=False)[1] if necesita_kb else None  # solo el recorrido de M1 vuelve a leer el grafo
    try:
        print(formatear(aud(traza, kb)))
    finally:
        if kb:
            kb.cerrar()
    return 0


def cmd_demo(orq, ids: list[str] | None, auditar: bool, pausa: float) -> None:
    from .casos import CASOS, REPREGUNTA
    from .trazabilidad import auditar as aud, formatear
    casos = [x for x in CASOS if not ids or x["id"] in ids]
    if not ids or "MEM-01" in ids:
        idx = next((i for i, x in enumerate(casos) if x["id"] == "E2E-01"), None)
        if idx is not None:
            casos.insert(idx + 1, REPREGUNTA)
    resultados = []
    for k, caso in enumerate(casos):
        print(c("1;35", "\n" + "═" * 100 + f"\n{caso['id']} · {caso['tipo']} · esperado: {caso['esperado']}\n" + "═" * 100))
        sesion = "demo-E2E-01" if caso["id"] in ("E2E-01", "MEM-01") else f"demo-{caso['id']}"
        traza = orq.procesar(caso["texto"], sesion_id=sesion)
        mostrar(traza)
        consultados = set(traza.get("modulos_consultados") or [])
        no_eval = {n["intencion"] for n in traza.get("no_evaluado") or []}
        cumple = set(caso["modulos_minimos"]) <= consultados and set(caso.get("no_evaluados", [])) <= no_eval
        print(c("32" if cumple else "31", f"\n  {'✓' if cumple else '✗'} módulos esperados {caso['modulos_minimos']} · "
                                          f"consultados {sorted(consultados)}"))
        if auditar and traza.get("secciones"):
            print("\n" + formatear(aud(traza, orq.kb)))
        resultados.append({"id": caso["id"], "texto": caso["texto"], "esperado": caso["esperado"],
                           "modulos_minimos": caso["modulos_minimos"], "modulos_consultados": sorted(consultados),
                           "cumple_modulos": cumple, "traza_id": traza["traza_id"], "flujo": traza.get("flujo"),
                           "respuesta": traza["respuesta_completa"], "segundos": traza.get("segundos"),
                           "verificacion_final": ((traza.get("verificacion") or {}).get("intentos") or [{}])[-1].get("fallas"),
                           "respaldo": (traza.get("verificacion") or {}).get("respaldo_deterministico")})
        if pausa and k < len(casos) - 1:
            time.sleep(pausa)
    salida = RAIZ / "logs" / "resultados_demo.json"
    salida.parent.mkdir(exist_ok=True)
    salida.write_text(a_json(resultados, 2), encoding="utf-8")
    ok = sum(r["cumple_modulos"] for r in resultados)
    print(c("1", f"\n{ok}/{len(resultados)} casos consultaron los submódulos esperados · detalle en {salida}"))


def main(argv=None) -> None:
    from .kb import ErrorBase
    from .llm import ErrorLLM
    try:
        _main(argv)
    except (ErrorBase, ErrorLLM) as exc:
        print(f"Configuración incompleta: {exc}\nRevisá el archivo .env (ver .env.example).", file=sys.stderr)
        sys.exit(2)


def _main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="sita", description="SITA · asistente unificado (PG3, Grupo 19)")
    ap.add_argument("-q", "--consulta", help="procesa una sola consulta")
    ap.add_argument("--demo", action="store_true", help="corre los casos de prueba")
    ap.add_argument("--casos", nargs="*", metavar="ID", help="con --demo: solo esos casos (E2E-01, ROB-02, MEM-01...)")
    ap.add_argument("--auditar", action="store_true", help="muestra la trazabilidad completa de cada respuesta")
    ap.add_argument("--resumido", action="store_true", help="muestra solo la respuesta")
    ap.add_argument("--json", action="store_true", help="con -q: imprime la traza completa en JSON")
    ap.add_argument("--traza", metavar="ID", help="audita una respuesta ya guardada en el log (no llama al LLM)")
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--verificar-difuso", action="store_true")
    ap.add_argument("--exportar", action="store_true")
    ap.add_argument("--servidor", action="store_true")
    ap.add_argument("--puerto", type=int, default=8000)
    a = ap.parse_args(argv)

    if a.exportar:
        return cmd_exportar()
    if a.servidor:
        import uvicorn
        uvicorn.run("sita.app:app", host="0.0.0.0", port=a.puerto)
        return
    if a.traza:
        sys.exit(cmd_traza(a.traza, a.json))
    if a.verificar or a.verificar_difuso:
        from .servicios import crear
        cfg, kb, _ = crear(con_llm=False)
        try:
            ok = cmd_verificar(kb) if a.verificar else True
            ok = (cmd_verificar_difuso(kb) if a.verificar_difuso else True) and ok
        finally:
            kb.cerrar()
        sys.exit(0 if ok else 1)

    from .trazabilidad import auditar as aud, formatear
    cfg, kb, orq = _orq()
    try:
        if a.demo:
            cmd_demo(orq, a.casos, a.auditar, cfg.llm_pausa)
        elif a.consulta:
            traza = orq.procesar(a.consulta)
            if a.json:
                print(a_json(traza, 1))
            else:
                mostrar(traza, detalle=not a.resumido)
                if a.auditar and traza.get("secciones"):
                    print("\n" + formatear(aud(traza, kb)))
        else:
            print("SITA · asistente de trayectoria académica. Escribí tu consulta («auditar» para ver la traza de la "
                  "última respuesta, «salir» para terminar).")
            ultima = None
            while True:
                try:
                    t = input(c("1;32", "\nVos › ")).strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if t.lower() in ("salir", "exit", "quit"):
                    break
                if t.lower() == "auditar":
                    print(formatear(aud(ultima, kb)) if ultima and ultima.get("secciones") else "No hay una respuesta para auditar.")
                    continue
                if t:
                    ultima = orq.procesar(t, sesion_id="cli")
                    mostrar(ultima, detalle=not a.resumido)
    finally:
        kb.cerrar()
