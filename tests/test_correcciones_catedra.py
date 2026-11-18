"""Regresión: observaciones de la cátedra sobre la entrega final de PG3 (17/11/2026).

1. E2E-05: el corte por X-01 (calidad del dato) se atribuía a la habilitación normativa.
2. E2E-02 / E2E-04: el desglose de la carga sumaba 24,25 h y el total era 31 h (faltaba la anual en curso).
3. E2E-04: con horas hipotéticas, carga y plan se mostraban sin aclarar que no se recalcularon.

Cada prueba usa el texto REAL que generó el LLM (logs/interacciones_pg3.jsonl) y comprueba que ahora el
verificador lo detecta, que una respuesta correcta pasa y que el orquestador entrega los datos que hacen falta.
"""
from fakes import CAP_JUAN, PLAN_JUAN, FakeKB, FakeLLM, config, enrutamiento

from sita import respaldo
from sita.modulos.m2 import desglose_carga, lectura_guiada
from sita.orquestador import Orquestador
from sita.verificacion import verificar

ITEMS_JUAN = [{"asignatura": "Tecnología para la Automatización", "horas_semanales": 6.75, "alcance": "cursar"},
              {"asignatura": "Inteligencia Artificial", "horas_semanales": 6.75, "alcance": "cursar"},
              {"asignatura": "Ciencia de Datos", "horas_semanales": 6.75, "alcance": "cursar"},
              {"asignatura": "Simulación", "horas_semanales": 4.0, "alcance": "rendir"}]
CAP_JUAN_COMPLETA = {**CAP_JUAN, "items_evaluados": ITEMS_JUAN, "carga_anuales_en_curso_h": 6.75}
RIESGO_JUAN_9H = {"escenario_hipotetico": True, "riesgo_atraso": {"etiqueta": "alto", "valor": 0.664},
                  "riesgo_registrado_en_PG2": {"etiqueta": "medio", "valor": 0.505},
                  "capacidad_disponible": {"horas_hipoteticas": 9.0}}


def orq(tmp_path, rutas, explicaciones, kb=None):
    return Orquestador(kb or FakeKB(), FakeLLM(rutas, explicaciones), config(tmp_path))


# ------------------------------------------------------------------ 1. E2E-05: causa del corte
T_SOFIA = "Soy Sofía Molina, legajo 48301. Armame el plan y decime si tengo riesgo de atrasarme."
R_SOFIA = {T_SOFIA: enrutamiento("48301", "Sofía Molina", [("M4", "plan", [], None), ("M3", "riesgo_atraso", [], None)])}
MALA_SOFIA = ("No, todavía no podés armar el plan ni saber si tenés riesgo de atraso porque la consulta está cortada. "
              "El sistema detuvo el proceso porque la información de tu historia académica es antigua (18 meses) y la "
              "confiabilidad quedó calificada como baja (0,244). Tanto el cálculo del riesgo de atraso como la generación "
              "del plan quedaron sin evaluar porque la regla que controla la habilitación normativa no pudo aplicarse sin "
              "esos datos actualizados. Tu historia académica puede no estar al día: confirmalo con el asesor académico.")
BUENA_SOFIA = ("Todavía no puedo armarte el plan ni evaluar tu riesgo de atraso: la consulta se detuvo porque tu historia "
               "académica no se actualiza hace unos 18 meses y su confiabilidad es baja. No es una falta de correlativas: "
               "cuando actualices la historia, volvé a consultar. Tu historia académica puede no estar al día, así que "
               "conviene confirmarlo con el asesor académico.")


def test_e2e05_corte_atribuido_a_la_habilitacion_se_detecta(tmp_path):
    t = orq(tmp_path, R_SOFIA, [MALA_SOFIA, MALA_SOFIA]).procesar(T_SOFIA)
    assert "causa_de_corte" in t["verificacion"]["intentos"][0]["fallas"]
    assert t["verificacion"]["respaldo_deterministico"]          # el error persiste: responde el respaldo
    assert "habilitación normativa" not in t["respuesta"]


def test_e2e05_respuesta_correcta_pasa(tmp_path):
    t = orq(tmp_path, R_SOFIA, [BUENA_SOFIA]).procesar(T_SOFIA)
    assert t["verificacion"]["intentos"][0]["fallas"] == {}


