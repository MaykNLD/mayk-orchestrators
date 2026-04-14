"""
Orquestador Maestro — Microservicio FastAPI
Puerto: 8000
Coordina los 5 agentes, gestiona fases y envía un único evento batch a Make.com
"""
import os
import sys
import json
import urllib.request
import urllib.error

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────────────────────
# URLs internas de los agentes (dentro de la red Docker)
# ──────────────────────────────────────────────────────────────────────────────
AGENT_URLS = {
    "agente-auditor":   "http://agente-auditor:8001/execute",
    "agente-estratega": "http://agente-estratega:8002/execute",
    "agente-visual":    "http://agente-visual:8003/execute",
    "agente-dev":       "http://agente-dev:8004/execute",
    "agente-qa-ops":    "http://agente-qa-ops:8005/execute",
}

MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "")

app = FastAPI(
    title="mayk.dev Orquestador",
    description="Coordina el flujo de fases entre los 5 agentes especializados.",
    version="4.0.0",
)


def call_agent(agent_id: str, payload: dict) -> str:
    """Llamada HTTP interna a un microservicio agente."""
    url  = AGENT_URLS.get(agent_id)
    if not url:
        return f"ERROR: Agente '{agent_id}' no registrado."
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data,
                                   headers={"Content-Type": "application/json"},
                                   method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode()).get("result", "")
    except urllib.error.HTTPError as e:
        return f"ERROR [{e.code}]: {e.read().decode()}"
    except Exception as e:
        return f"ERROR: {str(e)}"


def notify_make(batch: dict) -> bool:
    """
    Envía UN SOLO evento batch a Make.com al final del proyecto completo.
    Economiza créditos: 1 llamada = 1 crédito consumido.
    """
    if not MAKE_WEBHOOK_URL:
        return False
    data = json.dumps(batch).encode()
    req  = urllib.request.Request(MAKE_WEBHOOK_URL, data=data,
                                   headers={"Content-Type": "application/json"},
                                   method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Modelos de entrada
# ──────────────────────────────────────────────────────────────────────────────
class ProyectoRequest(BaseModel):
    nombre_proyecto:  str
    tipo_proyecto:    str          # landing | ecommerce | saas | app-movil | pwa | crm
    objetivo:         str
    url_existente:    str | None = None
    stack_existente:  str | None = None
    presupuesto:      str | None = None
    integraciones:    list[str]  = []
    notify_make:      bool       = True  # Activar notificación batch a Make.com


class OrquestadorResponse(BaseModel):
    proyecto:         str
    fase_1_auditoria: str | None = None
    fase_1_estrategia: str
    fase_2_diseno:    str
    fase_2_dev:       str
    fase_3_qa:        str
    make_notified:    bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "orchestrator": "mayk.dev", "version": "4.0.0",
            "agents": list(AGENT_URLS.keys())}


@app.get("/agents/health")
def agents_health():
    """Comprueba que todos los agentes responden."""
    results = {}
    for agent_id, base_url in AGENT_URLS.items():
        health_url = base_url.replace("/execute", "/health")
        req = urllib.request.Request(health_url)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                results[agent_id] = "ok"
        except Exception as e:
            results[agent_id] = f"down: {str(e)}"
    return results


@app.post("/proyecto/ejecutar", response_model=OrquestadorResponse)
def ejecutar_proyecto(req: ProyectoRequest):
    """
    Flujo completo de 3 fases:
      Fase 1: Auditoría (opcional) + Estrategia
      Fase 2: Diseño + Dev
      Fase 3: QA-Ops
      Fin: Notificación batch única a Make.com
    """

    # ── FASE 1A: Auditoría (solo si hay proyecto existente) ────────────────
    auditoria_result = None
    if req.url_existente or req.stack_existente:
        auditoria_result = call_agent("agente-auditor", {
            "url_actual":    req.url_existente,
            "codigo_fuente": req.stack_existente,
            "tipo_proyecto": req.tipo_proyecto,
        })

    # ── FASE 1B: Estrategia ────────────────────────────────────────────────
    estrategia_result = call_agent("agente-estratega", {
        "tipo_proyecto":   req.tipo_proyecto,
        "objetivo":        req.objetivo,
        "integraciones":   req.integraciones,
        "presupuesto":     req.presupuesto,
        "stack_existente": req.stack_existente,
    })

    # ── FASE 2A: Diseño (recibe resumen compacto de estrategia) ───────────
    diseno_result = call_agent("agente-visual", {
        "tipo_proyecto": req.tipo_proyecto,
        "requisitos":    estrategia_result[:2000],  # Solo lo esencial
    })

    # ── FASE 2B: Dev (recibe stack + diseño) ──────────────────────────────
    # Extraer stack de la respuesta del estratega (simplificado)
    stack_detectado = req.stack_existente or "react-node"
    dev_result = call_agent("agente-dev", {
        "stack":       stack_detectado,
        "requisitos":  estrategia_result[:1500],
        "diseno":      diseno_result[:1000],
    })

    # ── FASE 3: QA-Ops ─────────────────────────────────────────────────────
    qa_result = call_agent("agente-qa-ops", {
        "url_proyecto":  req.url_existente,
        "codigo_fuente": dev_result[:3000],
        "tipo_proyecto": req.tipo_proyecto,
    })

    # ── NOTIFICACIÓN BATCH A MAKE (1 sola llamada, 1 crédito) ─────────────
    make_ok = False
    if req.notify_make:
        batch = {
            "proyecto":         req.nombre_proyecto,
            "tipo":             req.tipo_proyecto,
            "fase_1_estrategia": estrategia_result[:500],
            "fase_2_dev":        dev_result[:500],
            "fase_3_qa":         qa_result[:500],
            "estado":           "COMPLETADO",
        }
        make_ok = notify_make(batch)

    return OrquestadorResponse(
        proyecto=           req.nombre_proyecto,
        fase_1_auditoria=   auditoria_result,
        fase_1_estrategia=  estrategia_result,
        fase_2_diseno=      diseno_result,
        fase_2_dev=         dev_result,
        fase_3_qa=          qa_result,
        make_notified=      make_ok,
    )
