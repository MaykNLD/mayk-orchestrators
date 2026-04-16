"""
Orquestador Maestro — Microservicio FastAPI
Puerto: 8000
Coordina los 5 agentes, gestiona fases, persiste en Supabase
y envía un único evento batch a Make.com al finalizar.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error

import requests
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

MAKE_WEBHOOK_URL  = os.environ.get("MAKE_WEBHOOK_URL", "")
SUPABASE_URL      = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SECRET   = os.environ.get("SUPABASE_SECRET_KEY", "")

app = FastAPI(
    title="mayk.dev Orquestador",
    description="Coordina el flujo de fases entre los 5 agentes especializados.",
    version="4.1.0",
)


# ──────────────────────────────────────────────────────────────────────────────
# Supabase REST helpers
# ──────────────────────────────────────────────────────────────────────────────
def _supa_headers() -> dict:
    return {
        "apikey": SUPABASE_SECRET,
        "Authorization": f"Bearer {SUPABASE_SECRET}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def supa_insert(table: str, data: dict) -> dict | None:
    """Inserta una fila en Supabase y devuelve la fila creada (con id)."""
    if not SUPABASE_URL or not SUPABASE_SECRET:
        return None
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_supa_headers(),
            json=data,
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else None
    except Exception as e:
        print(f"[Supabase] Error insert '{table}': {e}", file=sys.stderr)
        return None


def supa_update(table: str, row_id: str, data: dict) -> bool:
    """Actualiza una fila por id en Supabase."""
    if not SUPABASE_URL or not SUPABASE_SECRET:
        return False
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}",
            headers={**_supa_headers(), "Prefer": "return=minimal"},
            json=data,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Supabase] Error update '{table}' id={row_id}: {e}", file=sys.stderr)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Agente caller
# ──────────────────────────────────────────────────────────────────────────────
def call_agent(agent_id: str, payload: dict) -> str:
    """Llamada HTTP interna a un microservicio agente."""
    url = AGENT_URLS.get(agent_id)
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


# ──────────────────────────────────────────────────────────────────────────────
# Make.com notifier
# ──────────────────────────────────────────────────────────────────────────────
def notify_make(batch: dict) -> bool:
    """
    Envía UN SOLO evento batch a Make.com al final del proyecto completo.
    Economiza créditos: 1 llamada = 1 crédito consumido.
    """
    if not MAKE_WEBHOOK_URL:
        return False
    try:
        resp = requests.post(MAKE_WEBHOOK_URL, json=batch, timeout=15)
        return resp.status_code == 200
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Modelos de entrada / salida
# ──────────────────────────────────────────────────────────────────────────────
class ProyectoRequest(BaseModel):
    nombre_proyecto:  str
    tipo_proyecto:    str          # landing | ecommerce | saas | app-movil | pwa | crm
    objetivo:         str
    url_existente:    str | None = None
    stack_existente:  str | None = None
    presupuesto:      str | None = None
    integraciones:    list[str]  = []
    notify_make:      bool       = True


class OrquestadorResponse(BaseModel):
    proyecto:          str
    ejecucion_id:      str | None = None   # UUID en Supabase
    fase_1_auditoria:  str | None = None
    fase_1_estrategia: str
    fase_2_diseno:     str
    fase_2_dev:        str
    fase_3_qa:         str
    make_notified:     bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "orchestrator": "mayk.dev", "version": "4.1.0",
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
      Fin: Persistencia en Supabase + Notificación batch a Make.com
    """
    t_inicio = time.time()

    # Mapeo de tipos de CLI a la DB ENUM ('tipo_proyecto_enum')
    enum_map = {
        "landing":   "landing-page",
        "ecommerce": "e-commerce",
        "saas":      "saas-dashboard",
        "crm":       "sistema-crm-apis",
        "pwa":       "web-corporativa",
        "app-movil": "saas-dashboard"
    }
    tipo_db = enum_map.get(req.tipo_proyecto, "landing-page")

    # ── Persistir proyecto en Supabase ─────────────────────────────────────
    proyecto_row = supa_insert("proyectos", {
        "nombre":          req.nombre_proyecto,
        "tipo":            tipo_db,
        "objetivo":        req.objetivo,
        "url_existente":   req.url_existente,
        "stack_existente": req.stack_existente,
        "presupuesto":     req.presupuesto,
        "integraciones":   req.integraciones,
    })
    proyecto_id = proyecto_row["id"] if proyecto_row else None

    # ── Crear registro de ejecución (estado EN_PROCESO) ────────────────────
    ejecucion_row = supa_insert("ejecuciones", {
        "proyecto_id": proyecto_id,
        "estado":      "EN_PROCESO",
    }) if proyecto_id else None
    ejecucion_id = ejecucion_row["id"] if ejecucion_row else None

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

    # ── FASE 2A: Diseño ────────────────────────────────────────────────────
    diseno_result = call_agent("agente-visual", {
        "tipo_proyecto": req.tipo_proyecto,
        "requisitos":    estrategia_result[:2000],
    })

    # ── FASE 2B: Dev ───────────────────────────────────────────────────────
    stack_detectado = req.stack_existente or "react-node"
    dev_result = call_agent("agente-dev", {
        "stack":      stack_detectado,
        "requisitos": estrategia_result[:1500],
        "diseno":     diseno_result[:1000],
    })

    # ── FASE 3: QA-Ops ──────────────────────────────────────────────────────
    qa_result = call_agent("agente-qa-ops", {
        "url_proyecto":  req.url_existente,
        "codigo_fuente": dev_result[:3000],
        "tipo_proyecto": req.tipo_proyecto,
    })

    # ── NOTIFICACIÓN BATCH A MAKE (1 sola llamada, 1 crédito) ──────────────
    make_ok = False
    make_payload = {
        "proyecto":          req.nombre_proyecto,
        "tipo":              req.tipo_proyecto,
        "fase_1_estrategia": estrategia_result[:500],
        "fase_2_dev":        dev_result[:500],
        "fase_3_qa":         qa_result[:500],
        "estado":            "COMPLETADO",
        "ejecucion_id":      ejecucion_id,
    }
    if req.notify_make:
        make_ok = notify_make(make_payload)

    # ── Persistir en Make webhooks log ─────────────────────────────────────
    if ejecucion_id:
        supa_insert("make_webhooks_log", {
            "ejecucion_id": ejecucion_id,
            "payload":      make_payload,
            "enviado_ok":   make_ok,
            "http_status":  200 if make_ok else None,
        })

    # ── Actualizar ejecución como COMPLETADA en Supabase ───────────────────
    duracion_ms = int((time.time() - t_inicio) * 1000)
    if ejecucion_id:
        supa_update("ejecuciones", ejecucion_id, {
            "estado":            "COMPLETADO",
            "fase_1_auditoria":  auditoria_result,
            "fase_1_estrategia": estrategia_result,
            "fase_2_diseno":     diseno_result,
            "fase_2_dev":        dev_result,
            "fase_3_qa":         qa_result,
            "make_notificado":   make_ok,
            "duracion_ms":       duracion_ms,
        })

    return OrquestadorResponse(
        proyecto=           req.nombre_proyecto,
        ejecucion_id=       ejecucion_id,
        fase_1_auditoria=   auditoria_result,
        fase_1_estrategia=  estrategia_result,
        fase_2_diseno=      diseno_result,
        fase_2_dev=         dev_result,
        fase_3_qa=          qa_result,
        make_notified=      make_ok,
    )
