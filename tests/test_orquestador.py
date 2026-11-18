"""Pruebas del orquestador sin Neo4j ni LLM reales (dobles de prueba con valores de PG2)."""
from fakes import FakeKB, FakeLLM, config, enrutamiento

from sita.orquestador import Orquestador

T_LUCIA = "Soy Lucía, legajo 48115. ¿Por qué no puedo cursar IA y qué me conviene cursar este cuatrimestre?"
R_LUCIA = enrutamiento("48115", "Lucía", [("M1", "dictamen_asignatura", ["IA"], "cursar"), ("M4", "plan", [], None)])
BUENA_LUCIA = ("No, todavía no podés cursar Inteligencia Artificial. Te falta regularizar Simulación, que figura vencida, "
               "y aprobar Análisis Numérico, que estás cursando: esa parte depende de cómo termines la cursada.\n\n"
               "Además, Análisis Numérico es una materia llave del plan: muchas materias dependen de ella, así que "
               "conviene priorizarla. Simulación, en cambio, no es llave.\n\n"
               "Todavía no tengo un plan registrado para vos. Tu historia académica puede no estar al día, así que "
               "conviene confirmarlo con el asesor académico.")


def orq(tmp_path, rutas, explicaciones=None):
    return Orquestador(FakeKB(), FakeLLM(rutas, explicaciones), config(tmp_path))


def test_e2e_lucia_cruza_m1_m3_m4_y_verifica(tmp_path):
    o = orq(tmp_path, {T_LUCIA: R_LUCIA}, [BUENA_LUCIA])
    t = o.procesar(T_LUCIA)
    assert t["flujo"] == "sandwich completo"
    assert t["modulos_consultados"] == ["M1", "M3", "M4"]
    origenes = {(s["modulo"], s["intencion"], s["origen"]) for s in t["secciones"]}
    assert ("M3", "criticidad_asignatura", "enriquecimiento") in origenes      # R-E1: lo que hay que destrabar
    assert t["enriquecimiento"] == ["criticidad_causa_raiz"]                    # R-E2 no aplica: IA no fue candidata
    assert t["verificacion"]["intentos"][0]["fallas"] == {}
    assert "M1 H-03, H-04" in t["fundamento"] and "E-03, E-04" in t["fundamento"]
    assert t["respuesta_completa"].endswith(t["fundamento"])


def test_respuesta_con_errores_reales_termina_en_respaldo(tmp_path):
    mala = ("No podés cursar Inteligencia Artificial. La confiabilidad de tu historia es 0,79. "
            "Consultá con Bedelía para hacer el trámite.")
    o = orq(tmp_path, {T_LUCIA: R_LUCIA}, [mala, mala])
    t = o.procesar(T_LUCIA)
    fallas = t["verificacion"]["intentos"][0]["fallas"]
    assert {"instituciones_inventadas", "magnitudes_cruzadas", "cobertura_normativa"} <= set(fallas)
    assert t["verificacion"]["respaldo_deterministico"] is True
    assert "Todavía no podés cursar Inteligencia Artificial" in t["respuesta"]
    assert "Bedel" not in t["respuesta"]


def test_corte_en_m1_no_evalua_m3_ni_m4(tmp_path):
    texto = "Soy Sofía Molina, legajo 48301. Armame el plan y decime si tengo riesgo de atrasarme."
    rutas = {texto: enrutamiento("48301", "Sofía Molina", [("M4", "plan", [], None), ("M3", "riesgo_atraso", [], None)])}
    expl = ("Todavía no puedo armarte el plan ni evaluar tu riesgo de atraso: tu historia académica tiene una "
            "confiabilidad baja porque no se actualiza hace unos 18 meses. Actualizala y volvé a consultar.")
    t = orq(tmp_path, rutas, [expl]).procesar(texto)
    assert {n["intencion"] for n in t["no_evaluado"]} == {"plan", "riesgo_atraso"}
    assert [s["intencion"] for s in t["secciones"]] == ["estado_historia"]
    assert t["secciones"][0]["origen"] == "contexto"
    assert "X-01" in t["fundamento"]
    assert t["verificacion"]["intentos"][0]["fallas"] == {}


