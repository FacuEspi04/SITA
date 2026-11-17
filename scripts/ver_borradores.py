"""Muestra los borradores del LLM y los controles que fallaron en cada intento (para revisar la verificación).

Uso:  py scripts/ver_borradores.py [traza_id ...]     (sin argumentos: las últimas 5 interacciones)
"""
import json
import sys
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "logs" / "interacciones_pg3.jsonl"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

trazas = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
ids = sys.argv[1:]
elegidas = [t for t in trazas if t.get("traza_id") in ids] if ids else trazas[-5:]
for t in elegidas:
    print("=" * 100, f"\n{t['traza_id']} · {t['entrada']}")
    for i, it in enumerate((t.get("verificacion") or {}).get("intentos", []), 1):
        print(f"\n--- intento {i} · fallas: {json.dumps(it['fallas'], ensure_ascii=False) or 'ninguna'}\n{it['texto']}")
