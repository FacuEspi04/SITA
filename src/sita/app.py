"""API REST y interfaz web de SITA (punto de entrada único para cualquier cliente).

  POST /consultar        {"texto": "...", "sesion_id": "..."} -> respuesta, fundamento, submódulos y traza_id
  GET  /traza/{id}       traza completa de una interacción (enrutamiento, consultas, resultados, verificación)
  GET  /auditar/{id}     trazabilidad: fuente, regla, evidencia, consulta y recorrido del grafo
  GET  /salud            estado de Neo4j y del LLM configurado
  GET  /                 interfaz web mínima de chat

Ejecutar: python -m sita --servidor   (o: uvicorn sita.app:app --port 8000)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from . import __version__
from .trazabilidad import auditar

app = FastAPI(title="SITA — Sistema Inteligente de Trayectoria Académica", version=__version__,
              description="Asistente unificado del Grupo 19 (UTN FRM, IA 2026): M1 habilitación, M2 carga, "
                          "M3 riesgo de atraso, M4 planificación. Conocimiento en Neo4j; LLM como interfaz.")
_estado: dict = {"orq": None}

# Frontend desplegado aparte (p. ej. Vercel): SITA_CORS_ORIGINS="https://sita.vercel.app,https://otro.dominio"
_ORIGENES = [o.strip().rstrip("/") for o in os.getenv("SITA_CORS_ORIGINS", "").split(",") if o.strip()]
if _ORIGENES:
    app.add_middleware(CORSMiddleware, allow_origins=_ORIGENES, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])


def configurar(orquestador) -> None:
    """Permite inyectar un orquestador (pruebas)."""
    _estado["orq"] = orquestador


def orq():
    if _estado["orq"] is None:
        from .servicios import crear
        _, _, o = crear()
        _estado["orq"] = o
    return _estado["orq"]


class Consulta(BaseModel):
    texto: str = Field(min_length=1, max_length=1000)
    sesion_id: str = Field(default="web", max_length=64)


class Respuesta(BaseModel):
    traza_id: str
    respuesta: str
    fundamento: str | None
    modulos_consultados: list[str]
    no_evaluado: list[dict]
    flujo: str | None
    verificada: bool
    segundos: float | None


@app.post("/consultar", response_model=Respuesta)
def consultar(c: Consulta) -> Respuesta:
    t = orq().procesar(c.texto, sesion_id=c.sesion_id)
    v = t.get("verificacion") or {}
    ultimo = (v.get("intentos") or [{}])[-1].get("fallas") or {}
    return Respuesta(traza_id=t["traza_id"], respuesta=t["respuesta"], fundamento=t.get("fundamento"),
                     modulos_consultados=t.get("modulos_consultados") or [], no_evaluado=t.get("no_evaluado") or [],
                     flujo=t.get("flujo"), verificada=not ultimo or bool(v.get("respaldo_deterministico")),
                     segundos=t.get("segundos"))


@app.get("/traza/{traza_id}")
def ver_traza(traza_id: str) -> dict:
    t = orq().traza(traza_id)
    if t is None:
        raise HTTPException(404, "No existe esa traza.")
    return t


@app.get("/auditar/{traza_id}")
def ver_auditoria(traza_id: str) -> dict:
    o = orq()
    t = o.traza(traza_id)
    if t is None:
        raise HTTPException(404, "No existe esa traza.")
    return auditar(t, o.kb)


@app.get("/salud")
def salud() -> dict:
    o = orq()
    try:
        n = o.kb.valor("salud", "MATCH (e:Estudiante) RETURN count(e) AS n")
        neo = {"ok": True, "estudiantes": n, "transporte": getattr(o.kb, "transporte", "?")}
    except Exception as exc:  # noqa: BLE001
        neo = {"ok": False, "error": str(exc)[:200]}
    return {"version": __version__, "neo4j": neo, "llm": getattr(o.llm, "nombre", "?")}


_WEB = Path(__file__).parent / "web" / "index.html"


@app.get("/", response_class=HTMLResponse)
def inicio() -> str:
    """Interfaz de chat (web/index.html); si el archivo no está, la página mínima embebida."""
    try:
        return _WEB.read_text(encoding="utf-8")
    except OSError:
        return PAGINA


@app.get("/config.js", include_in_schema=False)
def config_js() -> Response:
    """Servida por esta API, la interfaz llama al mismo servidor (la copia en Vercel trae su propia URL)."""
    return Response('window.SITA_API = "";\n', media_type="application/javascript")


PAGINA = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SITA · Asistente de trayectoria académica</title>
<style>
 :root{--fondo:#f6f7f9;--tinta:#1d2430;--suave:#5b6574;--borde:#dde1e7;--acento:#1f5fbf}
 *{box-sizing:border-box} body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--fondo);color:var(--tinta)}
 main{max-width:820px;margin:0 auto;padding:24px 16px 120px} h1{font-size:22px;margin:0 0 4px} p.sub{color:var(--suave);margin:0 0 20px}
 .msg{background:#fff;border:1px solid var(--borde);border-radius:10px;padding:14px 16px;margin:12px 0;white-space:pre-wrap}
 .yo{background:#eaf1fc;border-color:#cfdcf3} .meta{font-size:13px;color:var(--suave);margin-top:8px;white-space:normal}
 .meta a{color:var(--acento)} .chip{display:inline-block;border:1px solid var(--borde);border-radius:999px;padding:0 8px;margin-right:4px;font-size:12px}
 form{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid var(--borde);padding:12px}
 .fila{max-width:820px;margin:0 auto;display:flex;gap:8px} input{flex:1;padding:10px 12px;border:1px solid var(--borde);border-radius:8px;font:inherit}
 button{padding:10px 16px;border:0;border-radius:8px;background:var(--acento);color:#fff;font:inherit;cursor:pointer} button:disabled{opacity:.5}
</style></head><body><main>
<h1>SITA</h1><p class="sub">Asistente de trayectoria académica · Ingeniería en Sistemas de Información · UTN FRM · Grupo 19</p>
<div id="chat"></div></main>
<form id="f"><div class="fila"><input id="t" maxlength="1000" placeholder="Ej.: Soy Lucía, legajo 48115. ¿Por qué no puedo cursar IA?" autocomplete="off">
<button id="b">Enviar</button></div></form>
<script>
const chat=document.getElementById('chat'),f=document.getElementById('f'),t=document.getElementById('t'),b=document.getElementById('b');
const sesion='web-'+Math.random().toString(36).slice(2,10);
function burbuja(texto,clase){const d=document.createElement('div');d.className='msg '+(clase||'');d.textContent=texto;chat.appendChild(d);d.scrollIntoView();return d;}
f.addEventListener('submit',async e=>{e.preventDefault();const q=t.value.trim();if(!q)return;burbuja(q,'yo');t.value='';b.disabled=true;
 const espera=burbuja('Consultando la base de conocimiento…');
 try{const r=await fetch('/consultar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texto:q,sesion_id:sesion})});
  const j=await r.json(); if(!r.ok) throw new Error(j.detail||r.status); espera.textContent=j.respuesta;
  const m=document.createElement('div');m.className='meta';
  m.innerHTML=(j.modulos_consultados||[]).map(x=>'<span class="chip">'+x+'</span>').join('')+(j.fundamento?' '+j.fundamento.replace(/</g,'&lt;'):'')+
   ' · <a href="/auditar/'+j.traza_id+'" target="_blank">ver auditoría</a> · '+j.segundos+' s';
  espera.appendChild(m);
 }catch(err){espera.textContent='No pude procesar la consulta: '+err.message;} finally{b.disabled=false;t.focus();}});
</script></body></html>"""
