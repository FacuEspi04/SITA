"""Cliente LLM único (antes: cuatro clientes distintos, uno por PI4).

Proveedor por defecto: Groq con openai/gpt-oss-120b (API compatible con OpenAI), el que usaron M1 y M4.
Alternativas sin cambiar código: Ollama local (M2) o Anthropic (M3), con LLM_PROVIDER en el .env.
Incluye los manejos que cada integrante resolvió por separado:
  - 429 del plan gratuito: espera lo que indica el proveedor y reintenta (M1, M2, M4);
  - respuesta vacía de un modelo con razonamiento: duplica el presupuesto de tokens (M3, M4);
  - modelos que no aceptan temperatura: reintenta sin ella (M3).
"""
from __future__ import annotations

import logging
import re
import time

import requests

from .cancelacion import esperar
from .config import Config
from .textos import limpiar_texto


log = logging.getLogger("uvicorn.error")


class ErrorLLM(RuntimeError):
    pass


def mensaje_error(err: Exception, timeout: int) -> str:
    """Mensajes de error comprensibles para quien ejecuta el asistente (M1)."""
    if isinstance(err, requests.exceptions.ReadTimeout):
        return (f"El modelo tardó más de {timeout} s en responder. Probá de nuevo (la primera llamada carga el modelo), "
                "o subí LLM_TIMEOUT en el .env.")
    if isinstance(err, requests.exceptions.ConnectionError):
        return "No se pudo conectar con el LLM. Si usás Ollama, verificá que esté corriendo (`ollama serve`)."
    if "429" in str(err) or "Límite de uso" in str(err):
        return ("El proveedor del LLM limitó el uso incluso después de reintentar. Esperá un minuto o definí "
                "LLM_PAUSA=30 en el .env.")
    return f"Tuve un problema técnico al procesar tu consulta ({type(err).__name__}). Probá de nuevo en unos segundos."


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.proveedor, self.modelo = cfg.llm_provider, cfg.llm_model
        if self.proveedor not in ("openai", "ollama", "anthropic"):
            raise ErrorLLM(f"LLM_PROVIDER desconocido: {self.proveedor}")
        if self.proveedor != "ollama" and not cfg.llm_api_key:
            raise ErrorLLM("Falta la clave del LLM (LLM_API_KEY o GROQ_API_KEY en el .env).")
        self.ultimo: dict = {}
        self._sin_temperatura = False

    @property
    def nombre(self) -> str:
        return f"{self.proveedor}:{self.modelo}"

    # ------------------------------------------------------------------ API pública
    def chat(self, system: str, user: str, json_mode: bool = False, max_tokens: int = 2000,
             json_schema: dict | None = None) -> str:
        if self.proveedor == "ollama":
            return self._ollama(system, user, json_schema or json_mode)
        if self.proveedor == "anthropic":
            return self._anthropic(system, user, max_tokens)
        return self._openai(system, user, json_mode, max_tokens)

    # ------------------------------------------------------------------ proveedores
    @staticmethod
    def _espera_429(r: requests.Response) -> float:
        """Segundos a esperar tras un 429: Retry-After o el «try again in 7.2s» del mensaje de Groq; tope 90 s (M1)."""
        try:
            if r.headers.get("retry-after"):
                return min(float(r.headers["retry-after"]) + 1, 90)
        except ValueError:
            pass
        m = re.search(r"try again in (?:(\d+)m)?(?:([\d.]+)s)?", r.text)
        if m and (m.group(1) or m.group(2)):
            return min(int(m.group(1) or 0) * 60 + float(m.group(2) or 0) + 1, 90)
        return 20.0

    def _post(self, url: str, headers: dict, body: dict) -> dict:
        for intento in range(6):
            t0 = time.perf_counter()
            r = requests.post(url, headers=headers, json=body, timeout=self.cfg.llm_timeout)
            log.info("SITA: LLM %s respondió %s en %.1f s", self.nombre, r.status_code, time.perf_counter() - t0)
            if r.status_code == 429 and intento < 5:
                espera = self._espera_429(r)
                log.warning("SITA: el proveedor del LLM limitó el uso (429); espero %.0f s y reintento (%d/5)",
                            espera, intento + 1)
                esperar(espera)  # se interrumpe si el estudiante detiene la consulta
                continue
            if r.status_code in (500, 502, 503, 504) and intento < 5:
                # proveedor saturado o caído un momento (p. ej. Gemini 503 «high demand»): espera creciente
                espera = (3, 6, 12, 20, 30)[intento]
                log.warning("SITA: el proveedor del LLM respondió %s (saturado); espero %d s y reintento (%d/5)",
                            r.status_code, espera, intento + 1)
                esperar(espera)  # se interrumpe si el estudiante detiene la consulta
                continue
            if r.status_code >= 400:
                raise ErrorLLM(f"{self.nombre} respondió {r.status_code}: {r.text[:400]}")
            return r.json()
        if r.status_code == 429:
            raise ErrorLLM("Límite de uso del proveedor: reintentá en unos segundos.")
        raise ErrorLLM(f"{self.nombre} sigue respondiendo {r.status_code} después de varios reintentos "
                       "(modelo saturado): probá en unos minutos o cambiá LLM_MODEL.")

    def _openai(self, system: str, user: str, json_mode: bool, max_tokens: int) -> str:
        body = {"model": self.modelo, "temperature": 0, "max_tokens": max(max_tokens, 1500),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if "gpt-oss" in self.modelo:  # modelo con razonamiento: bajo para enrutar, medio para explicar (M4)
            body["reasoning_effort"] = "low" if json_mode else "medium"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        url = f"{self.cfg.llm_base_url.rstrip('/')}/chat/completions"
        for _ in range(3):
            datos = self._post(url, {"Authorization": f"Bearer {self.cfg.llm_api_key}"}, body)
            eleccion = datos["choices"][0]
            texto = limpiar_texto(eleccion["message"].get("content") or "")
            self.ultimo = {"finish_reason": eleccion.get("finish_reason"), "uso": datos.get("usage")}
            if texto:
                return texto
            body["max_tokens"] *= 2  # el razonamiento agotó el presupuesto antes de escribir
        raise ErrorLLM("El modelo devolvió una respuesta vacía.")

    def _ollama(self, system: str, user: str, formato) -> str:
        body = {"model": self.modelo, "stream": False, "keep_alive": "30m",
                "options": {"temperature": 0, "num_ctx": 16384},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if isinstance(formato, dict):
            body["format"] = formato   # salida estructurada: Ollama restringe la generación al esquema (M1)
        elif formato:
            body["format"] = "json"
        r = requests.post(f"{self.cfg.ollama_url}/api/chat", json=body, timeout=self.cfg.llm_timeout)
        if r.status_code >= 400:
            raise ErrorLLM(f"Ollama respondió {r.status_code}: {r.text[:300]}")
        return limpiar_texto(r.json()["message"]["content"])

    def _anthropic(self, system: str, user: str, max_tokens: int) -> str:
        headers = {"x-api-key": self.cfg.llm_api_key, "anthropic-version": "2023-06-01"}
        body = {"model": self.modelo, "max_tokens": max_tokens, "system": system,
                "messages": [{"role": "user", "content": user}]}
        if not self._sin_temperatura:
            body["temperature"] = 0
        try:
            datos = self._post("https://api.anthropic.com/v1/messages", headers, body)
        except ErrorLLM as exc:
            if "temperature" not in str(exc) or self._sin_temperatura:
                raise
            self._sin_temperatura = True
            body.pop("temperature", None)
            datos = self._post("https://api.anthropic.com/v1/messages", headers, body)
        return limpiar_texto("".join(b.get("text", "") for b in datos["content"] if b.get("type") == "text"))