def test_corte_en_m2_conserva_m1(tmp_path):
    texto = "Soy Valentina Sosa, legajo 48412. ¿Puedo cursar Física II y cuántas materias puedo llevar?"
    rutas = {texto: enrutamiento("48412", "Valentina Sosa", [("M1", "dictamen_asignatura", ["Física II"], "cursar"),
                                                             ("M2", "capacidad", [], None)])}
    expl = ("Sí, podés cursar Física II. Lo que todavía no puedo decirte es cuántas materias podés llevar, porque faltan "
            "tus horas de trabajo semanales y tus turnos disponibles. Cuando los cargues, volvé a consultar.")
    t = orq(tmp_path, rutas, [expl]).procesar(texto)
    assert [s["modulo"] for s in t["secciones"]] == ["X", "M1"]
    assert [n["intencion"] for n in t["no_evaluado"]] == ["capacidad"]
    assert t["enriquecimiento"] == []          # con corte no se agrega el plan
    assert t["verificacion"]["intentos"][0]["fallas"] == {}


def test_habilitada_pero_excluida_del_plan(tmp_path):
    texto = "Soy Martina Gómez, legajo 48520. ¿Por qué no puedo cursar Análisis Numérico?"
    rutas = {texto: enrutamiento("48520", "Martina Gómez", [("M1", "dictamen_asignatura", ["Análisis Numérico"], "cursar")])}
    mala = ("No podés cursar Análisis Numérico este cuatrimestre: el plan no la incluye por limitaciones de capacidad.")
    buena = ("Sí podés cursar Análisis Numérico: estás habilitada porque tenés regularizada Análisis Matemático II.\n\n"
             "Lo que pasa es que el plan de este período no la recomienda: declaraste un tope de 2 materias y quedó empatada "
             "con otra candidata, así que el plan la excluye por el tope declarado y te presenta las dos opciones. Ese "
             "criterio de desempate todavía está en revisión, conviene confirmarlo con el asesor académico.")
    t = orq(tmp_path, rutas, [mala, buena]).procesar(texto)
    assert t["enriquecimiento"] == ["plan_de_la_asignatura", "tope_frente_a_capacidad"]  # R-E2 y R-E5
    primeras = t["verificacion"]["intentos"][0]["fallas"]
    assert "tipo_de_decision" in primeras and "causa_de_exclusion" in primeras
    assert t["verificacion"]["intentos"][1]["fallas"] == {}
    assert t["respuesta"].startswith("Sí podés cursar")


def test_memoria_de_sesion_y_causa_raiz(tmp_path):
    t2 = "¿Y Sistemas de Gestión?"
    rutas = {T_LUCIA: R_LUCIA, t2: enrutamiento(None, None, [("M1", "dictamen_asignatura", ["Sistemas de Gestión"], "cursar")])}
    invertida = ("Todavía no podés cursar Sistemas de Gestión. Pasos:\n1. Regularizar Investigación Operativa.\n"
                 "2. Regularizar Análisis Numérico.")
    buena = ("Todavía no podés cursar Sistemas de Gestión, porque te falta regularizar Investigación Operativa, y a su vez "
             "esa materia necesita que regularices Análisis Numérico. Lo que destraba todo es Análisis Numérico:\n"
             "1. Regularizar Análisis Numérico.\n2. Regularizar Investigación Operativa.\n3. Cursar Sistemas de Gestión.\n"
             "Además, Análisis Numérico es una materia llave. Tu historia puede no estar al día: confirmalo con el asesor.")
    o = orq(tmp_path, rutas, [BUENA_LUCIA, invertida, buena])
    o.procesar(T_LUCIA, sesion_id="s1")
    t = o.procesar(t2, sesion_id="s1")
    assert t["estudiante_de_sesion"] is True and t["estudiante"]["legajo"] == "48115"
    assert "orden_de_destrabe" in t["verificacion"]["intentos"][0]["fallas"]
    assert t["verificacion"]["intentos"][1]["fallas"] == {}
    assert "H-08" in t["fundamento"]


