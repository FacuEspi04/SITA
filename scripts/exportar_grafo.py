"""Exporta el grafo PG2 completo a JSON (nodos y relaciones) para la carpeta base_conocimiento/ del ZIP.

Complementa al script Grupo_19_PG2_U1.cypher (que reconstruye la base) cuando el plan de Aura no permite
descargar un snapshot. Solo lectura.

Uso:  python scripts/exportar_grafo.py [salida.json]
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sita.config import Config  # noqa: E402
from sita.kb import BaseConocimiento  # noqa: E402

NODOS = "MATCH (n) RETURN elementId(n) AS id, labels(n) AS etiquetas, properties(n) AS propiedades"
RELACIONES = ("MATCH (a)-[r]->(b) RETURN elementId(r) AS id, type(r) AS tipo, elementId(a) AS desde, "
              "elementId(b) AS hacia, properties(r) AS propiedades")


def main() -> None:
    salida = Path(sys.argv[1] if len(sys.argv) > 1 else "base_conocimiento/grafo_pg2_export.json")
    salida.parent.mkdir(parents=True, exist_ok=True)
    kb = BaseConocimiento(Config.desde_entorno())
    try:
        nodos, rels = kb.leer("export_nodos", NODOS), kb.leer("export_relaciones", RELACIONES)
    finally:
        kb.cerrar()
    datos = {"exportado": datetime.now().isoformat(timespec="seconds"), "nodos": nodos, "relaciones": rels,
             "resumen": {"nodos": len(nodos), "relaciones": len(rels)}}
    salida.write_text(json.dumps(datos, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    print(f"Exportados {len(nodos)} nodos y {len(rels)} relaciones a {salida}")


if __name__ == "__main__":
    main()
