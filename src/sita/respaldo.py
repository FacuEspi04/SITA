"""Respuesta de respaldo determinística (idea de M3): si el LLM no pasa los controles graves después
de una reescritura, se responde con plantillas fijas escritas sobre los mismos datos. No inventa nada
y no depende del modelo."""
from __future__ import annotations

import json
import re

from .textos import fecha_ar, fmt_num


def _lista(xs) -> str:
    xs = [str(x) for x in xs if x]
    return xs[0] if len(xs) == 1 else (", ".join(xs[:-1]) + " y " + xs[-1] if xs else "")


def _m1(s: dict) -> list[str]:
    r = s["resultado"]
    if "alcance_consultado" in r:  # dictamen
        asig = (r.get("asignatura") or {}).get("nombre", "esa asignatura")
        alcance = r.get("alcance_consultado", "cursar")
        d = r.get("dictamen")
        if not d:
            estado = (r.get("asignatura") or {}).get("estado_en_historia", "sin dato")
            return [f"No tengo un dictamen registrado para {alcance} {asig}; en tu historia figura como «{estado}»."]
        if str(d.get("tipo", "")).startswith("Bloqueo"):
            causas = [c.get("causa") or f"falta {c.get('asignatura')}" for c in d.get("causas") or []]
            out = [f"Todavía no podés {alcance} {asig}: {_lista(causas)}."]
            raices = [c.get("asignatura") for c in d.get("causa_raiz") or []]
            if raices:
                out.append(f"Lo primero que hay que destrabar es {_lista(raices)}.")
            cond = [c.get("asignatura") for c in d.get("causas") or [] if c.get("condicionada")]
            if cond:
                out.append(f"Parte de esto depende de cómo termines {_lista(cond)}, que estás cursando.")
            return out
        verif = [c.get("asignatura") for c in d.get("condiciones_verificadas") or []]
        return [f"Podés {alcance} {asig}" + (f": cumplís sus correlativas ({_lista(verif)})." if verif else ".")]
    if "dictamenes" in r:  # habilitaciones
        hab = [x.get("asignatura") for x in r.get("dictamenes", []) if x.get("dictamen") == "habilitada"]
        blo = [f"{x.get('asignatura')} ({_lista(x.get('causas') or [])})" for x in r.get("dictamenes", [])
               if x.get("dictamen") == "bloqueada"]
        out = [f"Podés cursar {_lista(hab)}." if hab else "No tenés asignaturas habilitadas registradas para el período."]
        if blo:
            out.append(f"Todavía no podés cursar: {_lista(blo)}.")
        return out
    if "regularidades" in r:
        return [f"{g.get('asignatura')}: regularidad {'vigente' if g.get('vigente') else 'vencida'}"
                f" (vence el {fecha_ar(g.get('fecha_vencimiento'))})." for g in r.get("regularidades") or []] \
            or ["No tenés regularidades registradas para esa consulta."]
    if "historia" in r:
        conf = r.get("confiabilidad") or {}
        inconsistencias = (r.get("historia") or {}).get("inconsistencias")
        if inconsistencias:
            out = [f"Tu consulta quedó detenida porque tu historia académica tiene {inconsistencias} registros que se "
                   "contradicen; mientras no se corrijan, el sistema no emite dictámenes."]
        elif (r.get("factores_confiabilidad") or {}).get("explicacion"):
            out = [r["factores_confiabilidad"]["explicacion"]]
        elif conf.get("etiqueta"):
            out = [f"Tu historia académica tiene una confiabilidad {conf['etiqueta']}."]
        else:
            out = ["Tu historia académica no tiene una confiabilidad calculada."]
        for sd in r.get("solicitudes_de_datos") or []:
            faltan = [str(f).strip().rstrip(":").strip() for f in sd.get("faltantes") or []]
            if faltan:
                out.append(f"Para continuar hace falta: {_lista(faltan)}.")
        out.append("Cuando se actualice tu historia, podés volver a consultar.")
        return out
    return []


