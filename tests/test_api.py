"""API REST con un orquestador de prueba inyectado."""
from fastapi.testclient import TestClient
from fakes import FakeKB, FakeLLM, config, enrutamiento

from sita import app as modulo_app
from sita.orquestador import Orquestador

TEXTO = "Soy Lucía, legajo 48115. ¿Por qué no puedo cursar IA?"
EXPL = ("No, todavía no podés cursar Inteligencia Artificial: te falta regularizar Simulación y aprobar Análisis Numérico, "
        "que estás cursando, así que depende de cómo termines. Además, Análisis Numérico es una materia llave. Tu historia "
        "académica puede no estar al día: confirmalo con el asesor académico.")


def cliente(tmp_path):
    rutas = {TEXTO: enrutamiento("48115", "Lucía", [("M1", "dictamen_asignatura", ["IA"], "cursar")])}
    modulo_app.configurar(Orquestador(FakeKB(), FakeLLM(rutas, [EXPL]), config(tmp_path)))
    return TestClient(modulo_app.app)


def test_consultar_y_auditar(tmp_path):
    c = cliente(tmp_path)
    r = c.post("/consultar", json={"texto": TEXTO, "sesion_id": "t"})
    assert r.status_code == 200
    j = r.json()
    assert j["verificada"] and j["modulos_consultados"] == ["M1", "M3"] and j["fundamento"].startswith("Fundamento:")
    a = c.get(f"/auditar/{j['traza_id']}").json()
    m1 = a["conclusiones"][0]
    assert m1["fuente"].startswith("Régimen de correlatividades")
    assert {r["id"] for r in m1["reglas"]} == {"H-03", "H-04"}
    assert m1["recorrido_grafo"]["originado_por"][0]["requisito"] == "Simulación"
    assert m1["consulta"]["reproducir_en_neo4j_browser"].startswith(":params")
    assert c.get(f"/traza/{j['traza_id']}").status_code == 200
    assert c.get("/traza/noexiste").status_code == 404


def test_validacion_de_entrada_e_interfaz_web(tmp_path):
    c = cliente(tmp_path)
    assert c.post("/consultar", json={"texto": ""}).status_code == 422
    assert "SITA" in c.get("/").text


def test_cli_traza_audita_una_respuesta_guardada(tmp_path, monkeypatch, capsys):
    import json
    from sita import cli
    log = tmp_path / "interacciones.jsonl"
    traza = {"traza_id": "abc123def456", "entrada": "Legajo 48611, ¿voy bien?", "respuesta": "Tu riesgo es bajo.",
             "modulos_consultados": ["M3"], "secciones": [{
                 "modulo": "M3", "intencion": "riesgo_atraso", "origen": "pedido", "tipo_decision": "riesgo_de_atraso_M3",
                 "consulta_id": "M3_Q1_RIESGO", "parametros": {"legajo": "48611"}, "estado": "ok", "reglas": ["E-11d"],
                 "resultado": {"asignaturas_llave": [{"asignatura": "Física I", "grado_llave": 0.7}]}}]}
    log.write_text(json.dumps({"traza_id": "otra"}) + "\n" + json.dumps(traza, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setenv("SITA_LOG", str(log))
    assert cli.cmd_traza("abc123def456", como_json=False) == 0
    salida = capsys.readouterr().out
    assert "M3_Q1_RIESGO" in salida and "Física I" in salida
    assert cli.cmd_traza("noexiste0000", como_json=False) == 1
