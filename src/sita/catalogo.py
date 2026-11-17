"""Resolución de entidades contra el grafo: estudiantes y asignaturas (una sola implementación).

Combina lo que cada PI4 hacía por separado: legajo exacto (M1, M4), nombre por tokens (M2),
siglas y alias de uso estudiantil (M3) y sugerencias aproximadas con difflib (M1, M3).
"""
from __future__ import annotations

import difflib

from .textos import norm, tokens

CAT_ESTUDIANTES = "MATCH (e:Estudiante) RETURN toString(e.legajo) AS legajo, e.nombre AS nombre ORDER BY nombre"
CAT_ASIGNATURAS = ("MATCH (a:Asignatura) WHERE a.codigo IS NOT NULL "
                   "RETURN a.codigo AS codigo, a.sigla AS sigla, a.nombre AS nombre ORDER BY codigo")

# Alias de uso estudiantil por código del Plan 2023 (tabla de M3, PI4)
ALIAS = {
    1: ["AM I", "AM1", "Análisis 1", "Analisis I"], 2: ["AGA", "Álgebra"], 3: ["FI", "Física 1", "Fisica 1"],
    4: ["Inglés 1"], 5: ["LED", "Lógica"], 6: ["AED", "Algoritmos"], 7: ["AC", "Arquitectura"], 8: ["SPN"],
    9: ["AM II", "AM2", "Análisis 2"], 10: ["FII", "Física 2", "Fisica 2"], 11: ["IyS"], 12: ["Inglés 2"],
    13: ["SSL", "Sintaxis"], 14: ["PP", "Paradigmas"], 15: ["SO", "Operativos"], 16: ["ASI"],
    17: ["PyE", "Proba", "Probabilidad"], 18: ["ECO"], 19: ["BD", "Bases de Datos", "Base de datos"],
    20: ["DS", "Desarrollo"], 21: ["COM", "Comunicaciones", "Comunicación de datos"], 22: ["AN", "Numérico"],
    23: ["DSI"], 24: ["LEG"], 25: ["ICS"], 26: ["RD", "Redes"], 27: ["IO", "Operativa"], 28: ["SIM", "Simu"],
    29: ["TA", "Automatización"], 30: ["ADSI"], 31: ["IA"], 32: ["CD"], 33: ["SG"], 34: ["GG"], 35: ["SSI"],
    36: ["PF", "Proyecto"], 37: ["SI", "Seminario"],
}


class Catalogo:
    def __init__(self, estudiantes: list[dict], asignaturas: list[dict]):
        self.estudiantes = [{"legajo": str(e["legajo"]), "nombre": e["nombre"]} for e in estudiantes]
        self.asignaturas = asignaturas
        self.indice: dict[str, dict] = {}
        for a in asignaturas:
            claves = [a.get("nombre") or "", a.get("sigla") or ""] + ALIAS.get(a.get("codigo"), [])
            for c in claves:
                if c:
                    self.indice.setdefault(norm(c), a)

    @classmethod
    def desde_kb(cls, kb) -> "Catalogo":
        return cls(kb.leer("CAT_ESTUDIANTES", CAT_ESTUDIANTES), kb.leer("CAT_ASIGNATURAS", CAT_ASIGNATURAS))

    # ------------------------------------------------------------------ estudiantes
    def resolver_estudiante(self, legajo: str | None, nombre: str | None) -> tuple[dict | None, str | None]:
        if legajo:
            for e in self.estudiantes:
                if e["legajo"] == legajo:
                    return e, None
            return None, f"No encuentro el legajo {legajo} en la base de conocimiento. Revisalo, por favor."
        if nombre:
            tk = tokens(nombre)
            hits = [e for e in self.estudiantes if tk and tk <= tokens(e["nombre"])]
            if len(hits) == 1:
                return hits[0], None
            if len(hits) > 1:
                return None, "Hay más de un estudiante con ese nombre. ¿Me pasás tu legajo?"
            return None, "No encontré a ese estudiante. Revisá cómo escribiste tu nombre o pasame tu legajo."
        return None, "Para responderte necesito saber quién sos: ¿me pasás tu legajo?"

    # ------------------------------------------------------------------ asignaturas
    def por_nombre(self, nombre: str) -> dict | None:
        return self.indice.get(norm(nombre))

    def por_codigo(self, codigo) -> dict | None:
        return next((a for a in self.asignaturas if a.get("codigo") == codigo), None)

    def resolver_asignatura(self, texto: str) -> tuple[dict | None, str | None]:
        k = norm(texto)
        if not k:
            return None, "¿Sobre qué asignatura querés saber?"
        if k in self.indice:
            return self.indice[k], None
        tk = tokens(texto)
        hits = [a for a in self.asignaturas if tk and tk <= tokens(a.get("nombre"))]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, f"«{texto}» coincide con varias asignaturas: " + ", ".join(a["nombre"] for a in hits[:6]) + ". ¿Cuál?"
        cerca = difflib.get_close_matches(k, list(self.indice), n=1, cutoff=0.85)
        if cerca:
            return self.indice[cerca[0]], None
        sug = difflib.get_close_matches(k, [norm(a["nombre"]) for a in self.asignaturas], n=3, cutoff=0.5)
        nombres = [a["nombre"] for a in self.asignaturas if norm(a["nombre"]) in sug]
        extra = f" ¿Quisiste decir {' o '.join(nombres)}?" if nombres else ""
        return None, f"«{texto}» no es una asignatura del Plan 2023.{extra}"
