"""SITA — Sistema Inteligente de Trayectoria Académica (Grupo 19, 5k10, UTN FRM, IA 2026).

PG3: asistente unificado. Un único punto de entrada (CLI o API) enruta la consulta del estudiante
hacia los submódulos M1–M4, que recuperan conocimiento del grafo PG2 (Neo4j, solo lectura);
un único prompt de explicación redacta la respuesta y un verificador controla su fidelidad.

Integrantes y submódulos:
  M1 Habilitación normativa y diagnóstico de bloqueos ...... Espínola, Facundo Nicolás
  M2 Carga académica y capacidad del estudiante ............ Manuel, Francisco Nicolás
  M3 Riesgo de atraso y estructura del plan ................ Suárez, Cristian
  M4 Planificación, priorización y explicación ............. Ferreyra, Paula
"""

__version__ = "3.0.0"
