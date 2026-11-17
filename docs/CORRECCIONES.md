# Registro de correcciones — revisión integral para PG3

Este registro corresponde a la sección 1 del informe («Revisión y depuración final»). Cada fila es un problema detectado al comparar los cuatro PI4 y la corrección que se aplicó en el asistente unificado. Hay que completar la columna *Evidencia* con capturas o líneas de `logs/interacciones_pg3.jsonl` de la corrida final.

| Id | Componente | Problema detectado | Corrección en PG3 | Evidencia |
|---|---|---|---|---|
| C-01 | Enrutamiento | Intenciones duplicadas: «dictamen» estaba en M1, M2 y M4, y «plan» en M2 y M4, ambas sobre la consulta 12.1 | Catálogo único con un dueño por intención (`esquemas.py`). Si el LLM indica otro módulo, se corrige y queda registrado | `test_cada_intencion_tiene_un_unico_duenio` |
| C-02 | LLM | Cuatro clientes y tres proveedores distintos (Groq, Ollama, Anthropic) | Un solo cliente (`llm.py`) que reúne los manejos de cada PI4: 429, respuesta vacía, temperatura no soportada | `.env.example` |
| C-03 | Prompts | Ocho prompts (dos por submódulo) | Un prompt maestro de enrutamiento y uno de explicación (`prompts.py`) | `prompts/` |
| C-04 | Terminología | El prompt de M4 tuteaba («Eres…», «respondes») y el resto usaba voseo | Voseo en ambos prompts maestros y control `voseo` en el verificador | `test_forma_tuteo_...` |
| C-05 | Formato de salida | «Fundamento:» (M1), «Evidencia:» (M4) y «Por qué:» (M3) cumplían la misma función | Una sola línea «Fundamento:», armada por Python con las reglas por submódulo, las consultas y la traza | `test_e2e_lucia_...` |
| C-06 | Política de ids | M1 sacaba los ids del cuerpo y M2 y M3 los escribían en el texto | Política única configurable (`SITA_IDS_EN_CUERPO`, por defecto 0) y control `ids_en_cuerpo` | `config.py` |
| C-07 | Consulta 12.1 | Dos ampliaciones distintas de la misma consulta (M2 y M4) | `M4_PLAN` unifica ambas (excluidos con habilitación + ajustes y sobrecarga) | `cypher/consultas_pg3.cypher` |
| C-08 | Consulta 12.3 | Dos versiones de la traza de corte | Se adopta la ampliada de M2 (`X_CORTE`) | ídem |
| C-09 | Acceso a la base | M3 escribió nodos en la base del grupo durante PI4 | Todas las consultas en sesiones de lectura (`execute_read`). Prueba que rechaza CREATE, MERGE, SET y DELETE en la lista blanca | `test_plantillas_solo_lectura_...` |
| C-10 | Verificación | El control de M2 aceptó «confiabilidad 0,79» porque 0,79 existía en la traza como adecuación | Control `magnitudes_cruzadas`: cada valor se compara con el campo de su magnitud | `test_ana_confiabilidad_...` |
| C-11 | Verificación | M4 aceptó «excluida por limitaciones de capacidad» cuando la causa era el tope declarado | Control `causa_de_exclusion` | `test_martina_exclusion_...` |
| C-12 | Verificación | M3 aceptó «consultá con Bedelía», que no figuraba en el resultado | Control `instituciones_inventadas` | `test_bedelia_inventada` |
| C-13 | Verificación (devolución de M1) | No se comprobaba que la explicación cubriera todas las condiciones normativas del caso | Control `cobertura_normativa`: causas, herencia y causa raíz, con el verbo correcto (regularizar o aprobar) y la condicionalidad | `test_cobertura_normativa_...` |
| C-14 | Trazabilidad (devolución de M1) | La demo mostraba la respuesta, pero no el recorrido del grafo que la justifica | `M1_RECORRIDO`, modo `--auditar` y `GET /auditar/{id}`: fuente, regla, evidencia, consulta, recorrido y explicación | `cypher/auditoria.cypher` |
| C-15 | Resolución de entidades | Cuatro resolvedores distintos de asignaturas y estudiantes | `catalogo.py`: alias de M3, tokens de M2 y sugerencias de M1 | `test_integracion_neo4j` |
| C-16 | Robustez | Solo M3 exigía que el legajo estuviera escrito en el mensaje | Anclaje del legajo y de las horas hipotéticas para todos los submódulos | `test_legajo_no_escrito_...` |
| C-17 | Memoria | Solo M1 recordaba al estudiante entre mensajes | Memoria de sesión en el orquestador para todos los submódulos (solo la identidad) | `test_memoria_de_sesion_...` |
| C-18 | Limitación de PI4 | Una sola intención y una sola asignatura por mensaje (M1, M3) | Hasta 4 pedidos por mensaje y una entrada por asignatura | `prompts.py`, regla 1 |
| C-19 | Cortes | Cada PI4 resolvía los cortes por separado | El orquestador aplica X-01, X-02 y X-03 a todos los submódulos y explica qué no se evaluó y por qué | `test_corte_en_m1_...`, `test_corte_en_m2_...` |
| C-20 | Informe PI4 de M1 | Quedaron notas internas en el PDF («Incluí esta fila solo si…», «verificá la URL…», «6. Agregar/ajustar filas») | Quitarlas antes de reutilizar ese contenido en el informe final | — |

