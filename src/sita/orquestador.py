"""Orquestador único de SITA (PG3).

Flujo (patrón sándwich ampliado a cuatro submódulos):
  1. entrada ............ validación de longitud
  2. enrutamiento ....... LLM + prompt maestro -> JSON validado con Pydantic (un reintento)
  3. resolución ......... estudiante (anclaje del legajo en el texto, memoria de sesión) y asignaturas
  4. contexto ........... estado de la consulta en el grafo (¿cortada? ¿dónde? confiabilidad del dato)
  5. plan de ejecución .. orden M1 -> M2 -> M3 -> M4 y propagación de cortes (X-01, X-02, X-03)
  6. ejecución .......... cada submódulo corre sus plantillas Cypher de solo lectura
  7. enriquecimiento .... reglas DETERMINISTAS que suman otros submódulos cuando su conocimiento cambia
                          la respuesta (no lo decide el LLM)
  8. explicación ........ LLM + prompt maestro, solo sobre el paquete recuperado
  9. verificación ....... controles sintácticos y semánticos; una reescritura; respaldo determinístico
 10. cierre ............. línea «Fundamento:» armada por Python y traza completa (JSONL + memoria)
"""
from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from datetime import datetime

from pydantic import ValidationError

from . import respaldo as resp_det
from .catalogo import Catalogo
from .esquemas import INTENCIONES, ORDEN_MODULOS, Enrutamiento
from .modulos import REGISTRO, transversal
from .modulos.base import Seccion
from .prompts import PROMPT_ENRUTADOR, prompt_explicacion
from .textos import limpiar_texto, limpiar_vacios, numero_en_texto, orden_natural, texto_plano
from .llm import mensaje_error
from .verificacion import hay_graves, instruccion_correccion, preparar, verificar

MAX_CARACTERES = 1000
MAX_ENRIQUECIMIENTOS = 3
MSG_ALCANCE = ("Solo puedo ayudarte con tu trayectoria en Ingeniería en Sistemas (Plan 2023): si podés cursar o rendir "
               "una materia, tu carga y capacidad, tu riesgo de atraso, qué materias son llave y qué te conviene cursar.")

MOTIVO_CORTE = {
    # Corrección de la cátedra (E2E-05): el corte en M1 NO es una restricción de habilitación ni de correlatividades;
    # lo produce X-01 por la calidad del dato. El texto anterior («se cortó en la habilitación normativa») llevaba al
    # LLM a atribuirle la causa a la habilitación.
    "M1": ("La consulta se detuvo antes de evaluar esta parte por la calidad de los datos de tu historia académica "
           "(regla X-01: datos desactualizados, contradictorios o poco confiables). No es una falta de correlativas: "
           "primero hay que actualizar o corregir la historia."),
    "M2": ("La consulta se cortó en carga y capacidad porque faltan datos de tu contexto (regla X-02): sin ellos no "
           "se estima la carga ni se arma un plan (regla X-03). Los dictámenes de habilitación se conservan."),
}
CAUSA_CORTE = {
    "M1": ("calidad del dato de la historia académica (regla X-01): no es una restricción de correlatividades ni un "
           "dictamen de habilitación"),
    "M2": "faltan datos del contexto del estudiante para estimar la carga (reglas X-02 y X-03)",
}
MOTIVO_ENRIQUECIMIENTO = {
    "criticidad_causa_raiz": "Indica cuánto pesa en el plan de estudios la materia que hay que destrabar primero.",
    "plan_de_la_asignatura": ("Qué decidió el plan de este período sobre esa misma asignatura (es una recomendación, "
                              "no una restricción)."),
    "dictamen_de_la_asignatura": "Si esa asignatura está habilitada o bloqueada por correlatividades.",
    "excluidas_por_recorte": "Qué asignaturas quedaron fuera del plan por ese recorte (siguen habilitadas).",
    "tope_frente_a_capacidad": ("El tope de materias que declaró el estudiante frente al tamaño admisible por capacidad: "
                                "el tope no cambia el tamaño admisible, pero limita el plan."),
}
MOTIVO_SIN_RAIZ = ("Cuánto pesa en el plan de estudios cada condición pendiente. No indica un orden obligatorio entre "
                   "ellas: no digas que una va «primero».")


