"""Regresión: errores REALES de la primera corrida de `sita --demo` contra la base (12/11/2026).

Cada prueba usa el texto que generó gpt-oss-120b y comprueba que ahora el verificador lo detecta
(o, en los falsos positivos, que ya no lo marca).
"""
from fakes import FakeKB, FakeLLM, config, enrutamiento

from sita.modulos.base import Seccion
from sita.modulos.m1 import _sin_contexto
from sita.orquestador import Orquestador
from sita.verificacion import verificar


def paquete(*secciones, contexto=None):
    return {"pregunta": "", "contexto": contexto or {}, "no_evaluado": [],
            "secciones": [{"modulo": m, "tipo_decision": t, "resultado": r} for m, t, r in secciones]}


def test_valentina_fisica_ii_aprobada_sin_dictamen():
    crudo = {"asignatura": {"codigo": 10, "nombre": "Física II", "estado_en_historia": "aprobada"},
             "alcance_consultado": "cursar", "dictamen": None, "advertencias": [],
             "correlativas_de_la_asignatura": [{"tipo": "regularidad", "asignatura": "Física I",
                                                "estado_estudiante": "pendiente (sin registro)"}]}
    r = _sin_contexto(crudo)
    assert "sin_dictamen" in r and "correlativas_de_la_asignatura" not in r
    p = paquete(("M1", "habilitacion_normativa_M1", r))
    mala = ("No, no podés cursar Física II y no puedo decirte cuántas materias podés llevar. Para cursar Física II "
            "necesitás tener regularizadas las correlativas; Física I está pendiente.")
    assert "sin_dictamen" in verificar(mala, p)
    buena = "Física II ya la tenés aprobada, así que no hay nada que habilitar para cursarla."
    assert "sin_dictamen" not in verificar(buena, p)


def test_juan_escenario_hipotetico_presentado_como_situacion_actual():
    p = paquete(("M3", "riesgo_de_atraso_M3", {"escenario_hipotetico": True,
                                               "riesgo_atraso": {"etiqueta": "alto", "valor": 0.664},
                                               "riesgo_registrado_en_PG2": {"etiqueta": "medio", "valor": 0.505}}))
    mala = "Tu riesgo de atraso sigue siendo alto (valor 0,664) incluso si solo podés dedicar 9 horas semanales."
    assert "escenario_hipotetico" in verificar(mala, p)
    buena = "En la simulación con 9 horas semanales, tu riesgo de atraso pasaría de medio (0,505) a alto (0,664)."
    assert "escenario_hipotetico" not in verificar(buena, p)


def test_tomas_confiabilidad_inventada_y_jerga():
    p = paquete(("M1", "calidad_del_dato_M1", {"historia": {"inconsistencias": 2}, "regla_corte": {"id": "X-01"}}))
    mala = "La confiabilidad del dato se considera baja y la condición está bajo supuesto, así que conviene verificarlo."
    f = verificar(mala, p)
    assert "etiqueta_inventada" in f and "jerga" in f


def test_martina_empate_y_lenguaje_de_probabilidad():
    p = paquete(("M4", "recomendacion_planificacion_M4",
                 {"items": [{"decision": "excluida", "asignatura": "Análisis Numérico", "causa": "tope declarado",
                             "empate_persistente": True}]}),
                ("M3", "riesgo_de_atraso_M3", {"riesgo_atraso": {"etiqueta": "alto", "valor": 0.721}}))
    mala = ("El plan excluye Análisis Numérico porque el tope declarado es 2 y ya hay otras asignaturas con mayor grado "
            "de llave. El riesgo de atraso es alto, lo que indica que es probable que te retrases.")
    f = verificar(mala, p)
    assert "causa_de_exclusion" in f and "porcentaje_o_probabilidad" in f


def test_juan_rendir_ia_exige_aprobar_no_regularizar():
    p = paquete(("M1", "habilitacion_normativa_M1",
                 {"asignatura": {"nombre": "Inteligencia Artificial", "estado_en_historia": "pendiente (sin registro)"},
                  "alcance_consultado": "rendir", "sin_dictamen": "...",
                  "advertencias": [{"tipo": "cursa_sin_rendir", "mensaje": "Puede cursar IA pero no rendirla hasta aprobar Simulación"}]}))
    assert "requisito_para_rendir" in verificar("No podés rendir el final hasta que regularices Simulación.", p)
    assert "requisito_para_rendir" not in verificar("Podés cursarla, pero para rendir el final primero tenés que aprobar Simulación.", p)