## Correcciones surgidas de la primera corrida contra la base real (`sita --demo`, 12/11/2026)

Resultado de la corrida: 16 de 17 casos consultaron los submódulos esperados. Al revisar las respuestas contra la auditoría aparecieron errores de contenido que los controles de entonces no detectaban. Cada uno quedó fijado como prueba de regresión en `tests/test_regresion_demo.py`.

| Id | Caso | Error observado | Corrección | Prueba |
|---|---|---|---|---|
| C-21 | E2E-06 Valentina | Física II figura **aprobada** y no tiene dictamen; el LLM dedujo un bloqueo a partir de las correlativas («no podés cursar Física II») | Sin dictamen, M1 quita las correlativas y agrega una nota explícita (`sin_dictamen`); nuevo control grave `sin_dictamen`; regla en el prompt | `test_valentina_...` |
| C-22 | E2E-04 Juan (9 h) | «Tu riesgo sigue siendo alto» cuando el registrado es medio y el alto es el simulado; no aclara que es una simulación | Control grave `escenario_hipotetico` y ejemplo en el prompt («pasaría de medio a alto») | `test_juan_escenario_...` |
| C-23 | FUN-03 Tomás | «La confiabilidad se considera baja» cuando no tenía activación (null); «está bajo supuesto» (estado interno) | Control grave `etiqueta_inventada`; «bajo supuesto» en la jerga | `test_tomas_...` |
| C-24 | E2E-03 Martina | Inventa «otras asignaturas con mayor grado de llave» cuando hubo empate persistente; «es probable que te retrases» | `causa_de_exclusion` detecta comparaciones con empate y exige mencionarlo; la probabilidad cubre «probable» | `test_martina_empate_...` |
| C-25 | E2E-02 Juan (rendir IA) | «Hasta que regularices Simulación» (ya era regular: para rendir hay que aprobarla, H-07) | Control grave `requisito_para_rendir` y regla en el prompt | `test_juan_rendir_...` |
| C-26 | E2E-03 Martina | No se consultó M2, aunque la pregunta era por el tope declarado | Regla R-E5 (M4 excluye por tope → M2) y enriquecimiento en dos rondas; ejemplo en el enrutador | `test_martina_cadena_...` |
| C-27 | E2E-07 Ana (falso positivo) | «No debe interpretarse como una probabilidad» se marcaba como error (ventana de negación corta) y terminaba en el respaldo | La negación se busca en 60 caracteres dentro de la misma oración | `test_falsos_positivos_...` |
| C-28 | E2E-05 Sofía (falso positivo) | La completitud (0,92) se asociaba a la confiabilidad | Otras mediciones cortan la asociación de magnitudes | ídem |
| C-29 | Fundamento | Aparecía H-09 porque estaba escrita dentro del enunciado de E-03 («sin H-09») | Los ids dentro de enunciados no se cuentan como reglas aplicadas | `test_ids_dentro_de_enunciados_...` |
| C-30 | Rendimiento | Respuestas de 40 a 90 s: el plan enviaba al LLM el glosario completo (19 reglas) | Cada sección envía solo el enunciado de sus propias reglas | — |
| C-32 | E2E-07 Ana (segunda corrida) | «Probabilidad y Estadística» (nombre de asignatura) se marcaba como lenguaje probabilístico y terminaba en el respaldo | El nombre de la asignatura se excluye del control | `test_ana_probabilidad_y_estadistica_...` |
| C-33 | E2E-03 Martina (segunda corrida) | «Riesgo de sobrecarga medio» se marcaba como inventado porque el dato venía en el texto de la lectura guiada de M2 | `etiqueta_inventada` también acepta las etiquetas que figuran en textos de los datos | `test_martina_etiqueta_...` |
| C-34 | E2E-04 Juan (segunda corrida) | «La sobrecarga sigue siendo alta» (verdadero) se tomaba como si el riesgo de atraso «siguiera igual» | El control mira solo las oraciones sobre el riesgo de atraso | `test_juan_sobrecarga_...` |
| C-35 | FUN-03 Tomás | «¿Por qué no me dan ningún dictamen?» se enrutó como dictamen sin asignatura y el sistema preguntó por una materia | Ejemplo en el enrutador y red de seguridad: sin asignatura y con la consulta cortada en M1 se explica el corte | `test_tomas_dictamen_sin_asignatura_...` |
| C-36 | FUN-03 Tomás (tercera corrida) | `etiqueta_inventada` tomaba como datos válidos las etiquetas mencionadas en los enunciados de las reglas y no admitía negaciones («no es alta») | Se ignoran los enunciados y las menciones negadas | `test_tomas_enunciados_...` |
| C-37 | E2E-03 Martina (tercera corrida) | `tipo_de_decision` marcaba una oración que refuta la creencia del estudiante («aunque creas que no podés…») | El control evalúa el contexto de la oración completa | `test_martina_oracion_...` |
| C-38 | Respaldo | La respuesta de respaldo de una historia con inconsistencias decía «confiabilidad sin evaluar» | Explica el corte por registros contradictorios y qué hay que confirmar | `test_respaldo_de_historia_...` |
| C-39 | E2E-03 Martina (corrida final, revisión manual) | «No podés cursar Análisis Numérico porque el plan del período lo excluyó…, aunque vos indicaras querer 2»: el «aunque» posterior anulaba el control | La refutación solo cuenta si está ANTES de la negación; una exclusión del plan escrita como «no podés» se marca siempre (regla 12f del prompt) | `test_martina_exclusion_del_plan_escrita_como_prohibicion` |
| C-40 | FUN-03 Tomás (corrida final) | Inventó «el área de registro» como oficina | Se amplió la lista de instituciones no respaldadas | `test_tomas_area_de_registro_inventada` |
| C-41 | E2E-01 Lucía (corrida final) | «Simulación y Análisis Numérico son materias clave», con Simulación debajo del corte α | Nuevo control grave `llave_inventada` (usa `es_llave` de M3) y regla 12e del prompt | `test_lucia_simulacion_no_es_materia_llave` |
| C-42 | E2E-07 Ana (corrida final) | «No, no tenés riesgo de atraso» con riesgo bajo (0,20) | Nuevo control grave `riesgo_negado` y regla 12c: bajo no es cero | `test_ana_riesgo_bajo_no_es_ausencia_de_riesgo` |
| C-43 | E2E-06 Valentina (corrida final) | Abría con «todavía no se puede determinar si podés cursar Física II», cuando ya la tiene aprobada | Regla 12d del prompt: sin dictamen y materia aprobada, empezar por eso | — (prompt) |
| C-44 | Auditoría | No había forma de auditar una respuesta ya guardada sin volver a llamar al LLM; la evidencia de M3 no mostraba las asignaturas llave | Nuevo comando `sita --traza <ID>` que lee el log JSONL; la evidencia de M3 lista las asignaturas llave con su grado | `test_cli_traza_audita_una_respuesta_guardada` |
| C-31 | Consola de Windows | Los colores se veían como «←[1;36m»; decía «relacións» | Se habilitan los colores ANSI en Windows; se corrigió el plural | — |

## Validaciones realizadas al armar el paquete

- Las 17 plantillas de la lista blanca, más la consulta visual de auditoría, pasan el analizador oficial de Neo4j (`@neo4j-cypher/language-support`, `lintCypherQuery`) sin errores ni avisos.
- Pasan las 66 pruebas offline: orquestador, cortes, enriquecimiento, verificador contra los errores reales de PI4, esquemas, lista blanca y API.
- Pendiente con la base real: `python -m sita --verificar`, `--verificar-difuso` y las pruebas de integración y E2E.
- Las cuatro plantillas de M1 del paquete son idénticas, comparadas en forma automática, a las de `sita_m1.py` (PI4). De ese script se incorporaron: la espera ante el 429 leyendo el «try again in…» de Groq, la salida estructurada con esquema en Ollama, el formato «Mensaje: …» del enrutador, la detección de jerga interna (ids `Q-…`, «regla candidata») y de portugués con diacríticos, la conversión a coma decimal, el aviso de reserva que agrega Python sin pedir una reescritura, el id de la Consulta del grafo en la línea «Fundamento:» y los mensajes de error comprensibles.