class Orquestador:
    def __init__(self, kb, llm, cfg, catalogo: Catalogo | None = None):
        self.kb, self.llm, self.cfg = kb, llm, cfg
        self.catalogo = catalogo or Catalogo.desde_kb(kb)
        self.sesiones: dict[str, dict] = {}
        self.trazas: "OrderedDict[str, dict]" = OrderedDict()

    # ================================================================== API pública
    def procesar(self, texto: str, sesion_id: str = "local") -> dict:
        t0 = time.time()
        traza = {"traza_id": uuid.uuid4().hex[:12], "fecha": datetime.now().isoformat(timespec="seconds"),
                 "sesion_id": sesion_id, "entrada": texto, "modelo": getattr(self.llm, "nombre", "?")}
        self.kb.registro.clear()
        try:
            self._procesar(limpiar_texto(texto), sesion_id, traza)
        except Exception as exc:  # noqa: BLE001 - nunca se muestra un traceback al estudiante
            traza["error"] = f"{type(exc).__name__}: {exc}"
            self._cerrar(traza, mensaje_error(exc, self.cfg.llm_timeout), flujo="error")
        traza["consultas_ejecutadas"] = list(self.kb.registro)
        traza["segundos"] = round(time.time() - t0, 2)
        self._guardar(traza)
        return traza

    def traza(self, traza_id: str) -> dict | None:
        if traza_id in self.trazas:
            return self.trazas[traza_id]
        try:
            with self.cfg.log_path.open(encoding="utf-8") as f:
                for linea in f:
                    t = json.loads(linea)
                    if t.get("traza_id") == traza_id:
                        return t
        except FileNotFoundError:
            pass
        return None

    # ================================================================== flujo
    def _procesar(self, texto: str, sesion_id: str, traza: dict) -> None:
        # 1. entrada
        if not texto or len(texto) > MAX_CARACTERES:
            return self._cerrar(traza, f"Escribí tu consulta en un mensaje de hasta {MAX_CARACTERES} caracteres, con tu "
                                       "legajo y qué querés saber.", flujo="aclaracion: entrada")
        # 2. enrutamiento
        enr = self._enrutar(texto, traza)
        if enr is None:
            return self._cerrar(traza, "No pude interpretar tu consulta. ¿La reformulás indicando tu legajo y qué "
                                       "querés saber?", flujo="aclaracion: enrutamiento invalido")
        if not enr.pedidos:
            return self._cerrar(traza, MSG_ALCANCE if enr.fuera_de_dominio else
                                "No terminé de entender la consulta. Podés preguntarme, por ejemplo: «Legajo 12345, "
                                "¿por qué no puedo cursar Simulación?» o «¿Qué me conviene cursar?».",
                                flujo="aclaracion: fuera de dominio" if enr.fuera_de_dominio else "aclaracion: sin pedidos")

        # 3. resolución de entidades (sin consultar trazas: solo catálogo)
        est, msg = self._resolver_estudiante(enr, texto, sesion_id, traza)
        if msg:
            return self._cerrar(traza, msg, flujo="aclaracion: estudiante")
        # 4. contexto de la consulta del estudiante (antes de pedir aclaraciones: si está cortada, eso es la respuesta)
        ctx = None
        if est:
            ctx = transversal.contexto(self.kb, est["legajo"])
            if ctx is None:
                return self._cerrar(traza, "El sistema no tiene una consulta registrada para tu legajo todavía.",
                                    flujo="sin datos en el grafo")
        traza["contexto"] = ctx
        pedidos, msg = self._resolver_pedidos(enr, texto, traza, ctx)
        if msg:
            return self._cerrar(traza, msg, flujo="aclaracion: parametros")

        # 5-6. plan de ejecución con cortes y ejecución
        secciones, no_eval = self._ejecutar(pedidos, ctx, traza)
        # 7. enriquecimiento determinista entre submódulos
        secciones += self._enriquecer(secciones, ctx, est, traza)
        traza["modulos_consultados"] = sorted({s.modulo for s in secciones if s.modulo != "X"}, key=ORDEN_MODULOS.get)
        traza["secciones"] = [s.para_log() for s in secciones]
        traza["no_evaluado"] = no_eval

        if all(s.estado != "ok" for s in secciones) and not no_eval:
            return self._cerrar(traza, " ".join(s.mensaje for s in secciones if s.mensaje) or
                                "No encontré datos para responderte.", flujo="sin datos en el grafo")

        # 8-9. explicación verificada
        paquete = self._paquete(texto, ctx, secciones, no_eval)
        traza["paquete_llm"] = paquete
        respuesta, verif = self._explicar(paquete)
        traza["verificacion"] = verif
        # 10. cierre
        self._cerrar(traza, respuesta, flujo="sandwich completo", secciones=secciones, no_eval=no_eval)

    # ------------------------------------------------------------------ 2. enrutamiento
    def _enrutar(self, texto: str, traza: dict) -> Enrutamiento | None:
        user, error = texto, None
        intentos = []
        user = f"Mensaje: {texto}"  # mismo formato que los ejemplos del prompt (M1)
        esquema = Enrutamiento.model_json_schema()
        for _ in range(2):
            crudo = self.llm.chat(PROMPT_ENRUTADOR, user, json_mode=True, max_tokens=1500, json_schema=esquema)
            intentos.append(crudo)
            try:
                obj = json.loads(_json_de(crudo))
                enr = Enrutamiento.model_validate(obj)
                traza["enrutamiento"] = {"crudo": intentos, "validado": enr.model_dump(), "correcciones": enr.correcciones}
                return enr
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                error = str(exc).splitlines()[0][:300]
                user = (f"Mensaje: {texto}\n\n(Tu respuesta anterior no cumplió el formato: {error}. "
                        "Devolvé SOLO el objeto JSON con las claves indicadas.)")
        traza["enrutamiento"] = {"crudo": intentos, "error": error}
        return None

    # ------------------------------------------------------------------ 3. resolución
    def _resolver_estudiante(self, enr: Enrutamiento, texto: str, sesion_id: str, traza: dict):
        necesita = any(INTENCIONES[p.intencion].requiere_estudiante for p in enr.pedidos)
        if not necesita:
            return None, None
        legajo = enr.legajo
        if legajo and not numero_en_texto(legajo, texto):  # anclaje: el legajo tiene que estar escrito (M3)
            traza.setdefault("correcciones", []).append(f"legajo {legajo} descartado: no aparece en el mensaje")
            legajo = None
        if not (legajo or enr.nombre_estudiante) and sesion_id in self.sesiones:
            traza["estudiante_de_sesion"] = True
            est = self.sesiones[sesion_id]
        else:
            est, msg = self.catalogo.resolver_estudiante(legajo, enr.nombre_estudiante)
            if msg:
                return None, msg
        self.sesiones[sesion_id] = est  # memoria de sesión: solo la identidad (M1)
        traza["estudiante"] = est
        return est, None

    def _resolver_pedidos(self, enr: Enrutamiento, texto: str, traza: dict, ctx: dict | None = None):
        resueltos: list[dict] = []
        cortada_m1 = bool(ctx and ctx.get("estado") == "cortada" and ctx.get("corte_en") == "M1")
        for p in enr.pedidos:
            info = INTENCIONES[p.intencion]
            if info.requiere_asignatura and not p.asignaturas and cortada_m1 and info.requiere_estudiante:
                # Caso real (Tomás): «¿por qué no me dan ningún dictamen?» sin asignatura y con la consulta cortada en M1:
                # la respuesta es el corte, no una pregunta por la materia.
                traza.setdefault("correcciones", []).append(
                    f"{p.intencion} sin asignatura con la consulta cortada en M1: se explica el corte (estado_historia)")
                resueltos.append({"intencion": "estado_historia", "modulo": "M1", "alcance": "cursar", "filtro": "todas"})
                continue
            base = {"intencion": p.intencion, "modulo": info.modulo, "alcance": p.alcance or "cursar", "filtro": p.filtro}
            asignaturas = []
            for nombre in p.asignaturas:
                a, msg = self.catalogo.resolver_asignatura(nombre)
                if msg:
                    return None, msg
                asignaturas.append(a)
            if info.requiere_asignatura and not asignaturas:
                return None, f"¿Sobre qué asignatura querés saber ({info.descripcion})?"
            if p.intencion == "criticidad_asignatura":
                resueltos.append({**base, "codigos": [a["codigo"] for a in asignaturas],
                                  "nombres": [a["nombre"] for a in asignaturas]})
            elif p.intencion in ("dictamen_asignatura", "decision_plan_asignatura") and asignaturas:
                for a in asignaturas:  # una entrada por asignatura (limitación de PI4: una por mensaje)
                    resueltos.append({**base, "codigo": a["codigo"], "nombre_asignatura": a["nombre"]})
            elif p.intencion == "vigencia_regularidad":
                a = asignaturas[0] if asignaturas else None
                resueltos.append({**base, "codigo": a["codigo"] if a else None,
                                  "nombre_asignatura": a["nombre"] if a else None})
            elif p.intencion == "riesgo_atraso" and enr.horas_hipoteticas is not None:
                h = enr.horas_hipoteticas
                if not numero_en_texto(h, texto):
                    traza.setdefault("correcciones", []).append("horas hipotéticas descartadas: no aparecen en el mensaje")
                    resueltos.append(base)
                elif not 0 <= h <= 55:
                    return None, (f"{h:g} horas semanales disponibles no es un escenario posible para simular: la capacidad "
                                  "disponible del modelo va de 0 a 55 horas por semana. Probá con un valor en ese rango.")
                else:
                    resueltos.append({**base, "horas_hipoteticas": h})
            elif p.intencion == "urgencias_vencimiento":
                hz = enr.horizonte_meses
                resueltos.append({**base, "horizonte_meses": hz if hz is not None and 0 < hz <= 24 else None})
            else:
                resueltos.append(base)
        # Corrida en Render (17/11): «si tuviera solo 9 horas, ¿qué me conviene cursar y cuántas materias puedo llevar?»
        # se enrutó a M2 y M4 sin M3: las 9 h se descartaban en silencio y la respuesta mostraba el plan registrado como
        # si respondiera a la hipótesis. Las horas hipotéticas solo las simula M3: se agrega su simulación y, con ella,
        # el aviso de escenario parcial (carga, capacidad y plan no se recalculan).
        h = enr.horas_hipoteticas
        if (h is not None and 0 <= h <= 55 and numero_en_texto(h, texto) and resueltos
                and not any(r["intencion"] == "riesgo_atraso" for r in resueltos)):
            info = INTENCIONES["riesgo_atraso"]
            resueltos.append({"intencion": "riesgo_atraso", "modulo": info.modulo, "alcance": "cursar",
                              "filtro": "todas", "horas_hipoteticas": h})
            traza.setdefault("correcciones", []).append(
                f"horas hipotéticas ({h:g} h) sin pedido de riesgo de atraso: se agrega la simulación de M3")
        # sin duplicados, en el orden de la cadena de razonamiento M1 -> M4
        vistos, unicos = set(), []
        for r in sorted(resueltos, key=lambda r: ORDEN_MODULOS[r["modulo"]]):
            clave = (r["intencion"], r.get("codigo"), tuple(r.get("codigos", [])), r.get("alcance"), r.get("filtro"))
            if clave not in vistos:
                vistos.add(clave)
                unicos.append(r)
        traza["pedidos_resueltos"] = unicos[:6]
        return unicos[:6], None

    # ------------------------------------------------------------------ 5-6. ejecución con cortes
    def _ejecutar(self, pedidos: list[dict], ctx: dict | None, traza: dict):
        corte_en = ctx.get("corte_en") if ctx and ctx.get("estado") == "cortada" else None
        legajo = ctx.get("legajo") if ctx else None
        a_ejecutar, no_eval = [], []
        for p in pedidos:
            independiente = p["intencion"] == "criticidad_asignatura"  # no depende de la historia del estudiante
            bloqueado = (corte_en == "M1" and p["intencion"] != "estado_historia" and not independiente) or \
                        (corte_en == "M2" and p["modulo"] in ("M2", "M3", "M4") and not independiente)
            if bloqueado:
                no_eval.append({"modulo": p["modulo"], "intencion": p["intencion"],
                                "descripcion": INTENCIONES[p["intencion"]].descripcion, "motivo": MOTIVO_CORTE[corte_en]})
            else:
                a_ejecutar.append(p)
        secciones: list[Seccion] = []
        if corte_en == "M1" and not any(p["intencion"] == "estado_historia" for p in a_ejecutar):
            s = REGISTRO["M1"].ejecutar(self.kb, "estado_historia", {"legajo": legajo})
            s.origen, s.motivo = "contexto", "Explica por qué se cortó la consulta y qué datos hay que actualizar."
            secciones.append(s)
        if corte_en == "M2":
            secciones.append(transversal.corte(self.kb, legajo, "Qué datos faltan para continuar la evaluación."))
        for p in a_ejecutar:
            secciones.append(REGISTRO[p["modulo"]].ejecutar(self.kb, p["intencion"], {**p, "legajo": legajo}))
        traza["plan_ejecucion"] = {"corte_en": corte_en, "ejecutados": [p["intencion"] for p in a_ejecutar],
                                   "no_evaluados": [n["intencion"] for n in no_eval]}
        return secciones, no_eval

    # ------------------------------------------------------------------ 7. enriquecimiento
    def _enriquecer(self, secciones: list[Seccion], ctx: dict | None, est: dict | None, traza: dict) -> list[Seccion]:
        corte_en = ctx.get("corte_en") if ctx and ctx.get("estado") == "cortada" else None
        legajo = est["legajo"] if est else None
        hechos = {(s.intencion, s.parametros.get("codigo"), tuple(s.parametros.get("codigos") or [])) for s in secciones}
        pedidas = {s.intencion for s in secciones}
        nuevas: list[Seccion] = []
        reglas_aplicadas = []

        def agregar(modulo, intencion, params, clave_motivo, foco=None, exigir_ok=False, motivo=None):
            if len(nuevas) >= MAX_ENRIQUECIMIENTOS:
                return
            clave = (intencion, params.get("codigo"), tuple(params.get("codigos") or []))
            if clave in hechos or (intencion in ("capacidad", "plan") and intencion in pedidas):
                return
            s = REGISTRO[modulo].ejecutar(self.kb, intencion, params)
            if exigir_ok and s.estado != "ok":
                return
            s.origen, s.motivo, s.foco = "enriquecimiento", motivo or MOTIVO_ENRIQUECIMIENTO[clave_motivo], foco
            hechos.add(clave)
            pedidas.add(intencion)
            nuevas.append(s)
            reglas_aplicadas.append(clave_motivo)

        # Dos rondas: lo que agrega una regla puede disparar otra (p. ej. M1 -> M4 -> M2 en el caso de Martina).
        pendientes = [s for s in secciones if s.origen == "pedido"]
        for _ronda in range(2):
            agregadas_antes = len(nuevas)
            for s in pendientes:
                if s.estado != "ok":
                    continue
                r = s.resultado or {}
                if s.intencion == "dictamen_asignatura":
                    d = r.get("dictamen") or {}
                    # R-E1: bloqueo -> ¿cuánto pesa lo que hay que destrabar? (M1 -> M3)
                    if str(d.get("tipo", "")).startswith("Bloqueo"):
                        raices = [c.get("asignatura") for c in d.get("causa_raiz") or []]
                        destrabar = raices or [c.get("asignatura") for c in d.get("causas") or []]
                        cods = [a["codigo"] for a in (self.catalogo.por_nombre(n) for n in destrabar if n) if a][:3]
                        if cods:
                            agregar("M3", "criticidad_asignatura", {"codigos": cods}, "criticidad_causa_raiz",
                                    exigir_ok=True, motivo=None if raices else MOTIVO_SIN_RAIZ)
                    # R-E2: dictamen -> ¿qué decidió el plan sobre esa asignatura? (M1 -> M4), solo si fue candidata
                    if corte_en is None and legajo and s.parametros.get("codigo") is not None:
                        agregar("M4", "decision_plan_asignatura", {"legajo": legajo, "codigo": s.parametros["codigo"]},
                                "plan_de_la_asignatura", exigir_ok=True)
                elif s.intencion == "decision_plan_asignatura" and legajo:
                    # R-E3: exclusión del plan -> ¿está habilitada o bloqueada? (M4 -> M1)
                    agregar("M1", "dictamen_asignatura",
                            {"legajo": legajo, "codigo": s.parametros["codigo"], "alcance": "cursar"},
                            "dictamen_de_la_asignatura", exigir_ok=True)
                    # R-E5: excluida por el tope declarado -> tope frente a tamaño admisible (M4 -> M2)
                    if corte_en is None and any("tope" in str(i.get("causa", "")) for i in r.get("items") or []):
                        agregar("M2", "capacidad", {"legajo": legajo}, "tope_frente_a_capacidad", exigir_ok=True,
                                foco=["tamano_base", "tamano_admisible", "tope_declarado", "ajustes",
                                      "advertencias_m2", "glosario_reglas", "lectura_guiada"])
                elif s.intencion == "capacidad" and r.get("ajustes") and corte_en is None and legajo:
                    # R-E4: recorte por capacidad -> ¿qué quedó fuera del plan? (M2 -> M4)
                    agregar("M4", "plan", {"legajo": legajo}, "excluidas_por_recorte",
                            foco=["excluidos", "periodo"], exigir_ok=True)
            pendientes = nuevas[agregadas_antes:]
            if not pendientes:
                break
        traza["enriquecimiento"] = reglas_aplicadas
        return nuevas

    # ------------------------------------------------------------------ 8. paquete y explicación
    def _paquete(self, texto: str, ctx: dict | None, secciones: list[Seccion], no_eval: list[dict]) -> dict:
        contexto = None
        if ctx:
            cortada = ctx.get("estado") == "cortada"
            contexto = limpiar_vacios({"estudiante": ctx.get("estudiante"), "periodo": ctx.get("periodo"),
                                       "estado_consulta": ctx.get("estado"), "corte_en": ctx.get("corte_en"),
                                       "causa_del_corte": CAUSA_CORTE.get(ctx.get("corte_en")) if cortada else None,
                                       "confiabilidad": ctx.get("confiabilidad"), "reserva": ctx.get("reserva")})
        paquete = {"pregunta": texto, "contexto": contexto or {}, "secciones": [s.para_llm() for s in secciones],
                   "no_evaluado": no_eval}
        parcial = escenario_parcial(secciones)
        if parcial:
            paquete["escenario_parcial"] = parcial
        return paquete

    def _explicar(self, paquete: dict) -> tuple[str, dict]:
        system = prompt_explicacion(self.cfg.ids_en_cuerpo)
        user = json.dumps(paquete, ensure_ascii=False, default=str, indent=1)
        borrador = preparar(texto_plano(self.llm.chat(system, user, max_tokens=4000)))
        fallas = verificar(borrador, paquete, self.cfg.ids_en_cuerpo)
        verif = {"intentos": [{"texto": borrador, "fallas": fallas}], "respaldo_deterministico": False}
        # El aviso de reserva no amerita una reescritura: si falta, lo agrega Python (M1, componer_respuesta)
        a_corregir = {k: v for k, v in fallas.items() if k != "reserva_omitida"}
        if not a_corregir:
            return self._con_aviso(borrador, fallas, paquete), verif
        user2 = (f"{user}\n\nBORRADOR_ANTERIOR:\n{borrador}\n\nCORRECCIÓN OBLIGATORIA: el borrador no pasó el control de "
                 f"fidelidad ({instruccion_correccion(a_corregir)}). Reescribí la respuesta completa corrigiendo solo "
                 "eso, sin agregar datos que no estén en las secciones.")
        respuesta = preparar(texto_plano(self.llm.chat(system, user2, max_tokens=4000)))
        fallas2 = verificar(respuesta, paquete, self.cfg.ids_en_cuerpo)
        verif["intentos"].append({"texto": respuesta, "fallas": fallas2})
        if hay_graves(fallas2):
            verif["respaldo_deterministico"] = True
            return resp_det.respaldo(paquete), verif
        verif["pendientes_leves"] = {k: v for k, v in fallas2.items() if k != "reserva_omitida"}
        return self._con_aviso(respuesta, fallas2, paquete), verif

    @staticmethod
    def _con_aviso(texto: str, fallas: dict, paquete: dict) -> str:
        if "reserva_omitida" in fallas:
            aviso = resp_det.aviso_reserva(paquete.get("contexto"))
            if aviso:
                return f"{texto}\n\n{aviso}"
        return texto

    # ------------------------------------------------------------------ 10. cierre
    def _fundamento(self, traza: dict, secciones: list[Seccion], no_eval: list[dict]) -> str:
        traza_id = traza["traza_id"]
        consulta_grafo = (traza.get("contexto") or {}).get("consulta")
        por_modulo: dict[str, set] = {}
        for s in secciones:
            por_modulo.setdefault("corte" if s.modulo == "X" else s.modulo, set()).update(s.reglas)
        for n in no_eval:
            por_modulo.setdefault("corte", set()).update({"X-01"} if "X-01" in n["motivo"] else {"X-02", "X-03"})
        partes = [f"{m} {', '.join(orden_natural(ids))}" for m, ids in
                  sorted(por_modulo.items(), key=lambda kv: ORDEN_MODULOS.get(kv[0], 0)) if ids]
        consultas = list(dict.fromkeys(s.consulta_id for s in secciones))
        nodo = f" — {consulta_grafo}" if consulta_grafo else ""   # id de la Consulta en el grafo (M1)
        return (f"Fundamento: {' · '.join(partes) or 'sin reglas registradas'}{nodo} — plantillas: "
                f"{', '.join(consultas)} — traza {traza_id}")

    def _cerrar(self, traza: dict, respuesta: str, flujo: str, secciones=None, no_eval=None) -> None:
        traza["flujo"] = flujo
        traza["respuesta"] = respuesta
        if secciones is not None:
            traza["fundamento"] = self._fundamento(traza, secciones, no_eval or [])
            traza["respuesta_completa"] = f"{respuesta}\n\n{traza['fundamento']}"
        else:
            traza["fundamento"] = None
            traza["respuesta_completa"] = respuesta

    def _guardar(self, traza: dict) -> None:
        self.trazas[traza["traza_id"]] = traza
        while len(self.trazas) > 200:
            self.trazas.popitem(last=False)
        try:
            self.cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cfg.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(traza, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass


def escenario_parcial(secciones: list[Seccion]) -> dict | None:
    """Corrección de la cátedra (E2E-04): con horas hipotéticas, M3 recalcula el riesgo de atraso, pero M2 y M4 siguen
    mostrando lo registrado para el escenario original. La diferencia tiene que quedar explícita en la respuesta:
    una simulación parcial no es una nueva evaluación completa de la trayectoria."""
    simuladas = [s for s in secciones if s.estado == "ok" and (s.resultado or {}).get("escenario_hipotetico")]
    registradas = sorted({s.modulo for s in secciones if s.estado == "ok" and s.modulo in ("M2", "M4")},
                         key=ORDEN_MODULOS.get)
    if not (simuladas and registradas):
        return None
    horas = simuladas[0].parametros.get("horas_hipoteticas")
    no_recalculado = [x for m in registradas for x in {"M2": ["la carga", "la capacidad"], "M4": ["el plan recomendado"]}[m]]
    lista = ", ".join(no_recalculado[:-1]) + " y " + no_recalculado[-1]
    return {"horas_hipoteticas": horas, "simulado": "el riesgo de atraso", "no_recalculado": no_recalculado,
            "aclaracion": (f"Solo el riesgo de atraso se simuló con {horas:g} horas semanales; {lista} corresponden "
                           "a tu situación registrada y no se recalcularon con esas horas.")}


def _json_de(crudo: str) -> str:
    """Tolera un bloque ```json``` o texto alrededor del objeto (M2); Pydantic hace el resto."""
    t = limpiar_texto(crudo).strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i >= 0 and j > i else t