def test_e2e05_el_motivo_y_el_contexto_nombran_la_causa_real(tmp_path):
    t = orq(tmp_path, R_SOFIA, [BUENA_SOFIA]).procesar(T_SOFIA)
    for n in t["no_evaluado"]:
        assert "X-01" in n["motivo"] and "habilitación" not in n["motivo"]
    assert "calidad del dato" in t["paquete_llm"]["contexto"]["causa_del_corte"]
    assert "X-01" in t["fundamento"]
    assert verificar(respaldo.respaldo(t["paquete_llm"]), t["paquete_llm"]).get("causa_de_corte") is None


def test_e2e05_negar_las_correlativas_no_es_atribuirles_el_corte():
    p = {"contexto": {"corte_en": "M1", "estado_consulta": "cortada"}, "secciones": [], "no_evaluado": []}
    assert verificar("No se evaluó tu plan porque tus datos están desactualizados, no por las correlativas.", p) \
        .get("causa_de_corte") is None
    assert verificar("La consulta se cortó en la habilitación normativa.", p).get("causa_de_corte")
    assert verificar("No pude evaluar tu riesgo porque te faltan correlativas.", p).get("causa_de_corte")


# ------------------------------------------------------------------ 2. E2E-02 / E2E-04: desglose de la carga
def paquete_m2(resultado, **extra):
    return {"pregunta": "", "contexto": {}, "no_evaluado": [], **extra,
            "secciones": [{"modulo": "M2", "tipo_decision": "carga_y_capacidad_M2", "resultado": resultado}]}


def test_m2_desglose_de_la_carga_suma_el_total():
    d = desglose_carga(CAP_JUAN_COMPLETA)
    assert d == {"asignaturas_del_periodo_h": 24.25, "anuales_en_curso_h": 6.75, "total_h": 31.0}
    lectura = " ".join(lectura_guiada({**CAP_JUAN_COMPLETA, "desglose_carga": d}))
    assert "24,25 h" in lectura and "6,75 h semanales de asignaturas anuales en curso" in lectura
    # si los componentes no cierran con el total, no se informa un desglose falso
    assert desglose_carga({**CAP_JUAN_COMPLETA, "carga_h": 35.0}) is None
    assert desglose_carga({**CAP_JUAN_COMPLETA, "carga_anuales_en_curso_h": None}) is None


def test_e2e02_desglose_sin_la_anual_en_curso_se_detecta():
    r = {**CAP_JUAN_COMPLETA, "desglose_carga": desglose_carga(CAP_JUAN_COMPLETA)}
    p = paquete_m2(r)
    mala = ("En cuanto a la carga, tenés 31 h semanales asignadas (6,75 h de Tecnología para la Automatización, 6,75 h "
            "de Inteligencia Artificial, 6,75 h de Ciencia de Datos y 4 h de Simulación), mientras que tu capacidad es "
            "de 25 h, lo que genera una holgura negativa de -6 h.")
    assert "desglose_incompleto" in verificar(mala, p)
    mala_e2e04 = ("En el período actual tenés cuatro materias asignadas: Tecnología para la Automatización, Inteligencia "
                  "Artificial y Ciencia de Datos, cada una con 6,75 h semanales, y Simulación con 4 h para rendir. La "
                  "carga total es 31 h.")
    assert "desglose_incompleto" in verificar(mala_e2e04, p)
    buena = ("Tu carga es de 31 h semanales: 6,75 h de Tecnología para la Automatización, 6,75 h de Inteligencia "
             "Artificial, 6,75 h de Ciencia de Datos y 4 h de Simulación, más 6,75 h de asignaturas anuales en curso.")
    assert "desglose_incompleto" not in verificar(buena, p)
    solo_total = "Tu carga es de 31 h semanales y tu capacidad de 25 h: la holgura es negativa (-6 h)."
    assert "desglose_incompleto" not in verificar(solo_total, p)


# ------------------------------------------------------------------ 3. E2E-04: escenario hipotético parcial
T_JUAN_9H = ("Legajo 47890. Si solo pudiera dedicarle 9 horas por semana a la facultad, ¿cómo cambia mi riesgo de "
             "atraso? ¿Y cuánta carga tengo hoy?")
R_JUAN_9H = {T_JUAN_9H: enrutamiento("47890", None, [("M3", "riesgo_atraso", [], None), ("M2", "capacidad", [], None)],
                                     horas=9)}
