# SITA — Asistente unificado (PG3 · Grupo 19 · 5k10)

**Sistema Inteligente de Trayectoria Académica** · Ingeniería en Sistemas de Información · UTN FRM · Inteligencia Artificial 2026

Un único asistente que integra los cuatro submódulos del proyecto. El estudiante escribe una consulta, el asistente la enruta a los submódulos que corresponden, recupera el conocimiento del grafo PG2 en Neo4j (solo lectura), lo explica en lenguaje natural y verifica que la explicación sea fiel a lo recuperado.

| Submódulo | Tarea experta | Responsable |
|---|---|---|
| M1 | Habilitación normativa y diagnóstico de bloqueos | Espínola, Facundo Nicolás |
| M2 | Carga académica y capacidad del estudiante | Manuel, Francisco Nicolás |
| M3 | Riesgo de atraso y estructura del plan | Suárez, Cristian |
| M4 | Planificación, priorización y explicación | Ferreyra, Paula |

---

## 1. Instalación

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                     # opcional: habilita el comando «sita»
cp .env.example .env                 # completar credenciales de Neo4j y del LLM
```

Requisitos: Python 3.10 o superior, la instancia AuraDB con `Grupo_19_PG2_U1.cypher` cargado (bloques 0.1 a 9.4) y una clave de Groq (o Ollama local).

## 2. Uso

Si no hiciste `pip install -e .`, ejecutá los comandos desde esta carpeta con `PYTHONPATH=src` (en Windows: `set PYTHONPATH=src`).

| Comando | Qué hace | Usa LLM |
|---|---|---|
| `python -m sita --verificar` | Comprueba etiquetas y relaciones del grafo, ejecuta `EXPLAIN` de las 17 plantillas y muestra el estado de cada estudiante | No |
| `python -m sita --verificar-difuso` | M3: compara la inferencia Mamdani ejecutada en Neo4j con PG2 y con el motor de PI3 | No |
| `python -m sita` | Modo conversación: recuerda tu legajo en la sesión; con `auditar` ves la traza de la última respuesta | Sí |
| `python -m sita -q "Soy Lucía, legajo 48115. ¿Por qué no puedo cursar IA?" --auditar` | Una consulta, con la trazabilidad completa | Sí |
| `python -m sita --demo` | Corre 7 casos integrados, 3 funcionales de M1, la repregunta con memoria y 6 de robustez, y guarda `logs/resultados_demo.json` | Sí |
| `python -m sita --servidor` | API REST e interfaz web en http://localhost:8000 (documentación interactiva en `/docs`) | Sí |
| `python -m sita --exportar` | Regenera `cypher/` y `prompts/` a partir del código | No |
| `python scripts/exportar_grafo.py` | Exporta el grafo completo a JSON para `base_conocimiento/` | No |
| `python -m sita --traza <traza_id> [--json]` | Audita una respuesta ya guardada en `logs/interacciones_pg3.jsonl`: fuente, reglas, evidencia y consulta para reproducir | No |
| `python scripts/ver_borradores.py [traza_id …]` | Muestra cada borrador del LLM y los controles que fallaron (sin argumentos: las últimas 5) | No |

**API REST**

- `POST /consultar` con `{"texto": "...", "sesion_id": "..."}` devuelve respuesta, fundamento, submódulos consultados y `traza_id`.
- `GET /traza/{id}`: traza completa (enrutamiento, consultas, resultados, verificación).
- `GET /auditar/{id}`: fuente, regla, evidencia, consulta, recorrido del grafo y explicación.
- `GET /salud`: estado de Neo4j y del LLM configurado.

## 3. Pruebas

```bash
sita --traza 8e8986b3e7c7                                  # audita una respuesta guardada, sin llamar al LLM
python -m pytest                                          # 66 pruebas sin Neo4j ni LLM (dobles de prueba)
SITA_TEST_NEO4J=1 python -m pytest tests/test_integracion_neo4j.py -v      # valores de PG2 contra la base real
SITA_TEST_E2E=1 LLM_PAUSA=20 python -m pytest tests/test_e2e_llm.py -v     # casos integrados de punta a punta
```

## 4. Arquitectura

```
Usuario ─► Interfaz (CLI · API REST · web) ─► Orquestador
                                                 │ 1 LLM + prompt maestro de ENRUTAMIENTO ─► JSON (Pydantic)
                                                 │ 2 resolución: estudiante (anclaje + sesión), asignaturas (catálogo + alias)
                                                 │ 3 contexto de la consulta (X_CONTEXTO): ¿cortada? ¿dónde? confiabilidad
                                                 │ 4 plan: orden M1→M2→M3→M4, cortes X-01 / X-02 / X-03
                                                 │ 5 submódulos M1 · M2 · M3 · M4 ─► plantillas Cypher (solo lectura) ─► Neo4j (grafo PG2)
                                                 │ 6 enriquecimiento determinista entre submódulos (R-E1 a R-E4)
                                                 │ 7 LLM + prompt maestro de EXPLICACIÓN (solo sobre el paquete recuperado)
                                                 │ 8 verificador (sintáctico + semántico) ─► reescritura ─► respaldo determinístico
                                                 └ 9 «Fundamento:» armado por Python + traza (JSONL) + auditoría
