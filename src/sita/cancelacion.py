"""Cancelación cooperativa de una consulta (botón «Detener» de la interfaz web).

Cuando el estudiante detiene una consulta, el navegador corta la conexión. El servidor lo detecta y activa un
`threading.Event`; el orquestador lo revisa antes de cada llamada al LLM y las esperas entre reintentos (429, 503) se
interrumpen en el acto. La llamada al LLM que ya está en vuelo no se puede cortar: termina, pero no se hace la
siguiente. Así una consulta abandonada no sigue consumiendo cuota del proveedor.

El evento vive en una variable local del hilo: cada consulta corre en su propio hilo del servidor.
"""
from __future__ import annotations

import threading
import time

_hilo = threading.local()


class ConsultaCancelada(Exception):
    """El estudiante detuvo la consulta."""


def activar(evento: threading.Event | None) -> None:
    _hilo.evento = evento


def cancelada() -> bool:
    evento = getattr(_hilo, "evento", None)
    return bool(evento and evento.is_set())


def verificar() -> None:
    if cancelada():
        raise ConsultaCancelada()


def esperar(segundos: float) -> None:
    """Como time.sleep, pero se interrumpe si la consulta se cancela."""
    evento = getattr(_hilo, "evento", None)
    if evento is None:
        time.sleep(segundos)
    elif evento.wait(segundos):
        raise ConsultaCancelada()
