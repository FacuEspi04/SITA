"""Contrato común de los submódulos: todos devuelven una Seccion con la misma forma.

Es lo que hace que PG3 sea un sistema y no cuatro scripts: el orquestador, el verificador, la
explicación y la auditoría tratan igual el resultado de cualquier submódulo.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..textos import ids_de_regla, limpiar_vacios

# Tipo de decisión experta de cada sección (idea de M4, extendida a los cuatro submódulos)
HABILITACION_M1 = "habilitacion_normativa_M1"
VIGENCIA_M1 = "vigencia_regularidad_M1"
CALIDAD_DATO_M1 = "calidad_del_dato_M1"
CAPACIDAD_M2 = "carga_y_capacidad_M2"
RIESGO_M3 = "riesgo_de_atraso_M3"
ESTRUCTURA_M3 = "estructura_del_plan_M3"
PLANIFICACION_M4 = "recomendacion_planificacion_M4"
SOLICITUD_DATOS = "solicitud_de_datos"


@dataclass
class Seccion:
    modulo: str
    intencion: str
    tipo_decision: str
    consulta_id: str
    parametros: dict
    resultado: dict | None
    estado: str = "ok"                 # ok | sin_datos
    mensaje: str | None = None         # explicación fija cuando no hay datos
    origen: str = "pedido"             # pedido | enriquecimiento | contexto
    motivo: str | None = None          # por qué la agregó el orquestador
    foco: list[str] | None = None      # claves del resultado relevantes (enriquecimiento)
    resultado_crudo: dict | None = field(default=None, repr=False)

    @property
    def reglas(self) -> list[str]:
        from ..textos import orden_natural
        return orden_natural(ids_de_regla(self.resultado or {}))

    def para_llm(self) -> dict:
        d = {"modulo": self.modulo, "tipo_decision": self.tipo_decision,
             "pedida_por": "estudiante" if self.origen == "pedido" else "sistema"}
        if self.motivo:
            d["motivo"] = self.motivo
        if self.estado != "ok":
            d["sin_datos"] = self.mensaje
            return d
        res = self.resultado or {}
        if self.foco:
            res = {k: v for k, v in res.items() if k in self.foco}
        if "glosario_reglas" in res:  # solo el enunciado de las reglas que sustentan esta sección (menos tokens)
            usadas = set(self.reglas)
            res = {**res, "glosario_reglas": [r for r in res["glosario_reglas"] or [] if r.get("id") in usadas]}
        d["resultado"] = limpiar_vacios(res)
        return d

    def para_log(self) -> dict:
        d = asdict(self)
        d.pop("resultado_crudo", None)
        d["reglas"] = self.reglas
        return d


def sin_datos(modulo: str, intencion: str, tipo: str, consulta_id: str, params: dict, mensaje: str) -> Seccion:
    return Seccion(modulo, intencion, tipo, consulta_id, params, None, estado="sin_datos", mensaje=mensaje)
