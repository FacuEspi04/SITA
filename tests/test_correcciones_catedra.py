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
