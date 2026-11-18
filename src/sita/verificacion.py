"""Verificación de la respuesta del LLM contra el paquete de conocimiento recuperado.

Reúne los controles de los cuatro PI4 y agrega los controles SEMÁNTICOS que faltaban (devolución de
la cátedra: «verificar la correspondencia entre la explicación generada y todas las condiciones
normativas del caso»). Cada control nuevo está pensado contra un error real observado en PI4:

  cobertura_normativa ..... la explicación tiene que nombrar TODAS las condiciones del dictamen (M1)
  magnitudes_cruzadas ..... «confiabilidad 0,79» cuando 0,79 era la adecuación (M2, caso Ana)
  causa_de_exclusion ...... «por limitaciones de capacidad» cuando la causa era el tope (M4, caso Martina)
  instituciones_inventadas  «consultá con Bedelía», que no figuraba en el resultado (M3, caso E4)
  causa_de_corte .......... «quedó sin evaluar por la habilitación normativa» cuando el corte era X-01 (E2E-05)
  desglose_incompleto ..... desglose de la carga que no suma el total: omitía las anuales en curso (E2E-02/04)
  escenario_parcial ....... con horas hipotéticas, carga y plan se mostraban como recalculados (E2E-04)
  causa_de_capacidad ...... «capacidad de 25 h porque se restó un ajuste por sobrecarga» (el ajuste recorta el plan)
  certeza_inventada ....... «el riesgo tiene un nivel de certeza alto… podés considerarlo bastante fiable» (Martina)
  factor_de_confiabilidad . «la completitud es solo 0,92» cuando es alta y la causa es la antigüedad (Sofía)
  causa_del_riesgo ........ «el riesgo se apoya en la ruta crítica y los cuellos de botella» (lo produce el arrastre)

Los controles se dividen en GRAVES (si persisten tras la reescritura, se usa la respuesta de respaldo
determinística) y LEVES (forma: se pide reescritura y, si persisten, se registran).
"""
from __future__ import annotations

import json
import re

from .textos import (RE_CORRELATIVIDAD, RE_REGLA, fmt_num, ids_de_regla, limpiar_texto, norm, recorrer, sin_acentos)

GRAVES = {"vacia", "numeros_sin_respaldo", "ids_sin_respaldo", "tipo_de_decision", "orden_de_destrabe",
          "cobertura_normativa", "causa_de_exclusion", "magnitudes_cruzadas", "instituciones_inventadas",
          "porcentaje_o_probabilidad", "idioma", "sin_dictamen", "requisito_para_rendir", "escenario_hipotetico",
          "etiqueta_inventada", "llave_inventada", "riesgo_negado", "causa_de_corte", "desglose_incompleto",
          "escenario_parcial", "causa_de_capacidad", "certeza_inventada", "factor_de_confiabilidad",
          "causa_del_riesgo"}

INSTRUCCION = {
    "vacia": "escribí la respuesta completa",
    "numeros_sin_respaldo": "quitá estos números, que no están en los datos",
    "ids_sin_respaldo": "quitá estos identificadores de regla, que no figuran en los datos",
    "ids_en_cuerpo": "no escribas identificadores de reglas ni de correlatividades: contá qué significan",
    "correlatividad_como_regla": "estos códigos son correlatividades, no reglas",
    "letras_sueltas": "nombrá las materias por su nombre, nunca con X o Y",
    "orden_de_destrabe": "el primer paso tiene que ser la materia de causa_raiz",
    "tipo_de_decision": "una habilitación o una exclusión del plan no es un bloqueo; solo un bloqueo permite decir «no podés»",
    "cobertura_normativa": "nombrá todas las condiciones del dictamen, con el verbo correcto (regularizar/aprobar)",
    "causa_de_exclusion": "usá la causa exacta de la exclusión que figura en los datos",
    "magnitudes_cruzadas": "cada valor tiene que ir con su magnitud (no mezcles confiabilidad, adecuación y riesgos)",
    "instituciones_inventadas": "no menciones oficinas, trámites ni sistemas que no figuran en los datos",
    "porcentaje_o_probabilidad": "los grados no son probabilidades ni porcentajes",
    "jerga": "no uses términos internos del sistema ni nombres de campos",
    "voseo": "usá voseo (tenés, podés), nunca tú ni usted",
    "idioma": "escribí todo en español rioplatense",
    "reserva_omitida": "decí que la historia académica puede no estar al día",
    "sin_dictamen": "no hay dictamen: no juzgues si puede cursar; decí el estado que figura en la historia",
    "requisito_para_rendir": "para rendir el final hay que APROBAR la correlativa (no alcanza con regularizarla)",
    "escenario_hipotetico": "aclará que es una simulación y comparala con el riesgo registrado (de X a Y)",
    "riesgo_negado": "riesgo bajo no es ausencia de riesgo: decí «tu riesgo de atraso es bajo»",
    "llave_inventada": "solo las asignaturas con es_llave verdadero son «llave»; las demás nombralas sin ese adjetivo",
    "etiqueta_inventada": "usá solo las etiquetas (alta, media, baja…) que figuran en los datos; si no hay, decí que no hay dato",
    "causa_de_corte": ("el corte se debe a la calidad de los datos de la historia académica (datos viejos, contradictorios "
                       "o poco confiables), no a la habilitación ni a las correlativas"),
    "desglose_incompleto": ("si desglosás la carga, incluí todos sus componentes (también las horas de asignaturas "
                            "anuales en curso, nombrando cada una) para que la suma dé el total"),
    "escenario_parcial": ("EMPEZÁ la respuesta con la aclaración, antes de nombrar materias: con esas horas solo se "
                          "simuló el riesgo de atraso; la carga, la capacidad, el plan y la cantidad de materias son los "
                          "de tu situación registrada y no se recalcularon. No abras con «podés llevar N materias»"),
    "causa_de_capacidad": ("la capacidad es la dedicación sostenible menos las horas de trabajo; el ajuste por sobrecarga "
                           "recorta materias del plan, no la capacidad"),
    "certeza_inventada": ("un grado difuso no es un nivel de certeza ni de fiabilidad; la confiabilidad es la calidad de "
                          "los datos de la historia, no la exactitud del cálculo"),
    "factor_de_confiabilidad": ("atribuí la confiabilidad baja solo a los factores desfavorables; un factor favorable "
                                "(p. ej. completitud alta) no es la causa"),
    "causa_del_riesgo": ("el riesgo de atraso lo produce lo que dice causa_del_riesgo (p. ej. la criticidad del arrastre); "
                         "la ruta crítica y los cuellos de botella no son entradas de ese cálculo"),
}