```

**Principios que se mantienen de los PI4**

- Neo4j es la única fuente de verdad. El LLM no escribe Cypher: elige intenciones de un catálogo cerrado y Python ejecuta plantillas de una lista blanca, siempre en transacciones de solo lectura.
- El LLM no decide nada. Las conclusiones ya están en el grafo con su traza (`JUSTIFICADO_POR`, `ORIGINADO_POR`, `CAUSA_RAIZ`).

**Reglas de enriquecimiento.** Son deterministas: las decide el código, no el modelo.

| Regla | Si… | …se consulta además | Para |
|---|---|---|---|
| R-E1 | M1 devuelve un bloqueo | M3 criticidad de la causa raíz (o de las causas directas) | Saber si lo que hay que destrabar es una materia llave |
| R-E2 | Se pregunta por un dictamen de M1 | M4 decisión del plan sobre esa asignatura (si fue candidata) | Separar «no podés» de «el plan no te la recomienda» |
| R-E3 | Se pregunta por una decisión del plan (M4) | M1 dictamen de esa asignatura | Aclarar si está habilitada |
| R-E4 | M2 recortó el plan | M4, solo los excluidos | Mostrar qué materia quedó afuera por el recorte |
| R-E5 | M4 excluyó una asignatura por el tope declarado | M2: tope frente a tamaño admisible | Explicar que el tope limita el plan sin cambiar la capacidad |

Las reglas se aplican en hasta dos rondas: lo que agrega una puede disparar otra (M1 → M4 → M2 en el caso de Martina).

## 5. Estructura

```
src/sita/
  orquestador.py   flujo completo, cortes, enriquecimiento, explicación y cierre
  prompts.py       prompt maestro de enrutamiento y de explicación
  esquemas.py      catálogo único de intenciones (un dueño por intención) y validación Pydantic
  modulos/         m1.py · m2.py · m3.py · m4.py · transversal.py (plantillas Cypher + contrato Seccion)
  verificacion.py  controles de fidelidad (sintácticos y semánticos)
  respaldo.py      respuesta determinística si el LLM no pasa los controles graves
  trazabilidad.py  auditoría: fuente, regla, evidencia, consulta, recorrido del grafo
  catalogo.py      resolución de estudiantes y asignaturas (alias, sugerencias)
  kb.py · llm.py · config.py · textos.py · casos.py · cli.py · app.py
cypher/            consultas_pg3.cypher (lista blanca) · auditoria.cypher (recorrido para Neo4j Browser)
prompts/           textos exactos de los dos prompts maestros
tests/             pruebas offline, de integración con Neo4j y E2E con LLM
docs/CORRECCIONES.md   registro de correcciones de la revisión integral (sección 1 del informe)
```
