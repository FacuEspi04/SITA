"""Contrato del enrutador (Pydantic): catálogo único de intenciones y validación de la salida del LLM.

Cada intención tiene UN dueño (corrige las intenciones duplicadas de los PI4: «dictamen» estaba en
M1, M2 y M4; «plan» en M2 y M4). El submódulo lo fija este catálogo, no el modelo: si el LLM escribe
otro módulo para una intención, se corrige y queda registrado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator


@dataclass(frozen=True)
class Intencion:
    modulo: str
    requiere_estudiante: bool
    requiere_asignatura: bool
    descripcion: str


INTENCIONES: dict[str, Intencion] = {
    "dictamen_asignatura": Intencion("M1", True, True, "si puede cursar o rendir una asignatura y por qué"),
    "habilitaciones": Intencion("M1", True, False, "qué asignaturas puede cursar en el período"),
    "vigencia_regularidad": Intencion("M1", True, False, "vigencia o vencimiento de regularidades"),
    "estado_historia": Intencion("M1", True, False, "confiabilidad de la historia y datos a actualizar"),
    "capacidad": Intencion("M2", True, False, "carga, capacidad, holgura, sobrecarga y tamaño del plan"),
    "riesgo_atraso": Intencion("M3", True, False, "riesgo de atraso (también escenario hipotético de horas)"),
    "arrastres": Intencion("M3", True, False, "asignaturas que arrastra de niveles anteriores"),
    "urgencias_vencimiento": Intencion("M3", True, False, "regularidades o finales por vencer"),
    "criticidad_asignatura": Intencion("M3", False, True, "si una asignatura es llave y cuánto pesa"),
    "plan": Intencion("M4", True, False, "qué conviene cursar o rendir y en qué orden"),
    "decision_plan_asignatura": Intencion("M4", True, True, "qué decidió el plan sobre una asignatura"),
}

ORDEN_MODULOS = {"M1": 1, "M2": 2, "M3": 3, "M4": 4, "X": 0}

NombreIntencion = Literal[
    "dictamen_asignatura", "habilitaciones", "vigencia_regularidad", "estado_historia", "capacidad",
    "riesgo_atraso", "arrastres", "urgencias_vencimiento", "criticidad_asignatura", "plan",
    "decision_plan_asignatura",
]


class Pedido(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modulo: Optional[Literal["M1", "M2", "M3", "M4"]] = None
    intencion: NombreIntencion
    asignaturas: list[str] = Field(default_factory=list, max_length=4)
    alcance: Optional[Literal["cursar", "rendir"]] = None
    filtro: Literal["todas", "habilitadas", "bloqueadas"] = "todas"

    @field_validator("asignaturas", mode="before")
    @classmethod
    def _lista(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator("filtro", mode="before")
    @classmethod
    def _filtro(cls, v):
        return v or "todas"


class Enrutamiento(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legajo: Optional[str] = None
    nombre_estudiante: Optional[str] = None
    horas_hipoteticas: Optional[float] = None
    horizonte_meses: Optional[float] = None
    pedidos: list[Pedido] = Field(default_factory=list, max_length=4)
    fuera_de_dominio: bool = False
    faltantes: list[str] = Field(default_factory=list)

    _correcciones: list[str] = PrivateAttr(default_factory=list)

    @field_validator("legajo", mode="before")
    @classmethod
    def _legajo(cls, v):
        if v in (None, ""):
            return None
        solo = re.sub(r"\D", "", str(v))
        return solo or None

    @field_validator("nombre_estudiante", mode="before")
    @classmethod
    def _nombre(cls, v):
        return (str(v).strip() or None) if v is not None else None

    @model_validator(mode="after")
    def _modulo_por_catalogo(self):
        vistos, unicos = set(), []
        for p in self.pedidos:
            dueno = INTENCIONES[p.intencion].modulo
            if p.modulo != dueno:
                if p.modulo is not None:
                    self._correcciones.append(f"{p.intencion}: el LLM indicó {p.modulo}, el catálogo asigna {dueno}")
                p.modulo = dueno
            clave = (p.intencion, tuple(a.lower() for a in p.asignaturas), p.alcance, p.filtro)
            if clave not in vistos:
                vistos.add(clave)
                unicos.append(p)
        self.pedidos = unicos
        return self

    @property
    def correcciones(self) -> list[str]:
        return list(self._correcciones)