def test_legajo_no_escrito_no_se_acepta(tmp_path):
    texto = "¿Puedo cursar IA?"
    rutas = {texto: enrutamiento("48115", None, [("M1", "dictamen_asignatura", ["IA"], "cursar")])}
    t = orq(tmp_path, rutas).procesar(texto)
    assert t["flujo"] == "aclaracion: estudiante"
    assert any("no aparece en el mensaje" in c for c in t["correcciones"])


def test_fuera_de_dominio_y_valores_absurdos(tmp_path):
    t1, t2 = "¿Cuál es la receta del flan?", "Legajo 47890, si tuviera 200 horas libres por semana, ¿cuál sería mi riesgo?"
    rutas = {t1: enrutamiento(fuera=True),
             t2: enrutamiento("47890", None, [("M3", "riesgo_atraso", [], None)], horas=200)}
    o = orq(tmp_path, rutas)
    assert o.procesar(t1)["flujo"] == "aclaracion: fuera de dominio"
    r = o.procesar(t2)
    assert r["flujo"] == "aclaracion: parametros" and "55" in r["respuesta"]
    assert not any(q["consulta"].startswith("M3") for q in r["consultas_ejecutadas"])


def test_recorte_de_m2_agrega_excluidas_de_m4(tmp_path):
    texto = "Soy Juan Pérez, legajo 47890. ¿Por qué me recortaron una materia?"
    rutas = {texto: enrutamiento("47890", "Juan Pérez", [("M2", "capacidad", [], None)])}
    expl = ("Te recortaron una materia porque tu carga estimada es de 31 horas semanales y tu capacidad de 25: tenés un "
            "déficit de 6 horas, y con eso el riesgo de sobrecarga es alto (0,77). Por eso el plan pasó de 4 a 3 materias. "
            "Ciencia de Datos sigue habilitada, pero el plan no la recomienda este período por capacidad. El criterio de "
            "carga todavía está en revisión, conviene confirmarlo con el asesor académico.")
    t = orq(tmp_path, rutas, [expl]).procesar(texto)
    assert t["enriquecimiento"] == ["excluidas_por_recorte"]                    # R-E4: M2 -> M4
    m4 = next(s for s in t["paquete_llm"]["secciones"] if s["modulo"] == "M4")
    assert set(m4["resultado"]) <= {"excluidos", "periodo"}                     # foco: solo lo relevante
    assert t["verificacion"]["intentos"][0]["fallas"] == {}


def test_enrutamiento_invalido_se_reintenta_y_corrige_modulo(tmp_path):
    texto = "Legajo 48520, ¿puedo cursar AN?"
    rutas = {texto: '{"legajo": "48520", "pedidos": [{"modulo": "M4", "intencion": "dictamen_asignatura", '
                    '"asignaturas": ["AN"], "alcance": "cursar", "filtro": "todas"}], "fuera_de_dominio": false, "faltantes": []}'}
    expl = ("Sí, podés cursar Análisis Numérico: estás habilitada. El plan de este período no la recomienda por el tope "
            "declarado y un empate con otra candidata; ese criterio todavía está en revisión con el asesor académico.")
    t = orq(tmp_path, rutas, [expl]).procesar(texto)
    assert any("el catálogo asigna M1" in c for c in t["enrutamiento"]["correcciones"])
    assert t["secciones"][0]["modulo"] == "M1"