MALA_JUAN_9H = ("No, el riesgo de atraso sube a alto cuando solo podés dedicar 9 h semanales; hoy tenés una carga de "
                "31 h. Tu capacidad es de 25 h, lo que genera una holgura negativa de -6 h y un riesgo de sobrecarga alto. "
                "Por esa razón el plan se recortó a tres materias. En la simulación con 9 h tu riesgo de atraso pasaría de "
                "medio a alto.")
BUENA_JUAN_9H = ("En la simulación con 9 horas semanales, tu riesgo de atraso pasaría de medio a alto. Esa simulación "
                 "solo cambia el riesgo de atraso: tu carga de 31 h, tu capacidad de 25 h y el plan son los de tu "
                 "situación registrada y no se recalcularon con esas horas. Hoy la holgura es negativa (-6 h) y el riesgo "
                 "de sobrecarga es alto.")


class KBJuan9h(FakeKB):
    def _valor(self, nombre, p):
        if nombre == "M3_Q5_RIESGO_SIMULADO" and p.get("legajo") == "47890" and p.get("horas_hipoteticas") == 9:
            return RIESGO_JUAN_9H
        if nombre == "M2_CAPACIDAD" and p.get("legajo") == "47890":
            return CAP_JUAN_COMPLETA
        return super()._valor(nombre, p)


def test_e2e04_carga_y_plan_sin_aclarar_que_no_se_recalcularon_se_detecta():
    p = paquete_m2(CAP_JUAN_COMPLETA, escenario_parcial={"aclaracion": "..."})
    p["secciones"].append({"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": RIESGO_JUAN_9H})
    assert "escenario_parcial" in verificar(MALA_JUAN_9H, p)
    assert "escenario_parcial" not in verificar(BUENA_JUAN_9H, p)
    # sin la marca del orquestador (no hay simulación), el control no se aplica
    del p["escenario_parcial"]
    assert "escenario_parcial" not in verificar(MALA_JUAN_9H, p)


def test_e2e04_el_orquestador_avisa_y_el_respaldo_lo_aclara(tmp_path):
    t = orq(tmp_path, R_JUAN_9H, [MALA_JUAN_9H, MALA_JUAN_9H], kb=KBJuan9h()).procesar(T_JUAN_9H)
    parcial = t["paquete_llm"]["escenario_parcial"]
    assert parcial["horas_hipoteticas"] == 9 and "la carga" in parcial["no_recalculado"]
    assert "no se recalcularon" in parcial["aclaracion"]
    assert "escenario_parcial" in t["verificacion"]["intentos"][0]["fallas"]
    assert t["verificacion"]["respaldo_deterministico"]
    assert "no se recalcularon" in t["respuesta"]


def test_e2e04_respuesta_correcta_pasa(tmp_path):
    t = orq(tmp_path, R_JUAN_9H, [BUENA_JUAN_9H], kb=KBJuan9h()).procesar(T_JUAN_9H)
    assert t["verificacion"]["intentos"][0]["fallas"] == {}   # «de medio a alto»: medio es el riesgo registrado


def test_sin_horas_hipoteticas_no_hay_aviso_de_escenario_parcial(tmp_path):
    texto = "Soy Juan Pérez, legajo 47890. ¿Cuánta carga tengo y qué me conviene cursar?"
    rutas = {texto: enrutamiento("47890", "Juan Pérez", [("M2", "capacidad", [], None), ("M4", "plan", [], None)])}
    t = orq(tmp_path, rutas, ["Tu carga es de 31 h y tu capacidad de 25 h."]).procesar(texto)
    assert "escenario_parcial" not in t["paquete_llm"]
    assert PLAN_JUAN["excluidos"]  # el plan sigue disponible sin simulación


# ------------------------------------------------------------------ segunda revisión (corrida en Render, 17/11)
CAP_JUAN_CON_NOMBRES = {**CAP_JUAN_COMPLETA, "anuales_en_curso": ["Proyecto Final"]}
DESGLOSE_SIN_NOMBRE = (
    "En el período 2027-2C tenés cuatro asignaturas evaluadas: Tecnología para la Automatización 6,75 h, Inteligencia "
    "Artificial 6,75 h, Ciencia de Datos 6,75 h (las tres para cursar) y Simulación 4,0 h (para rendir). Ese conjunto "
    "aporta 24,25 h. A esas se añaden 6,75 h de las asignaturas anuales que continúan, llegando al total de 31 h.")


