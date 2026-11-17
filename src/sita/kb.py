"""Acceso de SOLO LECTURA al grafo de PG2 (Neo4j AuraDB).

- Driver oficial con sesiones en modo lectura y transacciones execute_read (M1, M2): el asistente
  no puede modificar la base (corrección de la lección de proceso de M3 en PI4).
- Si el puerto Bolt no está disponible (red que solo permite HTTPS), usa la Query API HTTPS de Aura
  con las mismas consultas y parámetros (M4).
- Registra cada consulta ejecutada (id, parámetros) para la traza y la auditoría.
"""
from __future__ import annotations

import re

from .config import Config


class ErrorBase(RuntimeError):
    pass


class BaseConocimiento:
    def __init__(self, cfg: Config):
        if not (cfg.neo4j_uri and cfg.neo4j_password):
            raise ErrorBase("Faltan NEO4J_URI / NEO4J_PASSWORD (archivo .env o variables de entorno).")
        self.cfg = cfg
        self.db = cfg.neo4j_database or None
        self.registro: list[dict] = []
        self.driver = None
        self.http = None
        from neo4j import GraphDatabase
        try:
            self.driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password),
                                               connection_timeout=15)
            self.driver.verify_connectivity()
            self.transporte = "bolt"
        except Exception as exc:  # noqa: BLE001 - cualquier falla de Bolt habilita el transporte HTTPS
            if self.driver:
                self.driver.close()
            self.driver = None
            host = re.sub(r"^[\w+.-]+://", "", cfg.neo4j_uri).split(":")[0].split("/")[0]
            self.http = f"https://{host}/db/{self.db or 'neo4j'}/query/v2"
            self.transporte = f"https (Bolt no disponible: {type(exc).__name__})"

    def leer(self, nombre: str, cypher: str, **params) -> list[dict]:
        self.registro.append({"consulta": nombre, "parametros": params})
        if self.http:
            import requests
            r = requests.post(self.http, auth=(self.cfg.neo4j_user, self.cfg.neo4j_password), timeout=60,
                              json={"statement": cypher, "parameters": params},
                              headers={"Accept": "application/json"})
            cuerpo = r.json() if r.content else {}
            if r.status_code >= 400 or cuerpo.get("errors"):
                raise ErrorBase(f"Neo4j Query API {r.status_code}: {cuerpo.get('errors') or r.text[:300]}")
            campos = cuerpo["data"]["fields"]
            return [dict(zip(campos, fila)) for fila in cuerpo["data"]["values"]]
        from neo4j import READ_ACCESS
        with self.driver.session(database=self.db, default_access_mode=READ_ACCESS) as s:
            return s.execute_read(lambda tx: [rec.data() for rec in tx.run(cypher, params)])

    def valor(self, nombre: str, cypher: str, **params):
        """Primer valor del primer registro (las plantillas devuelven un único mapa)."""
        filas = self.leer(nombre, cypher, **params)
        return next(iter(filas[0].values())) if filas else None

    def cerrar(self) -> None:
        if self.driver:
            self.driver.close()