def test_aviso_de_reserva_lo_agrega_python_sin_reescribir(tmp_path):
    texto = "Legajo 48115, ¿puedo cursar IA?"
    rutas = {texto: enrutamiento("48115", None, [("M1", "dictamen_asignatura", ["IA"], "cursar")])}
    sin_aviso = ("No, todavía no podés cursar Inteligencia Artificial: te falta regularizar Simulación y aprobar Análisis "
                 "Numérico, que estás cursando, así que depende de cómo termines. Además, Análisis Numérico es una "
                 "materia llave.\nFundamento: H-03, H-04")
    o = orq(tmp_path, rutas, [sin_aviso])
    t = o.procesar(texto)
    assert len(t["verificacion"]["intentos"]) == 1                     # no hubo reescritura
    assert "confiabilidad media (0,638" in t["respuesta"]
    assert t["respuesta"].count("Fundamento") == 0 and "Q-LUCIA" in t["fundamento"]


def test_espera_429_lee_el_mensaje_de_groq():
    from types import SimpleNamespace
    from sita.llm import LLM
    r = SimpleNamespace(headers={}, text="Rate limit reached. Please try again in 1m7.5s.")
    assert LLM._espera_429(r) == 68.5


class _Resp:
    def __init__(self, status, datos):
        self.status_code, self._datos, self.headers, self.text = status, datos, {}, str(datos)

    def json(self):
        return self._datos


def _llm_anthropic(tmp_path, monkeypatch, respuestas, modelo="claude-sonnet-5-5"):
    from dataclasses import replace
    from sita import llm as modulo
    enviados = []

    def post(url, headers=None, json=None, timeout=None):
        enviados.append({**json})
        return respuestas.pop(0)

    monkeypatch.setattr(modulo.requests, "post", post)
    cfg = replace(config(tmp_path), llm_provider="anthropic", llm_model=modelo, llm_api_key="x")
    return modulo.LLM(cfg), enviados


def _texto(t, motivo="end_turn"):
    return _Resp(200, {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": t}],
                       "stop_reason": motivo})


def test_anthropic_sin_temperatura_y_con_esfuerzo_por_tarea(tmp_path, monkeypatch):
    llm, enviados = _llm_anthropic(tmp_path, monkeypatch, [_texto('{"ok": 1}'), _texto("Explicación")])
    assert llm.chat("s", "u", json_mode=True, max_tokens=1500) == '{"ok": 1}'
    assert llm.chat("s", "u", max_tokens=4000) == "Explicación"
    assert all("temperature" not in b for b in enviados)
    assert [b["output_config"]["effort"] for b in enviados] == ["low", "medium"]
    assert all(b["max_tokens"] >= 16000 for b in enviados)  # el razonamiento usa el mismo presupuesto


def test_anthropic_respuesta_vacia_duplica_el_presupuesto(tmp_path, monkeypatch):
    vacia = _Resp(200, {"content": [{"type": "thinking", "thinking": ""}], "stop_reason": "max_tokens"})
    llm, enviados = _llm_anthropic(tmp_path, monkeypatch, [vacia, _texto("Listo")])
    assert llm.chat("s", "u") == "Listo"
    assert enviados[1]["max_tokens"] == 2 * enviados[0]["max_tokens"]


def test_anthropic_modelo_sin_effort_reintenta_sin_el(tmp_path, monkeypatch):
    rechazo = _Resp(400, {"error": {"message": "output_config.effort: not supported on this model"}})
    llm, enviados = _llm_anthropic(tmp_path, monkeypatch, [rechazo, _texto("Hola"), _texto("Otra")],
                                   modelo="claude-haiku-4-5")
    assert llm.chat("s", "u") == "Hola"
    assert llm.chat("s", "u") == "Otra"
    assert "output_config" in enviados[0] and "output_config" not in enviados[1] and "output_config" not in enviados[2]


def test_anthropic_rechazo_da_error_claro(tmp_path, monkeypatch):
    import pytest
    from sita.llm import ErrorLLM
    llm, _ = _llm_anthropic(tmp_path, monkeypatch, [_Resp(200, {"content": [], "stop_reason": "refusal"})])
    with pytest.raises(ErrorLLM, match="declinó"):
        llm.chat("s", "u")