def test_falsos_positivos_de_la_demo_ya_no_se_marcan():
    ana = paquete(("M3", "riesgo_de_atraso_M3", {"riesgo_atraso": {"etiqueta": "bajo", "valor": 0.198}}))
    assert verificar("Tu riesgo de atraso es bajo (0,198); ese valor no debe interpretarse como una probabilidad.", ana) == {}
    sofia = paquete(("M1", "calidad_del_dato_M1", {"historia": {"antiguedad_meses": 18.14, "completitud": 0.92},
                                                   "confiabilidad": {"etiqueta": "baja", "valor": 0.244}}))
    r = ("La consulta se cortó porque la confiabilidad de tu historia académica es baja (valor 0,244), con una "
         "antigüedad de 18,1 meses y una completitud de 0,92.")
    assert "magnitudes_cruzadas" not in verificar(r, sofia)


def test_ids_dentro_de_enunciados_no_son_reglas_aplicadas():
    s = Seccion("M3", "criticidad_asignatura", "estructura_del_plan_M3", "M3_Q4_CRITICIDAD", {}, {
        "reglas": [{"id": "E-03", "enunciado": "descendientes(X) = asignaturas alcanzables (sin H-09)"}]})
    assert s.reglas == ["E-03"]


def test_martina_cadena_de_enriquecimiento_m1_m4_m2(tmp_path):
    texto = "Soy Martina Gómez, legajo 48520. ¿Por qué no puedo cursar Análisis Numérico si yo dije que quería 2 materias?"
    rutas = {texto: enrutamiento("48520", "Martina Gómez", [("M1", "dictamen_asignatura", ["Análisis Numérico"], "cursar")])}
    expl = ("Sí, podés cursar Análisis Numérico: estás habilitada. El plan de este período no la incluye porque declaraste "
            "un tope de 2 materias y quedó empatada con otra candidata; el tope no cambia el tamaño admisible, que es de 3. "
            "Ese criterio de desempate todavía está en revisión, conviene confirmarlo con el asesor académico.")
    t = Orquestador(FakeKB(), FakeLLM(rutas, [expl]), config(tmp_path)).procesar(texto)
    assert t["enriquecimiento"] == ["plan_de_la_asignatura", "tope_frente_a_capacidad"]
    assert t["modulos_consultados"] == ["M1", "M2", "M4"]
    assert t["verificacion"]["intentos"][0]["fallas"] == {}


# ---------------------------------------------------------------- segunda corrida (12/11/2026): falsos positivos
def test_ana_probabilidad_y_estadistica_es_una_asignatura():
    p = paquete(("M4", "recomendacion_planificacion_M4", {"plan": [{"orden": 1, "asignatura": "Física I"}]}))
    r = ("También aparecen advertencias porque Análisis Matemático II, Probabilidad y Estadística, Economía y "
         "Legislación están habilitadas pero no se dictan este período.")
    assert "porcentaje_o_probabilidad" not in verificar(r, p)


def test_martina_etiqueta_que_figura_en_la_lectura_guiada():
    p = paquete(("M2", "carga_y_capacidad_M2", {"tope_declarado": 2, "lectura_guiada": [
        "Riesgo de sobrecarga: medio (grado 0,4 entre 0 y 1, no es una probabilidad)."]}))
    assert "etiqueta_inventada" not in verificar("Tu riesgo de sobrecarga es medio.", p)
    assert "etiqueta_inventada" in verificar("Tu riesgo de sobrecarga es alto.", p)


def test_juan_sobrecarga_que_sigue_alta_no_es_el_riesgo_simulado():
    p = paquete(("M3", "riesgo_de_atraso_M3", {"escenario_hipotetico": True,
                                               "riesgo_atraso": {"etiqueta": "alto", "valor": 0.664},
                                               "riesgo_registrado_en_PG2": {"etiqueta": "medio", "valor": 0.505}}))
    r = ("En la simulación con 9 horas, tu riesgo de atraso pasaría de medio a alto. Hoy tu riesgo de sobrecarga sigue "
         "siendo alto porque la carga supera la capacidad.")
    assert "escenario_hipotetico" not in verificar(r, p)


def test_tomas_dictamen_sin_asignatura_con_consulta_cortada_explica_el_corte(tmp_path):
    texto = "Legajo 48230, ¿por qué no me dan ningún dictamen?"
    rutas = {texto: enrutamiento("48230", None, [("M1", "dictamen_asignatura", [], None)])}
    expl = ("No hay dictamen porque tu consulta quedó detenida: tu historia académica tiene 2 inconsistencias y hay que "
            "confirmar el estado real de Simulación. Cuando se corrija, podés volver a consultar con el asesor académico.")
    t = Orquestador(FakeKB(), FakeLLM(rutas, [expl]), config(tmp_path)).procesar(texto)
    assert t["flujo"] == "sandwich completo"
    assert [s["intencion"] for s in t["secciones"]] == ["estado_historia"]
    assert t["verificacion"]["intentos"][0]["fallas"] == {}