def test_m2_desglose_y_lectura_nombran_la_anual_en_curso():
    d = desglose_carga(CAP_JUAN_CON_NOMBRES)
    assert d["anuales_en_curso"] == ["Proyecto Final"]
    lectura = " ".join(lectura_guiada({**CAP_JUAN_CON_NOMBRES, "desglose_carga": d}))
    assert "6,75 h semanales de la asignatura anual en curso Proyecto Final" in lectura


def test_e2e02_desglose_que_no_nombra_la_anual_se_detecta():
    p = paquete_m2({**CAP_JUAN_CON_NOMBRES, "desglose_carga": desglose_carga(CAP_JUAN_CON_NOMBRES)})
    fallas = verificar(DESGLOSE_SIN_NOMBRE, p)
    assert "desglose_incompleto" in fallas and "Proyecto Final" in fallas["desglose_incompleto"][0]
    buena = DESGLOSE_SIN_NOMBRE.replace("de las asignaturas anuales que continúan", "de Proyecto Final, anual en curso")
    assert "desglose_incompleto" not in verificar(buena, p)
    assert "desglose_incompleto" not in verificar("Tu carga es de 31 h semanales y tu capacidad de 25 h.", p)


def paquete_rendir_ia(**extra_m1):
    return {"pregunta": "", "contexto": {}, "no_evaluado": [], "secciones": [
        {"modulo": "M1", "tipo_decision": "habilitacion_normativa_M1", "resultado": {
            "asignatura": {"nombre": "Inteligencia Artificial", "estado_en_historia": "pendiente (sin registro)"},
            "alcance_consultado": "rendir", "sin_dictamen": "...", **extra_m1,
            "advertencias": [{"tipo": "cursa_sin_rendir",
                              "mensaje": "Puede cursar Inteligencia Artificial pero no rendirla hasta aprobar Simulación"}]}}]}


def test_e2e02_regularizar_la_correlativa_en_el_cierre_se_detecta():
    p = paquete_rendir_ia()
    mala = ("Podés cursar Inteligencia Artificial, pero no podés rendir el final hasta que apruebes Simulación. "
            "Si necesitás confirmar algún dato o gestionar la regularización de Simulación, podés consultar al asesor "
            "académico.")
    assert "requisito_para_rendir" in verificar(mala, p)
    buena = ("Podés cursar Inteligencia Artificial, pero no podés rendir el final hasta que apruebes Simulación; no "
             "alcanza con regularizar Simulación. Si tenés dudas, consultá al asesor académico.")
    assert "requisito_para_rendir" not in verificar(buena, p)


def test_regularizar_la_correlativa_es_valido_si_un_dictamen_lo_exige():
    # Caso Lucía: la regularidad de Simulación venció y un bloqueo exige regularizarla para cursar.
    p = paquete_rendir_ia()
    p["secciones"].append({"modulo": "M1", "tipo_decision": "habilitacion_normativa_M1", "resultado": {
        "asignatura": {"nombre": "Sistemas de Gestión"}, "alcance_consultado": "cursar",
        "dictamen": {"tipo": "BloqueoDirecto", "causas": [
            {"correlatividad": "28-27-REG", "tipo": "regularidad", "asignatura": "Simulación"}]}}})
    texto = ("Para cursar Sistemas de Gestión tenés que regularizar Simulación. Para rendir el final de Inteligencia "
             "Artificial tenés que aprobar Simulación.")
    assert "requisito_para_rendir" not in verificar(texto, p)


# ------------------------------------------------------------------ tercera revisión (resto de la corrida en Render)
from sita.modulos.m1 import factores_confiabilidad  # noqa: E402
from sita.modulos.m2 import composicion_capacidad  # noqa: E402

PARAMS = [{"id": "dedicacion_total_sostenible", "valor": 55.0, "estado": "supuesto"},
          {"id": "factor_estudio", "valor": 0.5, "estado": "supuesto"},
          {"id": "horas_preparacion_final", "valor": 4.0, "estado": "supuesto"}]
CAP_JUAN_PARAMS = {**CAP_JUAN_COMPLETA, "horas_trabajo_semanales": 30, "capacidad_h": 25.0, "parametros_capacidad": PARAMS}


def test_m2_explica_de_donde_sale_la_capacidad_y_que_es_un_supuesto():
    c = composicion_capacidad(CAP_JUAN_PARAMS)
    assert c["dedicacion_sostenible_h"] == 55.0 and c["horas_trabajo_h"] == 30
    lectura = " ".join(lectura_guiada({**CAP_JUAN_PARAMS, "composicion_capacidad": c}))
    assert "dedicación semanal sostenible (55 h" in lectura and "menos tus horas de trabajo (30 h)" in lectura
    assert "no cambia la capacidad" in lectura and "supuestos del modelo" in lectura
    assert "si se detallan" not in lectura                     # la instrucción al LLM ya no viaja en los datos
    assert composicion_capacidad({**CAP_JUAN_PARAMS, "capacidad_h": 20.0}) is None   # no cierra: no se informa


