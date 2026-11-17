"""El verificador contra los errores REALES observados en los PI4 del grupo."""
from sita.verificacion import verificar


def paquete_plan():  # traza del plan de Ana (PI4 de M2, caso 4)
    return {"pregunta": "¿qué me conviene?", "contexto": {"confiabilidad": {"etiqueta": "alta", "valor": 0.78}},
            "no_evaluado": [],
            "secciones": [{"modulo": "M4", "tipo_decision": "recomendacion_planificacion_M4", "resultado": {
                "confiabilidad_del_dato_M1": {"etiqueta": "alta", "valor": 0.78},
                "adecuacion_del_plan_M4": {"etiqueta": "alta", "valor": 0.79},
                "riesgo_de_atraso_M3": {"etiqueta": "bajo", "valor": 0.2},
                "plan": [{"orden": 1, "alcance": "rendir", "asignatura": "Física I"}]}}]}


def paquete_dictamen_sg():  # Lucía, Sistemas de Gestión (PI4 de M4, caso 3)
    return {"pregunta": "¿por qué no puedo cursar SG?", "contexto": {}, "no_evaluado": [],
            "secciones": [{"modulo": "M1", "tipo_decision": "habilitacion_normativa_M1", "resultado": {
                "asignatura": {"nombre": "Sistemas de Gestión"}, "alcance_consultado": "cursar",
                "dictamen": {"tipo": "BloqueoHeredado",
                             "causas": [{"correlatividad": "33-27-REG", "tipo": "regularidad", "asignatura": "Investigación Operativa"}],
                             "hereda_de": [{"asignatura": "Investigación Operativa"}],
                             "causa_raiz": [{"correlatividad": "27-22-REG", "tipo": "regularidad", "asignatura": "Análisis Numérico"}],
                             "reglas": [{"id": "H-04"}, {"id": "H-08"}]}}}]}


def paquete_martina():  # Martina, Análisis Numérico (PI4 de M4, caso 4)
    return {"pregunta": "¿por qué no puedo cursar AN?", "contexto": {}, "no_evaluado": [], "secciones": [
        {"modulo": "M1", "tipo_decision": "habilitacion_normativa_M1", "resultado": {
            "asignatura": {"nombre": "Análisis Numérico"}, "alcance_consultado": "cursar",
            "dictamen": {"tipo": "HabilitacionCursar", "reglas": [{"id": "H-05"}]}}},
        {"modulo": "M4", "tipo_decision": "recomendacion_planificacion_M4", "resultado": {
            "tope_declarado": 2, "tamano_admisible": 3,
            "items": [{"decision": "excluida", "asignatura": "Análisis Numérico", "causa": "tope declarado",
                       "empate_persistente": True, "regla_desempate": "P-04"}]}}]}


def test_ana_confiabilidad_confundida_con_adecuacion():
    r = ("Te conviene rendir Física I. La confiabilidad del plan es alta, con un valor de 0,79. "
         "La adecuación del plan también es alta, con un valor de 0,79.")
    f = verificar(r, paquete_plan())
    assert "magnitudes_cruzadas" in f and "0,79" in f["magnitudes_cruzadas"][0]
    assert "numeros_sin_respaldo" not in f      # el control de PI4 no lo detectaba: 0,79 existe en la traza


def test_martina_exclusion_atribuida_a_capacidad_y_presentada_como_bloqueo():
    r = "No podés cursar Análisis Numérico: el plan recomendado no la incluye por limitaciones de capacidad."
    f = verificar(r, paquete_martina())
    assert "causa_de_exclusion" in f and "tipo_de_decision" in f


def test_martina_respuesta_correcta_pasa():
    r = ("Sí, podés cursar Análisis Numérico: estás habilitada. El plan de este período no la incluye porque "
         "declaraste un tope de 2 materias y quedó empatada con otra candidata.")
    assert verificar(r, paquete_martina()) == {}


def test_bedelia_inventada():
    r = "Sí, podés cursar Análisis Numérico: estás habilitada. Si tenés dudas consultá en Bedelía."
    assert "instituciones_inventadas" in verificar(r, paquete_martina())


def test_lucia_correlatividad_como_regla_y_orden_invertido():
    r = ("No podés cursar Sistemas de Gestión porque esa materia tiene la regla 33-27-REG.\n"
         "1. Regularizar Investigación Operativa.\n2. Regularizar Análisis Numérico.")
    f = verificar(r, paquete_dictamen_sg(), ids_en_cuerpo=True)
    assert "correlatividad_como_regla" in f and "orden_de_destrabe" in f


def test_cobertura_normativa_exige_todas_las_condiciones():
    r = "Todavía no podés cursar Sistemas de Gestión porque te falta regularizar Investigación Operativa."
    f = verificar(r, paquete_dictamen_sg())
    assert "cobertura_normativa" in f and "Análisis Numérico" in f["cobertura_normativa"][0]


def test_lucia_respuesta_correcta_pasa():
    r = ("Todavía no podés cursar Sistemas de Gestión: te falta regularizar Investigación Operativa, que a su vez necesita "
         "que regularices Análisis Numérico.\n1. Regularizar Análisis Numérico.\n2. Regularizar Investigación Operativa.")
    assert verificar(r, paquete_dictamen_sg()) == {}


def test_forma_tuteo_portugues_porcentaje_jerga_e_ids():
    r = ("Tú puedes cursar a matéria Sistemas de Gestión com 64% de probabilidad según el grafo (regla H-04). "
         "Revisá el campo estado_en_historia.")
    f = verificar(r, paquete_dictamen_sg())
    for control in ("voseo", "idioma", "porcentaje_o_probabilidad", "jerga", "ids_en_cuerpo", "numeros_sin_respaldo"):
        assert control in f, control


def test_regla_inexistente():
    f = verificar("Según la regla RS2 no podés cursar Sistemas de Gestión.", paquete_dictamen_sg(), ids_en_cuerpo=True)
    assert f.get("ids_sin_respaldo") == ["RS2"]


def test_grado_no_es_probabilidad_cuando_se_niega():
    r = "Te conviene rendir Física I. Tu riesgo de atraso es bajo (0,2), un grado que no es una probabilidad."
    assert verificar(r, paquete_plan()) == {}


def test_fundamento_escrito_por_el_llm_se_quita_y_decimales_con_coma():
    from sita.verificacion import preparar
    r = preparar("Tu riesgo de atraso es bajo (0.2).\nFundamento: H-04, Q-LUCIA")
    assert r == "Tu riesgo de atraso es bajo (0,2)." and verificar(r, paquete_plan()) == {}


def test_jerga_interna_de_m1_y_portugues_con_diacriticos():
    f = verificar("Según Q-LUCIA, la regla es candidata. Isso não é tudo.", paquete_plan())
    assert "jerga" in f and "idioma" in f
    assert "jerga" not in verificar("Te conviene rendir Física I; quedó empatada con otra candidata.", paquete_plan())