JERGA = ["json", "neo4j", "cypher", "grafo", "traza", "lectura guiada", "base de datos", "seccion", "modulo m"]
INSTITUCIONES = ["bedel", "secretari", "departamento de alumnos", "direccion de carrera", "mesa de entradas",
                 "sysacad", "autogestion", "tramite", "oficina", "coordinador", "director", "area de registro",
                 "registro academico", "alumnado", "departamento", "personal administrativo"]
RE_TUTEO = re.compile(r"\b(tienes|puedes|debes|quieres|necesitas|usted|tú)\b", re.I)
RE_PORTUGUES = re.compile(r"[ãõç]|\b(você|vocês|não|também|então|ainda|isso|porém|são|matéria|obrigad[oa])\b", re.I)
RE_JERGA_INTERNA = re.compile(r"\b(Q-[A-Z0-9-]+|ConfiabilidadDato|contexto\s*M1|bajo\s+supuesto)\b"
                              r"|\balcance:?\s+(cursar|rendir)\b"
                              r"|\betiqueta:?\s+(alt|medi|baj)[oa]\b"
                              r"|\(M[1-4]\)"
                              r"|\b(regla|criterio|estado|condicion)\s+(es\s+|esta\s+)?candidat\w*", re.I)
RE_INGLES = re.compile(r"\b(the|you|your|cannot|with|because|and)\b", re.I)
RE_NEGACION = re.compile(r"\b(no|ni|sin|tampoco|ningun\w*)\b")
RE_EXCLUSION = re.compile(r"(no la (incluye|recomienda|sugiere|propone)|exclu\w*|qued\w* (afuera|fuera)|fuera del plan|no entra)")
CAUSAS = {"capacidad": ("capacidad",), "tope": ("tope",), "empate": ("empate", "empat"), "oferta": ("oferta", "no se dicta")}
RE_COMPARACION = re.compile(r"(mayor|mas alto|superior)\s+(grado|prioridad|rango|criticidad)|mas (llave|importantes|prioritari)")
MAGNITUDES = {
    "confiabilidad": ("confiabilidad",),
    "adecuacion": ("adecuacion",),
    "riesgo de atraso": ("riesgo_atraso", "riesgo_de_atraso", "riesgo_registrado"),
    "riesgo de sobrecarga": ("riesgo_sobrecarga",),
    "urgencia": ("urgencia",),
    "grado de llave": ("grado_llave",),
}


# ------------------------------------------------------------------ auxiliares
def _secciones(paquete: dict) -> list[dict]:
    return [s for s in paquete.get("secciones", []) if isinstance(s.get("resultado"), dict)]


def _oraciones(texto: str) -> list[str]:
    return [o for o in re.split(r"(?<=[.!?;])\s+|\n+", texto) if o.strip()]


def _dictamenes_m1(paquete: dict) -> list[dict]:
    out = []
    for s in _secciones(paquete):
        r = s["resultado"]
        if s.get("modulo") == "M1" and isinstance(r.get("dictamen"), dict) and isinstance(r.get("asignatura"), dict):
            out.append({"asignatura": r["asignatura"].get("nombre", ""), "alcance": r.get("alcance_consultado", "cursar"),
                        **r["dictamen"]})
    return out


def _excluidas_m4(paquete: dict) -> list[dict]:
    out = []
    for s in _secciones(paquete):
        if s.get("modulo") != "M4":
            continue
        r = s["resultado"]
        for x in r.get("excluidos") or []:
            out.append(x)
        for i in r.get("items") or []:
            if i.get("decision") == "excluida":
                out.append(i)
    return out