def test_capacidad_atribuida_al_ajuste_se_detecta():
    p = paquete_m2(CAP_JUAN_PARAMS)
    mala = ("Tu capacidad es de 25 horas semanales porque se calculó restando un ajuste por sobrecarga a la capacidad "
            "base. El riesgo de sobrecarga se evaluó como alto, lo que activó una reducción de una unidad en la capacidad "
            "disponible.")
    fallas = verificar(mala, p)
    assert len(fallas["causa_de_capacidad"]) == 2
    buena = ("Tu capacidad es de 25 h: es la dedicación semanal sostenible de 55 h menos tus 30 h de trabajo. Como la "
             "carga supera la capacidad, por eso se aplicó un ajuste por sobrecarga que recortó el plan. El ajuste no "
             "cambia tu capacidad.")
    assert "causa_de_capacidad" not in verificar(buena, p)


def test_martina_certeza_inventada_se_detecta():
    mala = ("El riesgo de atraso que te calcularon es alto y, según los datos, tiene un nivel de certeza alto. La "
            "confiabilidad de la información es alta (0,778), por lo que podés considerarlo bastante fiable.")
    assert len(verificar(mala, {"secciones": [], "contexto": {}}).get("certeza_inventada", [])) == 2
    buena = ("Tu riesgo de atraso es alto (0,721): es un grado entre 0 y 1, no una certeza. Los datos de tu historia "
             "son confiables, pero los criterios del cálculo todavía están en revisión. Podés cursar Seguridad en los "
             "Sistemas de Información más adelante; no hay certeza de que el riesgo se mantenga.")
    assert "certeza_inventada" not in verificar(buena, {"secciones": [], "contexto": {}})


HIST_SOFIA = {"historia": {"inconsistencias": 0, "antiguedad_meses": 18.14, "completitud": 0.917},
              "mediciones_m1": [{"etiqueta": "antigua", "valor": 18.136, "variable": "antiguedad_meses"},
                                {"etiqueta": "alta", "valor": 0.917, "variable": "completitud"}],
              "confiabilidad": {"etiqueta": "baja", "valor": 0.244}}


def test_sofia_completitud_alta_presentada_como_causa_se_detecta():
    f = factores_confiabilidad(HIST_SOFIA)
    assert f["desfavorables"] == ["antiguedad_meses"] and f["favorables"] == ["completitud"]
    assert "es favorable y no es la causa" in f["explicacion"]
    p = {"contexto": {}, "secciones": [{"modulo": "M1", "resultado": {**HIST_SOFIA, "factores_confiabilidad": f}}]}
    mala = ("La consulta se cortó porque la historia académica que figura está desactualizada (tiene 18 meses de "
            "antigüedad) y la completitud es solo 0,92, lo que da una confiabilidad baja (0,244).")
    assert "factor_de_confiabilidad" in verificar(mala, p)
    buena_real = ("En el módulo que pediste, el sistema constató que la antigüedad de la información es de 18,14 meses "
                  "y que la completitud es 0,917; con esos valores la confiabilidad quedó etiquetada como baja.")
    assert "factor_de_confiabilidad" not in verificar(buena_real, p)
    # el respaldo explica la causa real
    assert "antigüedad" in respaldo.respaldo(p) and "no es la causa" in respaldo.respaldo(p)


def test_e2e04_borradores_correctos_ya_no_se_rechazan():
    p = paquete_m2(CAP_JUAN_COMPLETA, escenario_parcial={"aclaracion": "..."})
    p["secciones"].append({"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": RIESGO_JUAN_9H})
    borrador2 = ("Con 9 horas semanales tu riesgo de atraso pasa a alto (valor 0,664), mientras que antes estaba en "
                 "medio (valor 0,505). En tu situación actual la carga total es de 31 h semanales. La simulación con "
                 "9 h semanales se realizó solo para el riesgo de atraso; la carga, la capacidad y el plan recomendado "
                 "siguen siendo los que aparecen registrados.")
    assert "escenario_parcial" not in verificar(borrador2, p)


