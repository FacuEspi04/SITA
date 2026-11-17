"""Construcción de los servicios (base, LLM, orquestador) desde la configuración."""
from __future__ import annotations

from .config import Config
from .kb import BaseConocimiento
from .llm import LLM
from .orquestador import Orquestador


def crear(cfg: Config | None = None, con_llm: bool = True):
    cfg = cfg or Config.desde_entorno()
    kb = BaseConocimiento(cfg)
    if not con_llm:
        return cfg, kb, None
    return cfg, kb, Orquestador(kb, LLM(cfg), cfg)
