"""Dobles de prueba: base de conocimiento y LLM simulados con valores documentados en PG2 y los PI4.

Permiten probar el orquestador, los cortes, el enriquecimiento y la verificación SIN Neo4j ni API de LLM.
Los códigos de correlatividad de IA (31-28-REG, 31-22-APR) son ilustrativos.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from sita.config import Config
from sita.prompts import PROMPT_ENRUTADOR

ESTUDIANTES = [
    {"legajo": "47890", "nombre": "Juan Pérez"}, {"legajo": "48520", "nombre": "Martina Gómez"},
    {"legajo": "48611", "nombre": "Ana Torres"}, {"legajo": "48115", "nombre": "Lucía Fernández"},
    {"legajo": "48230", "nombre": "Tomás Ríos"}, {"legajo": "48412", "nombre": "Valentina Sosa"},
    {"legajo": "48301", "nombre": "Sofía Molina"},
]
ASIGNATURAS = [
    {"codigo": 10, "sigla": "FII", "nombre": "Física II"}, {"codigo": 15, "sigla": "SO", "nombre": "Sistemas Operativos"},
    {"codigo": 22, "sigla": "AN", "nombre": "Análisis Numérico"}, {"codigo": 27, "sigla": "IO", "nombre": "Investigación Operativa"},
    {"codigo": 28, "sigla": "SIM", "nombre": "Simulación"}, {"codigo": 29, "sigla": "TA", "nombre": "Tecnología para la Automatización"},
    {"codigo": 31, "sigla": "IA", "nombre": "Inteligencia Artificial"}, {"codigo": 32, "sigla": "CD", "nombre": "Ciencia de Datos"},
    {"codigo": 33, "sigla": "SG", "nombre": "Sistemas de Gestión"},
]

CONTEXTOS = {
    "48115": {"estudiante": "Lucía Fernández", "legajo": "48115", "consulta": "Q-LUCIA", "estado": "resuelta",
              "corte_en": None, "periodo": "2027-1C", "confiabilidad": {"etiqueta": "media", "valor": 0.638},
              "reserva": "Dictámenes emitidos con reserva: historia de 4.9 meses y completitud 1.0"},
    "47890": {"estudiante": "Juan Pérez", "legajo": "47890", "consulta": "Q-JUAN", "estado": "resuelta", "corte_en": None,
              "periodo": "2027-2C", "confiabilidad": {"etiqueta": "alta", "valor": 0.778}, "reserva": None},
    "48520": {"estudiante": "Martina Gómez", "legajo": "48520", "consulta": "Q-MARTINA", "estado": "resuelta",
              "corte_en": None, "periodo": "2027-2C", "confiabilidad": {"etiqueta": "alta", "valor": 0.778}, "reserva": None},
    "48301": {"estudiante": "Sofía Molina", "legajo": "48301", "consulta": "Q-SOFIA", "estado": "cortada", "corte_en": "M1",
              "periodo": "2027-2C", "confiabilidad": {"etiqueta": "baja", "valor": 0.244}, "reserva": None},
    "48230": {"estudiante": "Tomás Ríos", "legajo": "48230", "consulta": "Q-TOMAS", "estado": "cortada", "corte_en": "M1",
              "periodo": "2027-1C", "confiabilidad": None, "reserva": None},
    "48412": {"estudiante": "Valentina Sosa", "legajo": "48412", "consulta": "Q-VALENTINA", "estado": "cortada",
              "corte_en": "M2", "periodo": "2027-2C", "confiabilidad": {"etiqueta": "alta", "valor": 0.8}, "reserva": None},
}

DICT_LUCIA_IA = {
    "estudiante": "Lucía Fernández", "legajo": "48115",
    "asignatura": {"codigo": 31, "nombre": "Inteligencia Artificial", "estado_en_historia": "pendiente (sin registro)"},
    "alcance_consultado": "cursar",
    "dictamen": {"id": "D-LUCIA-31-C", "tipo": "BloqueoDirecto", "condicionado": True, "profundidad": 1,
                 "causas": [{"correlatividad": "31-28-REG", "tipo": "regularidad", "asignatura": "Simulación",
                             "estado_encontrado": "vencida", "condicionada": False, "causa": "falta regularizar Simulación"},
                            {"correlatividad": "31-22-APR", "tipo": "aprobacion", "asignatura": "Análisis Numérico",
                             "estado_encontrado": "cursando", "condicionada": True, "causa": "falta aprobar Análisis Numérico"}],
                 "condiciones_verificadas": [], "hereda_de": [], "causa_raiz": [],
                 "reglas": [{"id": "H-03", "enunciado": "SI ... exige aprobación ENTONCES bloqueo", "estado": "firme"},
                            {"id": "H-04", "enunciado": "SI ... exige regularidad ENTONCES bloqueo", "estado": "firme"}]},
    "correlativas_de_la_asignatura": [], "advertencias": [],
    "contexto_m1": {"consulta": "Q-LUCIA", "estado_consulta": "resuelta", "corte_en": None,
                    "confiabilidad": {"etiqueta": "media", "valor": 0.638}, "reserva": True},
}
DICT_LUCIA_SG = {
    "estudiante": "Lucía Fernández", "legajo": "48115",
    "asignatura": {"codigo": 33, "nombre": "Sistemas de Gestión", "estado_en_historia": "pendiente (sin registro)"},
    "alcance_consultado": "cursar",
    "dictamen": {"id": "D-LUCIA-33-C", "tipo": "BloqueoHeredado", "profundidad": 2,
                 "causas": [{"correlatividad": "33-27-REG", "tipo": "regularidad", "asignatura": "Investigación Operativa",
                             "estado_encontrado": "pendiente", "condicionada": False,
                             "causa": "falta regularizar Investigación Operativa"}],
                 "hereda_de": [{"asignatura": "Investigación Operativa", "dictamen": "D-LUCIA-27-C"}],
                 "causa_raiz": [{"correlatividad": "27-22-REG", "tipo": "regularidad", "asignatura": "Análisis Numérico"}],
                 "reglas": [{"id": "H-04", "estado": "firme", "enunciado": "..."}, {"id": "H-08", "estado": "firme", "enunciado": "..."}]},
}
DICT_MARTINA_AN = {
    "estudiante": "Martina Gómez", "legajo": "48520",
    "asignatura": {"codigo": 22, "nombre": "Análisis Numérico", "estado_en_historia": "pendiente (sin registro)"},
    "alcance_consultado": "cursar",
    "dictamen": {"id": "D-MARTINA-22-C", "tipo": "HabilitacionCursar",
                 "condiciones_verificadas": [{"correlatividad": "22-9-REG", "tipo": "regularidad", "asignatura": "Análisis Matemático II"}],
                 "reglas": [{"id": "H-05", "estado": "firme", "enunciado": "..."}]},
}
CRIT_AN = {"asignaturas": [{"asignatura": "Análisis Numérico", "codigo": 22, "descendientes": 4, "grado_llave": 0.641,
                            "es_llave": True, "criticidad": [{"etiqueta": "alta", "mu": 0.641}]}],
           "corte_alfa_llave": 0.5, "reglas": [{"id": "E-03", "estado": "firme", "enunciado": "..."},
                                               {"id": "E-04", "estado": "candidata", "enunciado": "..."}]}
CRIT_SIM_AN = {"asignaturas": CRIT_AN["asignaturas"] + [{"asignatura": "Simulación", "codigo": 28, "descendientes": 2,
                                                         "grado_llave": 0.2, "es_llave": False}],
               "corte_alfa_llave": 0.5, "reglas": CRIT_AN["reglas"]}
PLAN_MARTINA_AN = {"periodo": "2027-2C", "tamano_efectivo": 2, "tamano_admisible": 3, "tope_declarado": 2,
                   "items": [{"decision": "excluida", "asignatura": "Análisis Numérico", "alcance": "cursar", "orden": 3,
                              "causa": "tope declarado", "rango": 2, "criterio": "llave", "empate_persistente": True,
                              "regla_desempate": "P-04"}],
                   "reglas": [{"id": "P-05", "estado": "candidata", "enunciado": "..."}, {"id": "P-06", "estado": "firme", "enunciado": "..."},
                              {"id": "P-04", "estado": "candidata", "enunciado": "..."}]}
CAP_JUAN = {"estudiante": "Juan Pérez", "legajo": "47890", "estado_consulta": "resuelta", "carga_h": 31.0, "capacidad_h": 25,
            "holgura_h": -6.0, "tamano_base": 4, "tamano_admisible": 3, "tope_declarado": None,
            "riesgo_sobrecarga": {"etiqueta": "alto", "valor": 0.77, "reglas": [{"regla": "RS1", "alfa": 0.8}]},
            "ajustes": [{"tipo": "AjustePorSobrecarga", "unidades": 1, "causa": "sobrecarga", "reglas": []}],
            "items_evaluados": [], "advertencias_m2": [],
            "glosario_reglas": [{"id": "C-02", "estado": "firme_bajo_supuesto", "enunciado": "..."}]}
PLAN_JUAN = {"estudiante": "Juan Pérez", "legajo": "47890", "periodo": "2027-2C", "estado_consulta": "resuelta",
             "confiabilidad": {"etiqueta": "alta", "valor": 0.78}, "capacidad": {"carga_h": 31.0, "capacidad_h": 25, "holgura_h": -6.0,
             "tamano_admisible": 3, "ajustes": []},
             "plan": [{"orden": 1, "alcance": "rendir", "asignatura": "Simulación", "criterio": "urgencia", "reglas": ["P-02", "H-06"]},
                      {"orden": 2, "alcance": "cursar", "asignatura": "Tecnología para la Automatización", "criterio": "arrastre", "reglas": ["P-02", "H-05"]},
                      {"orden": 3, "alcance": "cursar", "asignatura": "Inteligencia Artificial", "criterio": "afinidad", "reglas": ["P-02", "H-05"]}],
             "excluidos": [{"asignatura": "Ciencia de Datos", "alcance": "cursar", "causa": "capacidad", "habilitada_por": ["H-05"],
                            "reglas": ["P-05", "P-06"]}],
             "advertencias": [], "riesgo": {"etiqueta": "medio", "valor": 0.5}, "adecuacion": {"etiqueta": "media", "valor": 0.53},
             "glosario_reglas": []}
CAP_MARTINA = {"estudiante": "Martina Gómez", "legajo": "48520", "estado_consulta": "resuelta", "carga_h": 40.5,
               "capacidad_h": 43, "holgura_h": 2.5, "tamano_base": 4, "tamano_admisible": 3, "tope_declarado": 2,
               "riesgo_sobrecarga": {"etiqueta": "medio", "valor": 0.4, "reglas": [{"regla": "RS2", "alfa": 0.61}]},
               "ajustes": [{"tipo": "AjustePorRendimiento", "unidades": 1, "causa": "rendimiento", "reglas": []}],
               "advertencias_m2": [{"tipo": "discrepancia_tope", "mensaje": "El tope declarado (2) es menor que el tamaño admisible (3)",
                                    "reglas": ["C-08"]}],
               "glosario_reglas": [{"id": "C-08", "estado": "firme", "enunciado": "..."}]}
HISTORIA_SOFIA = {"estudiante": "Sofía Molina", "legajo": "48301",
                  "historia": {"antiguedad_meses": 18.14, "completitud": 0.92, "inconsistencias": 0},
                  "confiabilidad": {"etiqueta": "baja", "valor": 0.244, "reglas_activadas": [{"id": "RB1", "alfa": 0.76}]},
                  "solicitudes_de_datos": [{"ambito": "historia", "motivo": "Confiabilidad del dato baja (0.24)",
                                            "faltantes": ["actualizar la historia académica"]}],
                  "regla_corte": {"id": "X-01", "estado": "firme", "enunciado": "..."}}
CORTE_VALENTINA = {"estudiante": "Valentina Sosa", "estado_consulta": "cortada", "corte_en": "M2", "ambito": "contexto",
                   "motivo": "Contexto incompleto", "faltantes": ["horas de trabajo semanales", "turnos disponibles"],
                   "reglas": [{"id": "X-02", "estado": "firme", "enunciado": "..."}], "dictamenes_conservados": 12}
DICT_VALENTINA_FII = {"estudiante": "Valentina Sosa", "legajo": "48412",
                      "asignatura": {"codigo": 10, "nombre": "Física II", "estado_en_historia": "pendiente (sin registro)"},
                      "alcance_consultado": "cursar",
                      "dictamen": {"id": "D-VAL-10", "tipo": "HabilitacionCursar", "condiciones_verificadas": [],
                                   "reglas": [{"id": "H-05", "estado": "firme", "enunciado": "..."}]}}


class FakeKB:
    def __init__(self):
        self.registro = []
        self.transporte = "fake"

    def leer(self, nombre, cypher, **params):
        self.registro.append({"consulta": nombre, "parametros": params})
        if nombre == "CAT_ESTUDIANTES":
            return ESTUDIANTES
        if nombre == "CAT_ASIGNATURAS":
            return ASIGNATURAS
        v = self._valor(nombre, params)
        return [{"r": v}] if v is not None else []

    def valor(self, nombre, cypher, **params):
        filas = self.leer(nombre, cypher, **params)
        return filas[0]["r"] if filas else None

    def _valor(self, nombre, p):
        leg = p.get("legajo")
        if nombre == "X_CONTEXTO":
            return CONTEXTOS.get(leg)
        if nombre == "M1_DICTAMEN":
            return {("48115", 31): DICT_LUCIA_IA, ("48115", 33): DICT_LUCIA_SG, ("48520", 22): DICT_MARTINA_AN,
                    ("48412", 10): DICT_VALENTINA_FII}.get((leg, p.get("codigo")))
        if nombre == "M1_HISTORIA" and leg == "48301":
            return HISTORIA_SOFIA
        if nombre == "M1_HISTORIA" and leg == "48230":
            return {"estudiante": "Tomás Ríos", "legajo": "48230",
                    "historia": {"inconsistencias": 2, "fecha_actualizacion": "2026-09-28"},
                    "solicitudes_de_datos": [{"ambito": "historia", "motivo": "2 inconsistencias en la historia",
                                              "faltantes": ["confirmar el estado real de Simulación"]}],
                    "regla_corte": {"id": "X-01", "estado": "firme_bajo_supuesto", "enunciado": "..."}}
        if nombre == "M1_RECORRIDO":
            return {"camino": "(Estudiante)<-[:SOLICITADA_POR]-(Consulta)-[:PRODUCE]->(Dictamen)-[:SOBRE]->(Asignatura)",
                    "originado_por": [{"relacion": "(Dictamen)-[:ORIGINADO_POR]->(Correlatividad)-[:APUNTA_A]->(Asignatura)",
                                       "correlatividad": "31-28-REG", "requisito": "Simulación", "estado_en_historia": "vencida"}]}
        if nombre == "M3_Q4_CRITICIDAD":
            cods = sorted(p.get("codigos") or [])
            return {(22,): CRIT_AN, (22, 28): CRIT_SIM_AN}.get(tuple(cods))
        if nombre == "M4_PLAN_ASIGNATURA":
            return PLAN_MARTINA_AN if (leg, p.get("codigo")) == ("48520", 22) else {"items": []}
        if nombre == "M2_CAPACIDAD" and leg in ("47890", "48520"):
            return CAP_JUAN if leg == "47890" else CAP_MARTINA
        if nombre == "M4_PLAN" and leg == "47890":
            return PLAN_JUAN
        if nombre == "X_CORTE" and leg == "48412":
            return CORTE_VALENTINA
        return None

    def cerrar(self):
        pass


def enrutamiento(legajo=None, nombre=None, pedidos=(), fuera=False, horas=None) -> str:
    return json.dumps({"legajo": legajo, "nombre_estudiante": nombre, "horas_hipoteticas": horas, "horizonte_meses": None,
                       "pedidos": [{"modulo": m, "intencion": i, "asignaturas": list(a), "alcance": al, "filtro": "todas"}
                                   for m, i, a, al in pedidos],
                       "fuera_de_dominio": fuera, "faltantes": []}, ensure_ascii=False)


class FakeLLM:
    """Enrutador por texto exacto; explicaciones en cola (o una función de la traza)."""
    nombre = "fake:modelo"

    def __init__(self, rutas: dict[str, str], explicaciones: list | None = None):
        self.rutas, self.explicaciones, self.llamadas = rutas, list(explicaciones or []), []

    def chat(self, system, user, json_mode=False, max_tokens=2000, json_schema=None):
        self.llamadas.append({"system": system[:40], "user": user, "json": json_mode})
        if system == PROMPT_ENRUTADOR:
            texto = user.split("\n\n(Tu respuesta anterior")[0].removeprefix("Mensaje: ")
            return self.rutas[texto]
        e = self.explicaciones.pop(0) if self.explicaciones else "Sin explicación."
        return e(user) if callable(e) else e


def config(tmp: Path) -> Config:
    base = Config.desde_entorno()
    return replace(base, log_path=tmp / "log.jsonl", ids_en_cuerpo=False)