def test_e2e04_suma_atribuida_solo_al_periodo_se_detecta():
    p = paquete_m2({**CAP_JUAN_COMPLETA, "desglose_carga": desglose_carga(CAP_JUAN_COMPLETA)})
    mala = ("En cuanto a la carga y capacidad, la suma de las materias que debés cursar (Tecnología para la "
            "Automatización, Inteligencia Artificial, Ciencia de Datos y Simulación) da 31 h, superando la capacidad.")
    assert "desglose_incompleto" in verificar(mala, p)


def test_respaldo_no_muestra_ids_ni_instrucciones():
    r = {**CAP_JUAN_PARAMS, "riesgo_sobrecarga": {"etiqueta": "alto", "valor": 0.77,
                                                  "reglas": [{"regla": "RS1", "alfa": 0.8}]}}
    r["desglose_carga"] = desglose_carga(r)
    r["composicion_capacidad"] = composicion_capacidad(r)
    r["lectura_guiada"] = lectura_guiada(r)
    texto = respaldo.respaldo(paquete_m2(r))
    assert "RS1" not in texto and "si se detallan" not in texto and "Riesgo de sobrecarga: alto" in texto


def test_alcance_como_nombre_de_campo_es_jerga():
    fallas = verificar("Inteligencia Artificial: 6,75 h/semana (alcance cursar).", {"secciones": [], "contexto": {}})
    assert any("alcance cursar" in x for x in fallas.get("jerga", []))


T_JUAN_9H_PLAN = "Legajo 47890, si tuviera solo 9 horas por semana, ¿qué me conviene cursar y cuántas materias puedo llevar?"


def test_horas_hipoteticas_sin_pedido_de_riesgo_agregan_la_simulacion(tmp_path):
    rutas = {T_JUAN_9H_PLAN: enrutamiento("47890", None, [("M4", "plan", [], None), ("M2", "capacidad", [], None)],
                                          horas=9)}
    t = orq(tmp_path, rutas, [BUENA_JUAN_9H], kb=KBJuan9h()).procesar(T_JUAN_9H_PLAN)
    sim = [p for p in t["pedidos_resueltos"] if p["intencion"] == "riesgo_atraso"]
    assert sim and sim[0]["horas_hipoteticas"] == 9
    assert "escenario_parcial" in t["paquete_llm"]
    assert any("se agrega la simulación" in c for c in t.get("correcciones", []))


# ------------------------------------------------------------------ cuarta revisión (Render tras el despliegue de C-63)
def test_e2e04_riesgo_eliptico_con_el_valor_de_la_sobrecarga_se_detecta():
    p = paquete_m2(CAP_JUAN_COMPLETA, escenario_parcial={"aclaracion": "..."})
    p["secciones"].append({"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": RIESGO_JUAN_9H})
    mala = ("El riesgo de atraso se simuló con 9 h semanales de estudio: bajo esa hipótesis el riesgo pasa a ser alto "
            "(grado 0,77). Tené en cuenta que solo el riesgo de atraso se simuló con 9 h; la carga, la capacidad y el "
            "plan siguen basados en tu situación actual.")
    fallas = verificar(mala, p)
    assert "magnitudes_cruzadas" in fallas
    assert "escenario_parcial" not in fallas          # «siguen basados en tu situación actual» es una aclaración válida
    buena = "El riesgo de atraso se simuló con 9 h: bajo esa hipótesis el riesgo pasa a ser alto (grado 0,664)."
    assert "magnitudes_cruzadas" not in verificar(buena, p)


def test_martina_ruta_critica_presentada_como_claves_se_detecta():
    r = {"riesgo_atraso": {"etiqueta": "alto", "valor": 0.721},
         "ruta_critica": ["Sistemas Operativos", "Redes de Datos", "Seguridad en los Sistemas de Información"],
         "asignaturas_llave": [{"asignatura": "Sistemas Operativos", "grado_llave": 0.641},
                               {"asignatura": "Diseño de Sistemas de Información", "grado_llave": 1.0}],
         "arrastres": [{"asignatura": "Sistemas Operativos", "grado_llave": 0.641}]}
    p = {"contexto": {}, "secciones": [{"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": r}]}
    mala = ("La ruta crítica incluye “Sistemas Operativos”, “Redes de Datos” y “Seguridad en los Sistemas de "
            "Información”, y esas asignaturas aparecen como claves en tu trayectoria.")
    fallas = verificar(mala, p)
    assert "llave_inventada" in fallas and "redes de datos" in fallas["llave_inventada"][0]
    buena = ("Tu ruta crítica pasa por Sistemas Operativos, Redes de Datos y Seguridad en los Sistemas de Información; "
             "de ellas, solo Sistemas Operativos es una materia llave.")
    assert "llave_inventada" not in verificar(buena, p)