def _m3(s: dict) -> list[str]:
    r = s["resultado"]
    out = []
    if "asignaturas" in r:
        for a in r["asignaturas"]:
            out.append(f"{a.get('asignatura')}: {a.get('descendientes')} asignaturas dependen de ella en el plan; "
                       f"{'es' if a.get('es_llave') else 'no es'} una materia llave.")
        return out
    ra = r.get("riesgo_atraso")
    if ra:
        if r.get("escenario_hipotetico"):
            reg = r.get("riesgo_registrado_en_PG2") or {}
            out.append(f"En la simulación, tu riesgo de atraso sería {ra.get('etiqueta')}; el registrado hoy es "
                       f"{reg.get('etiqueta', 'sin dato')}. Es una simulación, no tu situación registrada.")
        else:
            out.append(f"Tu riesgo de atraso es {ra.get('etiqueta')}.")
        if (r.get("causa_del_riesgo") or {}).get("explicacion"):
            out.append(r["causa_del_riesgo"]["explicacion"])
    arr = [a.get("asignatura") for a in r.get("arrastres") or []]
    if arr:
        out.append(f"Arrastrás {_lista(arr)}.")
    for u in r.get("urgencias") or []:
        out.append(f"La regularidad de {u.get('asignatura')} vence el {fecha_ar(u.get('vencimiento'))}.")
    for g in r.get("regularidades") or []:
        out.append(f"{g.get('asignatura')}: vence el {fecha_ar(g.get('vencimiento'))}.")
    return out


def _m4(s: dict) -> list[str]:
    r = s["resultado"]
    out = []
    if "plan" in r:
        items = [f"{i.get('orden')}. {i.get('alcance')} {i.get('asignatura')}" for i in r.get("plan") or []]
        if items:
            out.append("El plan recomendado es:\n" + "\n".join(items))
        adec = r.get("adecuacion_del_plan_M4") or {}
        if adec.get("etiqueta"):
            out.append(f"La adecuación del plan es {adec['etiqueta']}.")
        for x in r.get("excluidos") or []:
            out.append(f"{x.get('asignatura')} sigue habilitada, pero el plan no la recomienda este período "
                       f"(causa: {x.get('causa')}).")
    for i in r.get("items") or []:
        if i.get("decision") == "excluida":
            out.append(f"El plan no recomienda {i.get('asignatura', 'esa asignatura')} este período "
                       f"(causa: {i.get('causa')}), aunque no es una prohibición.")
        else:
            out.append(f"El plan incluye {i.get('asignatura', 'esa asignatura')} en el lugar {i.get('orden')}.")
    return out


def _corte(s: dict) -> list[str]:
    r = s["resultado"]
    return [f"No pude evaluar tu consulta completa: {r.get('motivo', 'faltan datos')}."
            + (f" Hace falta: {_lista(r.get('faltantes') or [])}." if r.get("faltantes") else "")]


def respaldo(paquete: dict) -> str:
    lineas: list[str] = []
    for s in paquete.get("secciones", []):
        if "sin_datos" in s:
            lineas.append(s["sin_datos"])
            continue
        mod = s.get("modulo")
        if mod == "M1":
            lineas += _m1(s)
        elif mod == "M2":
            # La lectura guiada es para el LLM: en el respaldo se quita el detalle de reglas («…la de mayor
            # activación es RS1»), que mostraba ids internos al estudiante (corrida en Render, 17/11).
            lineas += [re.sub(r"\s*Se activaron \d+ reglas difusas[^.]*\.", "", x)
                       for x in s["resultado"].get("lectura_guiada") or []]
        elif mod == "M3":
            lineas += _m3(s)
        elif mod == "M4":
            lineas += _m4(s)
        elif mod == "X":
            lineas += _corte(s)
    parcial = paquete.get("escenario_parcial")
    if parcial and parcial.get("aclaracion"):
        lineas.append(parcial["aclaracion"])
    for n in paquete.get("no_evaluado", []):
        lineas.append(f"No evalué {n.get('descripcion')}: {n.get('motivo')}")
    if '"candidata"' in json.dumps(paquete.get("secciones"), ensure_ascii=False) or \
            '"firme_bajo_supuesto"' in json.dumps(paquete.get("secciones"), ensure_ascii=False):
        lineas.append("Algunos criterios usados todavía están en revisión; conviene confirmarlos con el asesor académico.")
    ctx = paquete.get("contexto") or {}
    conf = (ctx.get("confiabilidad") or {}).get("etiqueta")
    if ctx.get("reserva") or conf in ("media", "baja"):
        lineas.append("Tu historia académica puede no estar al día, así que conviene confirmarlo con el asesor académico.")
    return "\n".join(x for x in lineas if x) or "No tengo datos suficientes para responder; consultalo con el asesor académico."


def aviso_reserva(contexto: dict | None) -> str | None:
    ctx = contexto or {}
    conf = ctx.get("confiabilidad") or {}
    if not (ctx.get("reserva") or conf.get("etiqueta") in ("media", "baja")):
        return None
    valor = f" ({fmt_num(conf['valor'])} en una escala de 0 a 1)" if conf.get("valor") is not None else ""
    return (f"Tu historia académica tiene una confiabilidad {conf.get('etiqueta', 'con reserva')}{valor}: puede no estar "
            "al día, así que conviene que lo confirmes con el asesor académico.")