# ---------------------------------------------------------------- tercera corrida (12/11/2026)
def test_tomas_enunciados_no_son_datos_y_etiqueta_negada():
    p = paquete(("M1", "calidad_del_dato_M1", {"historia": {"inconsistencias": 2}, "regla_corte": {
        "id": "X-01", "enunciado": "SI confiabilidad_del_dato ES baja ENTONCES corte; SI confiabilidad ES media ENTONCES reserva"}}))
    assert "etiqueta_inventada" not in verificar("Tu historia no tiene una confiabilidad alta calculada todavía.", p)
    assert "etiqueta_inventada" in verificar("La confiabilidad de tu historia es media.", p)


def test_martina_oracion_que_refuta_la_creencia_no_es_un_bloqueo():
    p = paquete(("M1", "habilitacion_normativa_M1", {"asignatura": {"nombre": "Análisis Numérico"},
                                                     "alcance_consultado": "cursar",
                                                     "dictamen": {"tipo": "HabilitacionCursar"}}))
    r = "Aunque creas que no podés cursar Análisis Numérico, en realidad estás habilitada para cursarla."
    assert "tipo_de_decision" not in verificar(r, p)
    assert "tipo_de_decision" in verificar("No podés cursar Análisis Numérico este cuatrimestre.", p)


def test_respaldo_de_historia_con_inconsistencias():
    from sita.respaldo import respaldo
    p = paquete(("M1", "calidad_del_dato_M1", {"historia": {"inconsistencias": 2}, "solicitudes_de_datos": [
        {"motivo": "Registros contradictorios", "faltantes": ["confirmar el estado real de: Simulación "]}]}))
    r = respaldo(p)
    assert "2 registros que se contradicen" in r and "Simulación." in r and "sin evaluar" not in r


# ---- Revisión manual de la corrida final (13/11/2026): errores que el verificador había dejado pasar ----

def test_martina_exclusion_del_plan_escrita_como_prohibicion():
    from fakes import PLAN_MARTINA_AN
    p = paquete(("M1", "habilitacion_normativa_M1", {"asignatura": {"nombre": "Análisis Numérico"},
                                                     "alcance_consultado": "cursar",
                                                     "dictamen": {"tipo": "HabilitacionCursar"}}),
                ("M4", "recomendacion_planificacion_M4", PLAN_MARTINA_AN))
    real = ("No podés cursar Análisis Numérico porque el plan del período lo excluyó al aplicar el tope declarado "
            "de 2 materias, aunque vos indicaras querer 2.")
    assert "tipo_de_decision" in verificar(real, p)  # el «aunque» posterior ya no la salva
    buena = ("Podés cursar Análisis Numérico: estás habilitada. El plan no la incluye este período porque quedó "
             "empatada con otra candidata al aplicar el tope declarado de 2 materias.")
    assert "tipo_de_decision" not in verificar(buena, p)
    # la refutación ANTES de la negación se sigue aceptando (C-37)
    assert "tipo_de_decision" not in verificar(
        "Aunque creas que no podés cursar Análisis Numérico, en realidad estás habilitada para cursarla.", p)


def test_tomas_area_de_registro_inventada():
    p = paquete(("M1", "calidad_del_dato_M1", {"historia": {"inconsistencias": 2}}))
    real = "Es necesario que actualices esos datos o que el área de registro aclare la situación."
    assert "instituciones_inventadas" in verificar(real, p)
    assert "instituciones_inventadas" not in verificar("Confirmalo con el asesor académico.", p)


def test_lucia_simulacion_no_es_materia_llave():
    from fakes import CRIT_SIM_AN
    p = paquete(("M3", "estructura_del_plan_M3", CRIT_SIM_AN))
    real = "El análisis muestra que Simulación y Análisis Numérico son materias clave para avanzar."
    assert "llave_inventada" in verificar(real, p)
    assert "llave_inventada" not in verificar(
        "Análisis Numérico es una materia llave; Simulación no es llave, aunque destraba otras dos.", p)
    assert "llave_inventada" not in verificar("Análisis Numérico es una materia llave (grado 0,641).", p)


def test_ana_riesgo_bajo_no_es_ausencia_de_riesgo():
    p = paquete(("M3", "riesgo_de_atraso_M3", {"riesgo_atraso": {"etiqueta": "bajo", "mu": 0.2}}))
    assert "riesgo_negado" in verificar("No, no tenés riesgo de atraso; el riesgo está catalogado como bajo.", p)
    assert "riesgo_negado" not in verificar("No tenés riesgo alto: tu riesgo de atraso es bajo (0,2).", p)