def test_otra_asignatura_como_sujeto_de_llave_no_es_falso_positivo():
    r = {"ruta_critica": ["Sistemas Operativos", "Redes de Datos", "Seguridad en los Sistemas de Información"],
         "asignaturas_llave": [{"asignatura": "Sistemas Operativos"}, {"asignatura": "Análisis Numérico"}]}
    p = {"contexto": {}, "secciones": [{"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": r}]}
    texto = ("Ya tenés una ruta crítica formada por Sistemas Operativos, Redes de Datos y Seguridad en los Sistemas de "
             "Información, y que Análisis Numérico figura como asignatura llave con grado 0,641.")
    assert "llave_inventada" not in verificar(texto, p)


# ------------------------------------------------------------------ quinta revisión (Render, tras C-64 a C-66)
from sita.modulos.m3 import causa_del_riesgo  # noqa: E402

RIESGO_MARTINA = {
    "riesgo_atraso": {"etiqueta": "alto", "valor": 0.721, "grados": {"bajo": 0.0, "medio": 0.211, "alto": 0.641}},
    "reglas_difusas": [
        {"id": "E-08d", "estado": "candidata", "alfa": 0.641, "consecuente": "alto",
         "enunciado": "SI criticidad del arrastre ES alta ENTONCES riesgo_atraso ES alto"},
        {"id": "E-12d", "estado": "candidata", "alfa": 0.211, "consecuente": "medio",
         "enunciado": "SI criticidad del arrastre ES baja O media ENTONCES riesgo_atraso ES medio"}],
    "arrastres": [{"asignatura": "Sistemas Operativos", "grado_llave": 0.641}],
    "ruta_critica": ["Sistemas Operativos", "Redes de Datos", "Seguridad en los Sistemas de Información"],
    "cuellos_de_botella": [{"asignatura": "Diseño de Sistemas de Información", "proporcion": 0.667}],
    "asignaturas_llave": [{"asignatura": "Sistemas Operativos", "grado_llave": 0.641}]}


def test_m3_causa_del_riesgo_es_el_arrastre():
    c = causa_del_riesgo(RIESGO_MARTINA)
    assert c["arrastres"] == ["Sistemas Operativos"] and c["grado"] == 0.641
    assert "la criticidad del arrastre de Sistemas Operativos" in c["explicacion"]
    assert "no son entradas de este cálculo" in c["explicacion"]


def test_martina_riesgo_atribuido_a_la_ruta_critica_se_detecta():
    r = {**RIESGO_MARTINA, "causa_del_riesgo": causa_del_riesgo(RIESGO_MARTINA)}
    p = {"contexto": {}, "secciones": [{"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": r}]}
    mala = ("Ese riesgo se apoya en la ruta crítica de asignaturas pendientes —Sistemas Operativos, Redes de Datos y "
            "Seguridad en los Sistemas de Información— y en los cuellos de botella detectados.")
    assert "causa_del_riesgo" in verificar(mala, p)
    buena = ("Tu riesgo de atraso es alto porque arrastrás Sistemas Operativos, una materia llave con criticidad alta. "
             "La ruta crítica pasa por Sistemas Operativos, Redes de Datos y Seguridad en los Sistemas de Información, "
             "pero no es la causa del riesgo.")
    assert "causa_del_riesgo" not in verificar(buena, p)
    assert "arrastre de Sistemas Operativos" in respaldo.respaldo(p)


def test_e2e04_abrir_con_el_plan_registrado_ante_la_hipotesis_se_detecta():
    p = paquete_m2(CAP_JUAN_COMPLETA, escenario_parcial={"aclaracion": "..."})
    p["secciones"].append({"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": RIESGO_JUAN_9H})
    mala = ("Sí, podés llevar tres materias: Simulación (para rendir) y, como cursadas, Tecnología para la Automatización "
            "e Inteligencia Artificial. Recordá que la simulación solo afectó al riesgo de atraso; la carga, la capacidad "
            "y el plan recomendado siguen basados en tu situación registrada.")
    assert "escenario_parcial" in verificar(mala, p)
    buena = ("Con 9 horas no se recalculó cuántas materias podés llevar: el plan de 3 materias corresponde a tu situación "
             "registrada. En la simulación, tu riesgo de atraso pasaría de medio a alto. La carga, la capacidad y el plan "
             "siguen basados en tu situación registrada.")
    assert "escenario_parcial" not in verificar(buena, p)


