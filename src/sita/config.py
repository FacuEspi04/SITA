"""Configuración única del asistente (variables de entorno o archivo .env). Sin credenciales en el código.

Unifica los nombres de variables que usaba cada PI4 (NEO4J_USER / NEO4J_USERNAME, GROQ_API_KEY /
LLM_API_KEY, LLM_BACKEND / LLM_PROVIDER) para que el .env de cualquier integrante siga sirviendo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # carpeta implementacion/


def _cargar_env() -> None:
    for ruta in (Path.cwd() / ".env", RAIZ / ".env"):
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _env(*nombres: str, defecto: str | None = None) -> str | None:
    for n in nombres:
        v = os.getenv(n)
        if v not in (None, ""):
            return v
    return defecto


@dataclass(frozen=True)
class Config:
    neo4j_uri: str | None
    neo4j_user: str
    neo4j_password: str | None
    neo4j_database: str | None
    llm_provider: str          # openai (Groq u otra API compatible) | ollama | anthropic
    llm_model: str
    llm_base_url: str
    llm_api_key: str | None
    ollama_url: str
    llm_timeout: int
    llm_pausa: float
    ids_en_cuerpo: bool        # política de identificadores de regla en el cuerpo de la respuesta
    log_path: Path

    @classmethod
    def desde_entorno(cls) -> "Config":
        _cargar_env()
        proveedor = (_env("LLM_PROVIDER", "LLM_BACKEND", defecto="openai") or "openai").lower()
        modelo_def = {"openai": "openai/gpt-oss-120b", "ollama": "qwen2.5:7b",
                      "anthropic": "claude-haiku-5-5"}.get(proveedor, "openai/gpt-oss-120b")
        clave = _env("LLM_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        return cls(
            neo4j_uri=_env("NEO4J_URI"),
            neo4j_user=_env("NEO4J_USER", "NEO4J_USERNAME", defecto="neo4j"),
            neo4j_password=_env("NEO4J_PASSWORD"),
            neo4j_database=_env("NEO4J_DATABASE"),
            llm_provider=proveedor,
            llm_model=_env("LLM_MODEL", "GROQ_MODEL", defecto=modelo_def),
            llm_base_url=_env("LLM_BASE_URL", "OPENAI_BASE_URL", defecto="https://api.groq.com/openai/v1"),
            llm_api_key=clave,
            ollama_url=_env("OLLAMA_URL", defecto="http://localhost:11434"),
            llm_timeout=int(_env("LLM_TIMEOUT", defecto="600")),
            llm_pausa=float(_env("LLM_PAUSA", defecto="0")),
            ids_en_cuerpo=_env("SITA_IDS_EN_CUERPO", defecto="0") == "1",
            log_path=Path(_env("SITA_LOG", defecto=str(RAIZ / "logs" / "interacciones_pg3.jsonl"))),
        )
