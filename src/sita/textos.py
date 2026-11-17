"""Utilidades de texto compartidas (antes duplicadas en los cuatro PI4)."""
from __future__ import annotations

import json
import re
import unicodedata

# Identificadores de regla del modelo: H-04, X-01, C-04d, E-07d, P-02, RS1, RB2, R0b, RA1 (inventada)...
RE_REGLA = re.compile(r"\b(?:[A-Z]{1,2}-\d{1,2}[a-z]?|R[A-Z]?\d{1,2}[a-z]?)\b")
# Correlatividades del plan de estudios: 33-27-REG, 22-1-APR (no son reglas)
RE_CORRELATIVIDAD = re.compile(r"\b\d{1,2}-\d{1,2}-(?:REG|APR)\b")

_RAROS = {"‐": "-", "‑": "-", "‒": "-", "–": "-", "−": "-",
          " ": " ", " ": " ", " ": " ", "​": "", "﻿": ""}


def limpiar_texto(s: object) -> str:
    """Normaliza guiones tipográficos y espacios especiales que emiten algunos modelos (M1, M2)."""
    s = str(s or "")
    for raro, normal in _RAROS.items():
        s = s.replace(raro, normal)
    return s.strip()


def texto_plano(t: str) -> str:
    """Quita negritas/cursivas de markdown y pone mayúscula inicial (M4)."""
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.M).strip()
    return t[:1].upper() + t[1:]


def sin_acentos(s: object) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def norm(s: object) -> str:
    """Minúsculas, sin tildes ni signos (para comparar nombres)."""
    return re.sub(r"[^a-z0-9 ]+", " ", sin_acentos(s)).strip()


def tokens(s: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", sin_acentos(s)))


def numero_en_texto(valor: object, texto: str) -> bool:
    """El valor extraído por el LLM tiene que estar escrito en el mensaje (anclaje, M3)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return False
    return any(abs(float(n.replace(",", ".")) - v) < 1e-9 for n in re.findall(r"\d+(?:[.,]\d+)?", texto))


def fmt_num(x: object) -> str:
    """0.638 -> '0,638'; 31.0 -> '31'."""
    if isinstance(x, bool) or x is None:
        return str(x)
    if isinstance(x, (int, float)):
        return f"{x:g}".replace(".", ",")
    return str(x)


def fecha_ar(iso: object) -> str:
    """'2027-12-15' -> '15/12/2027'."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso)


def recorrer(obj, ruta: str = ""):
    """Genera (ruta, valor) de todas las hojas de un JSON anidado. Ruta con '/'."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from recorrer(v, f"{ruta}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from recorrer(v, f"{ruta}/{i}")
    else:
        yield ruta, obj


def ids_de_regla(obj, excluir_claves=("glosario_reglas", "glosario", "enunciado")) -> set[str]:
    """Ids de regla presentes en un resultado, sin contar los glosarios (M4: el glosario no es evidencia) ni los
    ids que aparecen DENTRO del texto de un enunciado (p. ej. «sin H-09» en E-03, que no es una regla aplicada)."""
    ids: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in excluir_claves:
                continue
            ids |= ids_de_regla(v, excluir_claves)
    elif isinstance(obj, list):
        for v in obj:
            ids |= ids_de_regla(v, excluir_claves)
    elif isinstance(obj, str):
        ids |= set(RE_REGLA.findall(limpiar_texto(obj)))
    return ids


def orden_natural(ids) -> list[str]:
    def clave(i: str):
        m = re.match(r"([A-Z]+)-?(\d+)([a-z]?)", i)
        return (m.group(1), int(m.group(2)), m.group(3)) if m else (i, 0, "")
    return sorted(set(ids), key=clave)


def limpiar_vacios(d):
    """Quita claves None/vacías para que el paquete que recibe el LLM sea compacto (M4)."""
    if isinstance(d, dict):
        return {k: limpiar_vacios(v) for k, v in d.items() if v not in (None, [], {}, "")}
    if isinstance(d, list):
        return [limpiar_vacios(x) for x in d if x not in (None, [], {}, "")]
    return d


def a_json(obj, indent: int | None = None) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, indent=indent)