def _numeros_permitidos(paquete: dict) -> list[float]:
    base: set[float] = set()
    for _, v in recorrer(paquete):
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            base.add(abs(float(v)))
        elif isinstance(v, str):
            for n in re.findall(r"\d+(?:[.,]\d+)?", v):
                base.add(float(n.replace(",", ".")))

    def longitudes(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from longitudes(v)
        elif isinstance(o, list):
            yield len(o)
            for v in o:
                yield from longitudes(v)
    base |= {float(n) for n in longitudes(paquete)}
    extra = set()
    for x in base:
        extra |= {x, float(round(x)), round(x, 1), round(x, 2)}
    return sorted(extra | {float(i) for i in range(0, 11)})


# ------------------------------------------------------------------ controles
def numeros_sin_respaldo(resp: str, paquete: dict) -> list[str]:
    texto = RE_CORRELATIVIDAD.sub(" ", RE_REGLA.sub(" ", resp))
    permitidos = _numeros_permitidos(paquete)
    malos = []
    for n in re.findall(r"\d+(?:[.,]\d+)?", texto):
        v = float(n.replace(",", "."))
        if not any(abs(v - p) <= 0.006 for p in permitidos):
            malos.append(n)
    return sorted(set(malos))


def ids_sin_respaldo(resp: str, paquete: dict) -> list[str]:
    citables = ids_de_regla(paquete.get("secciones", [])) | ids_de_regla(paquete.get("no_evaluado", [])) \
        | ids_de_regla(paquete.get("contexto", {}))
    return sorted(set(RE_REGLA.findall(resp)) - citables)


def correlatividad_como_regla(resp: str) -> list[str]:
    return sorted(set(re.findall(r"\breglas?\s+(?:de\s+correlatividad\s+)?[\"«“]?(\d{1,2}-\d{1,2}-(?:REG|APR))\b", resp, re.I)))


def orden_de_destrabe(resp: str, paquete: dict) -> list[str]:
    problemas = []
    pasos1 = [m.group(1) for m in re.finditer(r"^\s*1[.)]\s*(.+)$", resp, re.M)]
    if not pasos1:
        return []
    for d in _dictamenes_m1(paquete):
        raices = [c.get("asignatura") for c in d.get("causa_raiz") or [] if c.get("asignatura")]
        if raices and not any(norm(r) in norm(p) for r in raices for p in pasos1):
            problemas.append(f"el paso 1 debería ser destrabar {' / '.join(raices)} (causa raíz de {d['asignatura']})")
    return problemas


def _span_negado(span: str) -> bool:
    return bool(RE_NEGACION.search(span))


def tipo_de_decision(resp: str, paquete: dict) -> list[str]:
    t = sin_acentos(resp)
    problemas = []
    dictamenes = _dictamenes_m1(paquete)
    bloqueadas = {sin_acentos(d["asignatura"]) for d in dictamenes if str(d.get("tipo", "")).startswith("Bloqueo")}
    habilitadas = {sin_acentos(d["asignatura"]) for d in dictamenes if str(d.get("tipo", "")).startswith("Habilitacion")}
    excluidas = {sin_acentos(x.get("asignatura")) for x in _excluidas_m4(paquete) if x.get("asignatura")} - bloqueadas
    for a in sorted((habilitadas | excluidas) - {""}):
        if a not in t:
            continue
        for o in _oraciones(resp):
            so = sin_acentos(o)
            m = re.search(r"\bno\s+(podes|puedes|puede|podras|vas a poder)\s+(cursar|rendir)\b[^.]{0,60}" + re.escape(a), so)
            if not m:
                continue
            # la oración refuta o cita la creencia del estudiante ANTES de la negación
            # («aunque creas que no podés cursar…», «no es que no podés…»): no afirma un bloqueo.
            # La refutación posterior («…, aunque vos quisieras») no la salva.
            previo = so[:m.start()]
            if re.search(r"no (es|significa|quiere decir) que|por que|¿|en realidad|aunque|"
                         r"pensas|crees|creas|creer|dijiste|parece|preguntas", previo):
                continue
            if a in excluidas and re.search(r"\bplan\b|exclu|tope|recomend|capacidad|sugier|propon", so):
                problemas.append(f"presenta como prohibición que el plan no incluya {a}: es una recomendación, "
                                 f"la materia está habilitada")
            else:
                problemas.append(f"dice que no podés cursar/rendir {a}, que está habilitada")
            break
        for m in re.finditer(re.escape(a) + r"[^.]{0,40}?\bbloque\w*", t):
            if not _span_negado(m.group(0)):
                problemas.append(f"presenta {a} como bloqueada, y no lo está")
                break
    if habilitadas and any(a in t for a in habilitadas) and not re.search(r"habilit|\bpodes (cursar|rendir)|\bsi,? podes", t):
        problemas.append("el dictamen es una habilitación y la respuesta no lo dice")
    if bloqueadas and not re.search(r"\bno pod|bloque|todavia no|aun no", t):
        problemas.append("el dictamen es un bloqueo y la respuesta no lo dice")
    return problemas


def cobertura_normativa(resp: str, paquete: dict) -> list[str]:
    """Cada condición normativa de un bloqueo (causas, herencia y causa raíz) tiene que aparecer en la explicación."""
    tn, t = norm(resp), sin_acentos(resp)
    problemas = []
    for d in _dictamenes_m1(paquete):
        if not str(d.get("tipo", "")).startswith("Bloqueo"):
            continue
        causas, raices = d.get("causas") or [], d.get("causa_raiz") or []
        nombres = [c.get("asignatura") for c in causas + raices] + [h.get("asignatura") for h in d.get("hereda_de") or []]
        faltan = sorted({n for n in nombres if n and norm(n) not in tn})
        if faltan:
            problemas.append(f"no menciona {', '.join(faltan)}, condición del dictamen de {d['asignatura']}")
        tipos = " ".join(f"{c.get('tipo', '')} {c.get('correlatividad', '')}" for c in causas + raices).lower()
        if ("regular" in tipos or "-reg" in tipos) and "regulariz" not in t:
            problemas.append(f"una condición de {d['asignatura']} exige regularizar y la respuesta no lo dice")
        if ("aprob" in tipos or "-apr" in tipos) and "aprob" not in t:
            problemas.append(f"una condición de {d['asignatura']} exige aprobar y la respuesta no lo dice")
        if any(c.get("condicionada") for c in causas) and not re.search(r"cursando|depend|como termines", t):
            problemas.append("una causa está condicionada a una materia en curso y la respuesta no lo aclara")
    return problemas


def causa_de_exclusion(resp: str, paquete: dict) -> list[str]:
    problemas = []
    for x in _excluidas_m4(paquete):
        nombre = norm(x.get("asignatura"))
        if not nombre:
            continue
        causa = sin_acentos(x.get("causa", "")).replace("_", " ")
        reales = {k for k, terms in CAUSAS.items() if any(tt in causa for tt in terms)}
        if x.get("empate_persistente"):
            reales.add("empate")
        menciona = False
        for o in _oraciones(resp):
            on, os_ = norm(o), sin_acentos(o)
            if nombre in on and RE_EXCLUSION.search(os_):
                menciona = True
                dichas = {k for k, terms in CAUSAS.items() if any(tt in os_ for tt in terms)}
                malas = dichas - reales
                if malas:
                    problemas.append(f"atribuye la exclusión de {x.get('asignatura')} a {', '.join(sorted(malas))}; "
                                     f"la causa registrada es «{x.get('causa')}»")
                # error real (Martina): con empate persistente no hay «otras con mayor prioridad/grado de llave»
                if x.get("empate_persistente") and RE_COMPARACION.search(os_):
                    problemas.append(f"{x.get('asignatura')} quedó EMPATADA; la respuesta inventa que otras tenían "
                                     "mayor prioridad")
        if menciona and x.get("empate_persistente") and "empat" not in sin_acentos(resp):
            problemas.append(f"no dice que {x.get('asignatura')} quedó empatada con otra candidata")
    return problemas


def magnitudes_cruzadas(resp: str, paquete: dict) -> list[str]:
    t = sin_acentos(resp)
    valores: dict[str, set[float]] = {k: set() for k in MAGNITUDES}
    for ruta, v in recorrer(paquete):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        r = ruta.lower()
        for k, claves in MAGNITUDES.items():
            if any(c in r for c in claves):
                valores[k].add(abs(float(v)))
    # cualquier otra magnitud o medición nombrada en el medio corta la asociación (falso positivo real: «confiabilidad
    # baja (0,244), con una antigüedad de 18,1 meses y una completitud de 0,92»)
    otras = "|".join([re.escape(k) for k in MAGNITUDES] + ["completitud", "antiguedad", "holgura", "carga", "capacidad",
                                                           "meses", "horas", "descendientes", "valor de la"])
    problemas = []
    for k, vals in valores.items():
        if not vals:
            continue
        for m in re.finditer(re.escape(k) + r"(.{0,50}?)(\d+[.,]\d+)", t):
            hueco = m.group(1)
            if ". " in hueco or ";" in hueco or "\n" in hueco or re.search(otras, hueco):
                continue
            v = float(m.group(2).replace(",", "."))
            if not any(abs(v - x) <= 0.006 for x in vals):
                problemas.append(f"asocia {m.group(2)} a {k}, pero ese valor no es el de {k}")
    # Elipsis (corrida en Render 17/11, Juan 9 h): «El riesgo de atraso se simuló con 9 h…: bajo esa hipótesis el
    # riesgo pasa a ser alto (grado 0,77)». 0,77 era la sobrecarga; el «riesgo» suelto queda lejos del nombre completo.
    atraso = valores.get("riesgo de atraso") or set()
    if atraso:
        for o in _oraciones(resp):
            so = sin_acentos(o)
            if "riesgo de atraso" not in so or "sobrecarga" in so:
                continue
            for m in re.finditer(r"\briesgo(?! de atraso)(.{0,40}?)(\d+[.,]\d+)", so):
                if re.search(otras, m.group(1)):
                    continue
                v = float(m.group(2).replace(",", "."))
                if not any(abs(v - x) <= 0.006 for x in atraso):
                    problemas.append(f"asocia {m.group(2)} a riesgo de atraso, pero ese valor no es el de riesgo de atraso")
    return sorted(set(problemas))


RE_CORTE = re.compile(r"cort\w*|detuv\w*|deten\w*|sin evaluar|no se (evalu\w*|pudo evaluar|emit\w*)|"
                      r"qued\w* sin|no pudo aplicarse|no (pude|puedo|podemos|se puede) (evaluar|armar|calcular|darte)")
RE_CAUSA_HABILITACION = re.compile(r"\b(porque|por|debido a|ya que|a causa de|dado que)\b[^.;:]{0,50}?"
                                   r"(habilitaci\w*|correlativ\w*|no estas habilitad\w*)"
                                   r"|\b(cort|detuv|deten)\w*\s+(en|por)\s+(la|las|el)?\s*(habilitaci|correlativ)\w*")
RE_NEGADA = re.compile(r"\bno (es|son|se debe|tiene|por)\b|\bni\b|\bno\s*$")


def _corte_por_calidad_del_dato(paquete: dict) -> bool:
    ctx = paquete.get("contexto") or {}
    if ctx.get("corte_en") == "M1" and ctx.get("estado_consulta") == "cortada":
        return True
    return any("X-01" in str(n.get("motivo", "")) for n in paquete.get("no_evaluado") or [])


def causa_de_corte(resp: str, paquete: dict) -> list[str]:
    """Corrección de la cátedra (E2E-05): un corte por X-01 (calidad del dato) no se puede atribuir a la habilitación
    normativa ni a las correlatividades. Error real: «quedaron sin evaluar porque la regla que controla la
    habilitación normativa no pudo aplicarse»."""
    if not _corte_por_calidad_del_dato(paquete):
        return []
    for o in _oraciones(resp):
        so = sin_acentos(o)
        if not RE_CORTE.search(so):
            continue
        for m in RE_CAUSA_HABILITACION.finditer(so):
            previo = so[max(0, m.start() - 12):m.start()]
            if RE_NEGADA.search(m.group(0)) or RE_NEGADA.search(previo):
                continue
            return [f"atribuye el corte a la habilitación o a las correlativas («{o.strip()[:120]}»); la causa es la "
                    "calidad del dato de la historia académica (X-01)"]
    return []


def _horas_junto_a(nombre: str, horas, texto: str) -> bool:
    """¿El texto asocia esas horas a esa asignatura en la misma oración? («6,75 h de IA» / «IA, con 6,75 h»)."""
    h = re.escape(str(horas if isinstance(horas, str) else f"{horas:g}").replace(".", ","))
    n = re.escape(sin_acentos(nombre))
    return bool(re.search(h + r"\s*(h|horas)\b[^.;\n]{0,70}?" + n, texto) or
                re.search(n + r"[^.;\n]{0,70}?" + h + r"\s*(h|horas)\b", texto))


def desglose_incompleto(resp: str, paquete: dict) -> list[str]:
    """Corrección de la cátedra (E2E-02 y E2E-04): el total de carga era correcto (31 h), pero el detalle por
    asignatura sumaba 24,25 h porque omitía las 6,75 h de la anual en curso (Proyecto Final). No alcanza con que
    cada número esté en los datos: si la respuesta desglosa un total, tienen que estar todos sus componentes."""
    t = sin_acentos(resp)
    for s in _secciones(paquete):
        r = s["resultado"]
        d = r.get("desglose_carga") if s.get("modulo") == "M2" else None
        if not d:
            continue
        detalladas = [i for i in r.get("items_evaluados") or []
                      if i.get("asignatura") and i.get("horas_semanales") is not None
                      and _horas_junto_a(i["asignatura"], i["horas_semanales"], t)]
        nombres = d.get("anuales_en_curso") or []
        # Corrida en Render (17/11): «la suma de las materias que debés cursar (Tecnología…, IA, Ciencia de Datos y
        # Simulación) da 31 h»: no detalla horas, pero atribuye el total solo a las del período.
        total = re.escape(fmt_num(d["total_h"]).replace(".", ","))
        items = [sin_acentos(i.get("asignatura")) for i in r.get("items_evaluados") or [] if i.get("asignatura")]
        for o in _oraciones(resp):
            so = sin_acentos(o)
            if (sum(1 for n in items if n in so) >= 2 and re.search(r"\b" + total + r"\s*(h|horas)\b", so)
                    and re.search(r"\bsuma|\bda\b|\bdan\b|en total|totaliz", so)
                    and not re.search(r"anual|proyecto final", so) and not any(sin_acentos(n) in so for n in nombres)):
                return [f"atribuye el total de {fmt_num(d['total_h'])} h solo a las asignaturas del período: faltan las "
                        f"{fmt_num(d['anuales_en_curso_h'])} h de asignaturas anuales en curso"]
        if len(detalladas) < 2:
            continue
        if not re.search(r"anual|proyecto final", t) and not any(sin_acentos(n) in t for n in nombres):
            return [f"detalla las horas de {len(detalladas)} asignaturas pero omite las {fmt_num(d['anuales_en_curso_h'])} h "
                    f"de asignaturas anuales en curso: el detalle no suma el total de {fmt_num(d['total_h'])} h"]
        # Segunda devolución (corrida del 17/11): «6,75 h de las asignaturas anuales que continúan» suma bien, pero
        # no dice CUÁL es. Si el dato trae el nombre, el desglose tiene que nombrarla.
        faltan = [n for n in nombres if sin_acentos(n) not in t]
        if faltan:
            return [f"menciona las horas de asignaturas anuales en curso sin nombrarlas: falta {', '.join(faltan)}"]
    return []


RE_REGULARIZAR_NEGADO = re.compile(r"no (alcanza|basta|es suficiente) con regulariz|no hace falta regulariz|"
                                   r"ya (la )?(tenes |esta |estas )?regulariz|sin necesidad de regulariz")
RE_TEMA_REGISTRADO = re.compile(r"\bcarga\b|capacidad|holgura|sobrecarga|\bplan\b")
RE_NO_RECALCULADO = re.compile(r"no se (recalcul|modific|ajust|simul|volv\w* a calcular)\w*|sin recalcul\w*|"
                               r"no (cambia|cambian|varia|varian)\b|(situacion|datos?|valores?) registrad\w*|"
                               # corrida en Render (17/11): borradores correctos rechazados por estas formas
                               r"(siguen siendo|son|corresponden a) (los|las|el|la) "
                               r"(que (aparecen|figuran|estan|quedaron) )?registrad\w*|"
                               r"(se hizo|se calculo|se simulo|se realizo|se aplico) solo (para|sobre|en|con) (el|tu) riesgo|"
                               r"(siguen|quedan|estan) basad\w* en (tu|la) situacion (actual|registrada)|"
                               r"(son|siguen siendo|corresponden a) (los|las|el|la) de (tu|la) situacion")


def escenario_parcial(resp: str, paquete: dict) -> list[str]:
    """Corrección de la cátedra (E2E-04): con horas hipotéticas solo se simula el riesgo de atraso. Si la respuesta
    menciona carga, capacidad o plan, tiene que aclarar que son los registrados y que no se recalcularon.
    Error real: «el riesgo de atraso sube a alto cuando solo podés dedicar 9 h; hoy tenés una carga de 31 h… por esa
    razón el plan se recortó a tres materias», sin decir que carga y plan no corresponden a la simulación."""
    if not paquete.get("escenario_parcial"):
        return []
    t = sin_acentos(resp)
    if not RE_TEMA_REGISTRADO.search(t):
        return []
    # Corrida en Render (17/11): «Sí, podés llevar tres materias: …» como primera oración ante «si tuviera solo 9 horas,
    # ¿cuántas materias puedo llevar?». La aclaración llegaba recién al final; la respuesta directa era la registrada.
    oraciones = _oraciones(resp)
    # La primera oración va hasta el primer punto (no hasta el «;»): falso positivo real (Render 18/11) con «Podés cursar
    # hasta tres materias, pero con solo 9 h solo se simuló el riesgo de atraso; la carga… siguen siendo los registrados».
    primera = sin_acentos(re.split(r"(?<=[.!?])\s+|\n+", resp.strip(), maxsplit=1)[0]) if resp.strip() else ""
    if (primera and re.search(r"\b(podes|vas a poder) (llevar|cursar|tomar)\b|\bmaterias\b", primera)
            and not RE_NO_RECALCULADO.search(primera)
            and not re.search(r"registrad|no se recalcul|situacion actual|hoy\b|solo se simulo", primera)):
        return ["abre respondiendo con el plan registrado como si fuera el resultado de las horas hipotéticas"]
    for o in oraciones:
        so = sin_acentos(o)
        if RE_TEMA_REGISTRADO.search(so) and RE_NO_RECALCULADO.search(so):
            return []
    return ["menciona la carga o el plan sin aclarar que son los registrados y que no se recalcularon con las horas "
            "hipotéticas (solo se simuló el riesgo de atraso)"]


RE_CAPACIDAD_POR_AJUSTE = re.compile(
    r"capacidad[^.;]{0,50}\b(porque|debido a|a causa de|restando|tras|luego de|despues de)\b[^.;]{0,40}"
    r"(ajuste|sobrecarga|unidad|recorte)"
    r"|capacidad[^.;]{0,50}\bpor (el|un|la|una) (ajuste|recorte|reduccion)"
    r"|\b(reduccion|recorte|descuento|ajuste)s? (de [^.;]{0,20} )?(en|de|a) (la|tu) capacidad")
RE_CAPACIDAD_NEGADA = re.compile(r"no (cambia|modifica|reduce|afecta|toca|altera)\w* (la|tu) capacidad|"
                                 r"capacidad no (cambia|se modifica|se reduce|se ve afectada)")


def causa_de_capacidad(resp: str, paquete: dict) -> list[str]:
    """Corrida en Render (17/11, Juan): «tu capacidad es de 25 h porque se calculó restando un ajuste por sobrecarga…
    una reducción de una unidad en la capacidad disponible». La capacidad es dedicación sostenible − horas de trabajo
    (C-02); el ajuste por sobrecarga (C-04d) recorta el TAMAÑO del plan, no la capacidad."""
    if not any(s.get("modulo") == "M2" for s in _secciones(paquete)):
        return []
    problemas = []
    for o in _oraciones(resp):
        so = sin_acentos(o)
        if RE_CAPACIDAD_POR_AJUSTE.search(so) and not RE_CAPACIDAD_NEGADA.search(so):
            problemas.append(f"atribuye la capacidad al ajuste por sobrecarga: «{o.strip()[:140]}»")
    return problemas


RE_CERTEZA = re.compile(r"\b(certeza|certidumbre|nivel de seguridad|grado de seguridad)\b|"
                        # Render 18/11, Martina: «la confiabilidad del cálculo es alta (0,778)» (es la del dato de la
                        # historia) y «el valor podría variar ligeramente» (ningún dato dice cuánto)
                        r"\bconfiabilidad (del|de este|de ese|de la) (calculo|resultado|riesgo|modelo|valor|analisis|"
                        r"evaluacion|estimacion)\b|"
                        r"\b(podria|puede|podrian|pueden) variar (ligeramente|levemente|un poco|apenas|poco|muy poco)\b|"
                        r"consider\w*(lo|la)? (bastante |muy |totalmente )?(fiable|confiable|segur[oa])|"
                        r"\b(el|tu) (riesgo|resultado|calculo|valor)[^.;]{0,30}\b(es|resulta) (bastante |muy )?"
                        r"(fiable|confiable|segur[oa])")


def certeza_inventada(resp: str) -> list[str]:
    """Corrida en Render (17/11, Martina): «el riesgo… tiene un nivel de certeza alto… la confiabilidad de la información
    es alta (0,778), por lo que podés considerarlo bastante fiable». El grado difuso no mide certeza, y la confiabilidad
    del dato de la historia no dice nada de la exactitud del modelo (reglas candidatas)."""
    problemas = []
    for o in _oraciones(resp):
        so = re.sub(r"seguridad en los sistemas de informacion", " ", sin_acentos(o))  # nombre de asignatura
        m = RE_CERTEZA.search(so)
        if m and not _span_negado(so[max(0, m.start() - 40):m.start()]):
            problemas.append(f"presenta el resultado como cierto o fiable: «{o.strip()[:140]}»")
    return problemas


RE_FACTOR = {"completitud": re.compile(r"completitud[^.;]{0,40}\b(solo|apenas|baja|insuficiente|incomplet|falt)\w*|"
                                       r"\b(solo|apenas|baja|insuficiente)\w* (completitud|esta completa)"),
             "antiguedad_meses": re.compile(r"(desactualizad|antigua|vieja|atrasad)\w*[^.;]{0,30}historia|"
                                            r"historia[^.;]{0,30}(desactualizad|antigua|vieja)\w*")}


def factor_de_confiabilidad(resp: str, paquete: dict) -> list[str]:
    """Corrida en Render (17/11, Sofía): «la completitud es solo 0,92, lo que da una confiabilidad baja», cuando la
    completitud es ALTA y la causa es la antigüedad. Un factor favorable no puede presentarse como deficiente."""
    favorables = set()
    for s in _secciones(paquete):
        f = s["resultado"].get("factores_confiabilidad") if s.get("modulo") == "M1" else None
        if isinstance(f, dict):
            favorables |= set(f.get("favorables") or [])
    problemas = []
    for o in _oraciones(resp):
        so = sin_acentos(o)
        for var in favorables:
            rx = RE_FACTOR.get(var)
            m = rx.search(so) if rx else None
            if m and not _span_negado(so[max(0, m.start() - 30):m.start()]):
                problemas.append(f"presenta {var} (favorable) como causa de la confiabilidad baja: «{o.strip()[:140]}»")
    return problemas


RE_CAUSA_ESTRUCTURA = re.compile(
    r"\b(se apoya|se basa|se debe|depende|surge|deriva|lo (producen?|explican?|generan?|causan?)|es consecuencia|"
    r"a causa|porque|debido)\b[^.;]{0,60}(ruta critica|cuellos? de botella)"
    r"|(ruta critica|cuellos? de botella)[^.;]{0,120}\b(eleva|aumenta|sube|explica|genera|produce|causa)\w* (el|tu|ese) riesgo")
RE_CAUSA_ESTRUCTURA_NEGADA = re.compile(r"no (son|es|depende|se apoya|se basa|entran?|forman parte)\b|\bni\b")


def causa_del_riesgo(resp: str, paquete: dict) -> list[str]:
    """Corrida en Render (17/11, Martina): «ese riesgo se apoya en la ruta crítica… y en los cuellos de botella», cuando
    lo produce la criticidad del arrastre de Sistemas Operativos (E-08d). La ruta crítica y los cuellos de botella no
    son entradas del sistema difuso del riesgo de atraso."""
    causas = [s["resultado"].get("causa_del_riesgo") for s in _secciones(paquete) if s.get("modulo") == "M3"]
    causas = [c for c in causas if isinstance(c, dict)]
    if not causas:
        return []
    problemas = []
    for o in _oraciones(resp):
        so = sin_acentos(o)
        m = RE_CAUSA_ESTRUCTURA.search(so)
        if m and "riesgo" in so and not RE_CAUSA_ESTRUCTURA_NEGADA.search(so):
            problemas.append(f"atribuye el riesgo de atraso a la ruta crítica o a los cuellos de botella: «{o.strip()[:140]}»")
    return problemas


def instituciones_inventadas(resp: str, paquete: dict) -> list[str]:
    t, base = sin_acentos(resp), sin_acentos(json.dumps(paquete, ensure_ascii=False))
    return [i for i in INSTITUCIONES if i in t and i not in base]


def porcentaje_o_probabilidad(resp: str) -> list[str]:
    """«Probabilidad», «probable» o «%» presentados como lectura de un grado difuso. Se admite la negación
    explícita dentro de la misma oración («no debe interpretarse como una probabilidad»)."""
    problemas = ["usa porcentajes"] if "%" in resp else []
    for o in _oraciones(resp):
        t = sin_acentos(o)
        t = re.sub(r"probabilidad(es)? y estadistica", " ", t)  # nombre de asignatura (falso positivo real: Ana)
        for m in re.finditer(r"\bprobab\w*|\bprobable\w*|\bimprobable\w*", t):
            antes = t[max(0, m.start() - 60):m.start()]
            if not _span_negado(antes):
                problemas.append(f"presenta un grado como probabilidad: «{o.strip()[:140]}»")
                break
    return problemas


def sin_dictamen(resp: str, paquete: dict) -> list[str]:
    """Si M1 no emitió dictamen, la respuesta no puede juzgar la habilitación (error real: Valentina, Física II
    aprobada, respondida como «no podés cursar»). Tiene que informar el estado registrado en la historia."""
    t = sin_acentos(resp)
    problemas = []
    for s in _secciones(paquete):
        r = s["resultado"]
        if s.get("modulo") != "M1" or "sin_dictamen" not in r or not isinstance(r.get("asignatura"), dict):
            continue
        a = sin_acentos(r["asignatura"].get("nombre"))
        estado = sin_acentos(r["asignatura"].get("estado_en_historia", ""))
        if not r.get("advertencias") and re.search(r"\bno\s+(podes|puedes|puede|vas a poder)\s+(cursar|rendir)\b[^.]{0,60}"
                                                   + re.escape(a), t):
            problemas.append(f"juzga que no podés cursar/rendir {r['asignatura'].get('nombre')}, pero no hay dictamen")
        palabra = estado.split()[0] if estado and not estado.startswith("pendiente") else None
        if palabra and a in t and palabra[:6] not in t:
            problemas.append(f"no dice que {r['asignatura'].get('nombre')} figura como «{estado}» en la historia")
    return problemas


def requisito_para_rendir(resp: str, paquete: dict) -> list[str]:
    """Advertencia cursa_sin_rendir (H-07): para rendir hay que APROBAR la correlativa (error real: «hasta que
    regularices Simulación», que ya era regular)."""
    t = sin_acentos(resp)
    problemas = []
    # Correlativas que algún dictamen del paquete SÍ exige regularizar: ahí «regularizar» es correcto (p. ej. Lucía).
    a_regularizar = set()
    for d in _dictamenes_m1(paquete):
        for c in (d.get("causas") or []) + (d.get("causa_raiz") or []):
            if "reg" in sin_acentos(f"{c.get('tipo', '')} {c.get('correlatividad', '')}"):
                a_regularizar.add(sin_acentos(c.get("asignatura")))
    for s in _secciones(paquete):
        advs = (s["resultado"].get("advertencias") or []) if s.get("modulo") == "M1" else []
        advs = [a for a in advs if a.get("tipo") == "cursa_sin_rendir"]
        if not advs:
            continue
        if not re.search(r"aprob|aprueb", t):  # «aprobar», «aprobada» y también «apruebes», «aprueba»
            return ["para rendir hace falta aprobar la correlativa y la respuesta no lo dice"]
        # Segunda devolución (corrida del 17/11): abría bien («hasta que apruebes Simulación») y cerraba con
        # «gestionar la regularización de Simulación». Basta con que aparezca «aprob» en otra oración para que
        # el control anterior pasara; ahora también se busca «regulariz…» junto a la correlativa.
        for a in advs:
            m = re.search(r"hasta aprobar (.+?)\.?$", sin_acentos(a.get("mensaje")))
            req = m.group(1).strip() if m else ""
            if not req or req in a_regularizar:
                continue
            for o in _oraciones(resp):
                os_ = sin_acentos(o)
                if req in os_ and re.search(r"regulariz", os_) and not RE_REGULARIZAR_NEGADO.search(os_):
                    problemas.append(f"dice que hay que regularizar {req}, pero para rendir hay que aprobarla")
                    break
    return sorted(set(problemas))


def escenario_hipotetico(resp: str, paquete: dict) -> list[str]:
    """Una simulación tiene que presentarse como tal y compararse con lo registrado (error real: «tu riesgo sigue
    siendo alto», cuando el registrado era medio y el alto era el simulado)."""
    t = sin_acentos(resp)
    problemas = []
    for s in _secciones(paquete):
        r = s["resultado"]
        if not r.get("escenario_hipotetico"):
            continue
        if not re.search(r"simul|hipotet|escenario|si (solo )?(pudieras|tuvieras|dedicaras)", t):
            problemas.append("no aclara que el resultado es una simulación")
        reg = sin_acentos((r.get("riesgo_registrado_en_PG2") or {}).get("etiqueta", ""))
        sim = sin_acentos((r.get("riesgo_atraso") or {}).get("etiqueta", ""))
        if reg and reg not in t:
            problemas.append(f"no compara con el riesgo registrado ({reg})")
        if reg and sim and reg != sim:
            for o in _oraciones(resp):
                so = sin_acentos(o)
                if "atraso" in so and "sobrecarga" not in so and re.search(r"sigue (siendo|igual)|se mantiene|seguiria", so):
                    problemas.append(f"dice que el riesgo de atraso «sigue igual», pero pasa de {reg} a {sim}")
                    break
    return problemas


ETIQUETAS_FEM = {"confiabilidad": "confiabilidad", "adecuacion": "adecuacion"}
ETIQUETAS_MASC = {"riesgo de atraso": ("riesgo_atraso", "riesgo_de_atraso", "riesgo_registrado"),  # E2E-04: «de medio a alto»
                  "riesgo de sobrecarga": ("riesgo_sobrecarga",)}


def etiqueta_inventada(resp: str, paquete: dict) -> list[str]:
    """La etiqueta difusa que se nombra tiene que existir en los datos (error real: Tomás, «confiabilidad baja»
    cuando la confiabilidad no tenía activación). Se ignoran los resultados de escenarios hipotéticos registrados."""
    t = sin_acentos(resp)
    etiquetas: dict[str, set[str]] = {}
    for ruta, v in recorrer(paquete):
        if not ruta.endswith("/etiqueta") or not isinstance(v, str):
            continue
        r = ruta.lower()
        for k, c in ETIQUETAS_FEM.items():
            if c in r:
                etiquetas.setdefault(k, set()).add(sin_acentos(v))
        for k, cs in ETIQUETAS_MASC.items():
            if any(c in r for c in cs):
                etiquetas.setdefault(k, set()).add(sin_acentos(v))
    patrones = [(k, r"(alta|media|baja)\b") for k in ETIQUETAS_FEM] + [(k, r"(alto|medio|bajo)\b") for k in ETIQUETAS_MASC]
    for ruta, v in recorrer(paquete):  # «Riesgo de sobrecarga: medio (grado 0,4…)» en la lectura guiada de M2
        if isinstance(v, str) and not ruta.endswith("/enunciado"):  # un enunciado habla de etiquetas en general
            sv = sin_acentos(v)
            for k, patron in patrones:
                for m in re.finditer(re.escape(k) + r"[^.;\n]{0,35}?\b" + patron, sv):
                    etiquetas.setdefault(k, set()).add(m.group(1))
    problemas = []
    for k, patron in patrones:
        for m in re.finditer(re.escape(k) + r"[^.;\n]{0,35}?\b" + patron, t):
            dicha = m.group(1)
            contexto = t[max(0, m.start() - 30):m.end()]
            if re.search(r"\bno (es|esta|tiene|hay|puede|se (puede|considera)|alcanza)|\bsin\b|ni (alta|media|baja)", contexto):
                continue
            # «el riesgo de atraso bajo 9 h es alto»: «bajo» como preposición (falso positivo real, Render 18/11)
            if dicha == "bajo" and re.match(r"\s*(\d|esas?|esos?|estas?|estos?|las?|los?|tu|tus|un|una)\b", t[m.end():]):
                continue
            validas = {e[:4] for e in etiquetas.get(k, set())}
            if dicha[:4] not in validas:
                problemas.append(f"dice que la {k} es «{dicha}», pero ese valor no figura en los datos"
                                 + (f" ({', '.join(sorted(etiquetas.get(k, [])))})" if etiquetas.get(k) else " (no hay dato)"))
    return problemas


def _dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _dicts(v)


RE_ES_LLAVE = r"[^.;:\n]{0,60}?\b(es|son|resulta|resultan|funciona|funcionan|figura|figuran)\b[^.;:\n]{0,25}?\b(llaves?|claves?)\b"


def llave_inventada(resp: str, paquete: dict) -> list[str]:
    """Una asignatura que M3 evaluó como NO llave (grado bajo el corte α) no puede presentarse como «materia llave»
    o «clave» (error real: Lucía, «Simulación y Análisis Numérico son materias clave», con Simulación no llave)."""
    no_llave = {sin_acentos(d["asignatura"]) for d in _dicts(paquete)
                if d.get("es_llave") is False and isinstance(d.get("asignatura"), str)}
    # Riesgo de atraso de M3 (corrida en Render 17/11, Martina): trae «asignaturas_llave» y otras listas (ruta crítica,
    # arrastres, cuellos de botella) sin es_llave. Las que no están entre las llave tampoco pueden llamarse «clave».
    for s in _secciones(paquete):
        r = s["resultado"]
        if s.get("modulo") != "M3" or not isinstance(r.get("asignaturas_llave"), list):
            continue
        llave = {sin_acentos(a.get("asignatura")) for a in r["asignaturas_llave"] if isinstance(a, dict)}
        mencionadas = list(r.get("ruta_critica") or []) + [x.get("asignatura") for x in (r.get("arrastres") or [])
                                                             + (r.get("cuellos_de_botella") or []) if isinstance(x, dict)]
        no_llave |= {sin_acentos(a) for a in mencionadas if isinstance(a, str)} - llave
    nombres = {sin_acentos(d["asignatura"]) for d in _dicts(paquete) if isinstance(d.get("asignatura"), str)} | no_llave
    problemas = []
    for o in _oraciones(resp):
        so = sin_acentos(o)
        # «La ruta crítica incluye SO, Redes de Datos y SSI, y esas asignaturas aparecen como claves»
        if any(a in so for a in no_llave):
            m = re.search(r"\b(esas|estas|todas|las tres|las dos|ambas)\b[^.;:\n]{0,30}?\b(son|aparecen como|figuran como|"
                          r"resultan|se consideran)\s+(materias?\s+|asignaturas?\s+)?(llaves?|claves?)\b", so)
            if m and not re.search(r"\bno\b|\bni\b", m.group(0)):
                nombres = sorted(a for a in no_llave if a in so)
                problemas.append(f"presenta como llave a {', '.join(nombres)}, que no están entre las asignaturas llave")
        for a in sorted(no_llave):
            if a not in so:
                continue
            for m in list(re.finditer(re.escape(a) + RE_ES_LLAVE, so)) + \
                     list(re.finditer(r"\b(materias?|asignaturas?)\s+(llaves?|claves?)\b[^.;:\n]{0,40}?" + re.escape(a), so)):
                if re.search(r"\bno\b|\bni\b|\bsin\b|\bsolo\b|unicamente|en cambio", m.group(0)):
                    continue
                # «…Seguridad en los SI, y que Análisis Numérico figura como asignatura llave»: con verbo en singular,
                # si otra asignatura se interpone, el sujeto es esa otra (falso positivo real del log, Martina). Con verbo
                # en plural («Simulación y Análisis Numérico son clave», C-41) las dos son sujeto y se sigue marcando.
                resto = m.group(0).replace(a, " ", 1)
                v = re.search(r"\b(es|resulta|funciona|figura)\b", resto)
                if v and any(n != a and n in resto[:v.start()] for n in nombres):
                    continue
                problemas.append(f"presenta {a} como materia llave, pero su grado está debajo del corte (no es llave)")
                break
    return sorted(set(problemas))


def riesgo_negado(resp: str, paquete: dict) -> list[str]:
    """«No tenés riesgo de atraso» cuando el dato es un grado BAJO (error real: Ana, riesgo bajo 0,20).
    «No tenés riesgo alto» sí es correcto."""
    hay_riesgo = any("riesgo" in ruta.lower() and ruta.endswith("/etiqueta") for ruta, _ in recorrer(paquete)) \
        or "riesgo" in sin_acentos(json.dumps(paquete, ensure_ascii=False))
    if not hay_riesgo:
        return []
    t = sin_acentos(resp)
    m = re.search(r"\bno\s+(tenes|hay|existe|corres)\s+(ningun\s+)?riesgo(\s+de\s+(atraso|sobrecarga))?(?!\s+(alto|medio|grave|importante|elevado))", t)
    return ["dice que no hay riesgo, pero el dato es un grado (bajo no es cero)"] if m else []


def jerga(resp: str) -> list[str]:
    t = sin_acentos(resp)
    encontrados = [j for j in JERGA if re.search(r"\b" + re.escape(j), t)]
    encontrados += re.findall(r"\b[a-z]+_[a-z_]+\b", resp)
    encontrados += re.findall(r"\b(?:Bloqueo|Habilitacion)[A-Z]\w+\b", resp)
    encontrados += [m.group(0) for m in RE_JERGA_INTERNA.finditer(resp)]
    return sorted(set(encontrados))


def idioma(resp: str) -> list[str]:
    problemas = []
    pt = [m.group(0) for m in RE_PORTUGUES.finditer(resp)]
    if pt:
        problemas.append("hay palabras en portugués: " + ", ".join(sorted(set(pt))[:5]))
    if len(RE_INGLES.findall(resp)) >= 4:
        problemas.append("hay fragmentos en inglés")
    return problemas


def reserva_omitida(resp: str, paquete: dict) -> list[str]:
    ctx = paquete.get("contexto") or {}
    conf = (ctx.get("confiabilidad") or {}).get("etiqueta")
    if not (ctx.get("reserva") or conf in ("media", "baja")):
        return []
    t = sin_acentos(resp)
    if re.search(r"al dia|reserva|confiab|actualiz|asesor", t):
        return []
    return ["la historia académica tiene reserva y la respuesta no lo menciona"]


def verificar(respuesta: str, paquete: dict, ids_en_cuerpo: bool = False) -> dict[str, list[str]]:
    """Devuelve solo los controles que fallaron (dict vacío = respuesta verificada)."""
    r = limpiar_texto(respuesta)
    if not r:
        return {"vacia": ["respuesta vacía"]}
    c = {
        "numeros_sin_respaldo": numeros_sin_respaldo(r, paquete),
        "ids_sin_respaldo": ids_sin_respaldo(r, paquete),
        "ids_en_cuerpo": [] if ids_en_cuerpo else sorted(set(RE_REGLA.findall(r)) | set(RE_CORRELATIVIDAD.findall(r))),
        "correlatividad_como_regla": correlatividad_como_regla(r),
        "letras_sueltas": sorted(set(re.findall(r"(?<![\w-])[XY](?![\w-])", r))),
        "orden_de_destrabe": orden_de_destrabe(r, paquete),
        "tipo_de_decision": tipo_de_decision(r, paquete),
        "cobertura_normativa": cobertura_normativa(r, paquete),
        "causa_de_exclusion": causa_de_exclusion(r, paquete),
        "magnitudes_cruzadas": magnitudes_cruzadas(r, paquete),
        "instituciones_inventadas": instituciones_inventadas(r, paquete),
        "porcentaje_o_probabilidad": porcentaje_o_probabilidad(r),
        "sin_dictamen": sin_dictamen(r, paquete),
        "requisito_para_rendir": requisito_para_rendir(r, paquete),
        "escenario_hipotetico": escenario_hipotetico(r, paquete),
        "causa_de_corte": causa_de_corte(r, paquete),
        "desglose_incompleto": desglose_incompleto(r, paquete),
        "escenario_parcial": escenario_parcial(r, paquete),
        "etiqueta_inventada": etiqueta_inventada(r, paquete),
        "llave_inventada": llave_inventada(r, paquete),
        "riesgo_negado": riesgo_negado(r, paquete),
        "causa_de_capacidad": causa_de_capacidad(r, paquete),
        "certeza_inventada": certeza_inventada(r),
        "factor_de_confiabilidad": factor_de_confiabilidad(r, paquete),
        "causa_del_riesgo": causa_del_riesgo(r, paquete),
        "jerga": jerga(r),
        "voseo": sorted(set(m.lower() for m in RE_TUTEO.findall(r))),
        "idioma": idioma(r),
        "reserva_omitida": reserva_omitida(r, paquete),
    }
    return {k: v for k, v in c.items() if v}


RE_FUNDAMENTO = re.compile(r"(?im)^[ \t*]*(Fundamento|Evidencia)[ \t*]*:.*$")


def preparar(respuesta: str) -> str:
    """Normaliza la redacción del LLM antes de verificarla (M1): quita una línea «Fundamento:»/«Evidencia:» que el
    modelo haya escrito por su cuenta (la arma Python) y pasa los decimales a coma."""
    r = RE_FUNDAMENTO.sub("", limpiar_texto(respuesta)).strip()
    return re.sub(r"(?<=\d)\.(?=\d)", ",", r)


def hay_graves(fallas: dict) -> bool:
    return any(k in GRAVES for k in fallas)


def instruccion_correccion(fallas: dict) -> str:
    return "; ".join(f"{INSTRUCCION.get(k, k)}: {v}" for k, v in fallas.items())