def test_etiqueta_y_valor_como_campos_son_jerga():
    fallas = verificar("La confiabilidad es alta (etiqueta alta, valor 0,778).", {"secciones": [], "contexto": {}})
    assert any("etiqueta alta" in x for x in fallas.get("jerga", []))
    assert "jerga" not in verificar("El riesgo está etiquetado como alto.", {"secciones": [], "contexto": {}})


# ------------------------------------------------------------------ sexta revisión (Render 18/11, tras C-67)
RIESGO_JUAN_9H_REAL = {
    "escenario_hipotetico": True,
    "riesgo_atraso": {"etiqueta": "alto", "valor": 0.664, "grados": {"bajo": 0.0, "medio": 0.304, "alto": 0.717}},
    "riesgo_registrado_en_PG2": {"etiqueta": "medio", "valor": 0.505},
    "reglas_difusas": [
        {"id": "E-12d", "alfa": 1.0, "consecuente": "medio",
         "enunciado": "SI criticidad del arrastre ES baja O media ENTONCES riesgo_atraso ES medio"},
        {"id": "E-09d", "alfa": 0.781, "consecuente": "alto",
         "enunciado": "SI hay arrastre Y proximidad ES (inminente O cercana) Y capacidad ES baja ENTONCES riesgo_atraso ES alto"}],
    "arrastres": None,
    "entradas_inferencia": {"peor_arrastre": "Tecnología para la Automatización", "arrastre": 1.0, "criticidad_alta": 0.018,
                            "meses_regularidad_mas_proxima": 4.205, "capacidad_baja": 0.926},
    "capacidad_disponible": {"horas_hipoteticas": 9.0, "horas_registradas": 25.0}}


def test_m3_causa_en_la_simulacion_usa_las_entradas_de_la_regla():
    c = causa_del_riesgo(RIESGO_JUAN_9H_REAL)
    assert c["grado"] == 0.781
    assert "que arrastrás Tecnología para la Automatización" in c["explicacion"]
    assert "criticidad" not in c["explicacion"]            # E-09d usa «hay arrastre», no su criticidad (0,018)
    assert "(4,2 meses)" in c["explicacion"] and "(9 h semanales en la simulación)" in c["explicacion"]


def test_e2e04_aclaracion_en_la_misma_oracion_que_el_plan_no_es_falso_positivo():
    p = paquete_m2(CAP_JUAN_COMPLETA, escenario_parcial={"aclaracion": "..."})
    p["secciones"].append({"modulo": "M3", "tipo_decision": "riesgo_de_atraso_M3", "resultado": RIESGO_JUAN_9H})
    borrador2 = ("Podés cursar hasta tres materias, pero con solo 9 h semanales solo se simuló el riesgo de atraso; la "
                 "carga, la capacidad y el plan recomendado siguen siendo los de tu situación registrada, así que no se "
                 "puede confirmar cuántas materias podrías cargar sin sobrecarga.")
    assert "escenario_parcial" not in verificar(borrador2, p)


def test_respaldo_con_escenario_parcial_empieza_por_la_aclaracion():
    p = paquete_m2({**CAP_JUAN_COMPLETA, "lectura_guiada": ["La holgura es negativa (-6 h)."]},
                   escenario_parcial={"aclaracion": "Solo el riesgo de atraso se simuló con 9 horas semanales."})
    assert respaldo.respaldo(p).startswith("Solo el riesgo de atraso se simuló")


def test_martina_confiabilidad_del_calculo_se_detecta():
    mala = ("El riesgo de atraso es alto y la confiabilidad del cálculo es alta (valor 0,778). La regla que produce el "
            "riesgo está en revisión, por lo que el valor podría variar ligeramente.")
    assert len(verificar(mala, {"secciones": [], "contexto": {}}).get("certeza_inventada", [])) == 2
    buena = ("Tu riesgo de atraso es alto. Los datos de tu historia académica tienen una confiabilidad alta (0,778), "
             "pero el criterio que calcula el riesgo todavía está en revisión.")
    assert "certeza_inventada" not in verificar(buena, {"secciones": [], "contexto": {}})
