"""
Career-Ops Orchestrator — FastAPI
Puerto: 8020
Endpoints consumidos por mayk-cli.py opcion 3
"""
import os, json, sys, time, urllib.request
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from supabase_client import (get_pending_applications, get_first_perfil,
                              create_application, update_application,
                              get_pending_applications, log_ejecucion)

EVALUADOR_URL = os.environ.get("AGENTE_HR_EVALUADOR_URL", "http://localhost:8011")
SASTRE_URL    = os.environ.get("AGENTE_HR_SASTRE_URL",    "http://localhost:8012")
MAKE_WEBHOOK  = os.environ.get("MAKE_WEBHOOK_URL", "")
MIN_SCORE     = float(os.environ.get("CAREER_MIN_SCORE", "3.0"))

app = FastAPI(
    title="Career-Ops Orchestrator",
    description="Orquestador central del modulo de busqueda de empleo. Consumido por mayk-cli.py.",
    version="1.0.0",
)

class EvaluarRequest(BaseModel):
    url_oferta:   Optional[str] = None
    texto_oferta: Optional[str] = None
    perfil_id:    Optional[str] = None  # UUID de perfil_base en Supabase
    idioma:       str = "ES"

class ScanRequest(BaseModel):
    max_results: int = 20

class TrackerResponse(BaseModel):
    total: int
    aplicaciones: List[dict]

def call_agent(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{url}/execute", data=data,
          headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())

def notify_make(payload: dict):
    if not MAKE_WEBHOOK:
        return
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(MAKE_WEBHOOK, data=data,
              headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

@app.get("/health")
def health():
    agents = {}
    for name, url in [("evaluador", EVALUADOR_URL), ("sastre", SASTRE_URL)]:
        try:
            req = urllib.request.Request(f"{url}/health")
            with urllib.request.urlopen(req, timeout=3) as r:
                agents[name] = json.loads(r.read().decode()).get("status", "unknown")
        except Exception:
            agents[name] = "offline"
    return {"status": "ok", "version": "1.0.0", "agents": agents, "min_score": MIN_SCORE}

@app.post("/career/evaluar")
def evaluar(req: EvaluarRequest):
    """Evalua una oferta y opcionalmente genera el CV adaptado + PDF."""
    if not req.url_oferta and not req.texto_oferta:
        raise HTTPException(400, "Proporciona url_oferta o texto_oferta")

    perfil = get_first_perfil()
    if not perfil:
        raise HTTPException(404, "No hay perfil base en Supabase. Completa el onboarding.")

    # Crear registro en Supabase
    app_record = create_application({
        "perfil_id":    perfil["id"],
        "job_title":    "Pendiente de evaluacion",
        "company":      "Pendiente",
        "url":          req.url_oferta or "",
        "status":       "evaluando",
    })
    app_id = app_record["id"]

    # Llamar al evaluador
    try:
        eval_resp = call_agent(EVALUADOR_URL, {
            "url_oferta":       req.url_oferta or "",
            "texto_oferta":     req.texto_oferta or "",
            "perfil_base_json": perfil.get("datos_json", {}),
            "idioma":           req.idioma,
        })
        fit_score    = eval_resp.get("fit_score", 0.0)
        grado        = eval_resp.get("grado", "F")
        recomendacion = eval_resp.get("recomendacion", "Descartar")
        raw_analysis  = json.loads(eval_resp.get("result", "{}"))

        # Extraer empresa/rol del bloque A si disponible
        bloque_a = raw_analysis.get("bloque_a", "")
        update_application(app_id, {
            "fit_score":    fit_score,
            "grado":        grado,
            "raw_analysis": raw_analysis,
            "keywords":     raw_analysis.get("keywords_clave", []),
            "status":       "evaluando" if fit_score >= MIN_SCORE else "descartado",
        })
    except Exception as e:
        raise HTTPException(500, f"Error en agente evaluador: {e}")

    result = {
        "aplicacion_id": app_id,
        "fit_score":     fit_score,
        "grado":         grado,
        "recomendacion": recomendacion,
        "bloques":       raw_analysis,
    }

    # Si score suficiente, lanzar sastre en background (no bloquea)
    if fit_score >= MIN_SCORE:
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). Generando CV adaptado en background..."
        result["estado"]  = "procesando"
    else:
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). Oferta descartada (minimo {MIN_SCORE})."
        result["estado"]  = "descartado"
        notify_make({"company": "?", "role": "?", "score": fit_score, "grado": grado, "status": "descartado"})

    return result

@app.get("/career/tracker")
def tracker():
    """Devuelve el estado de todas las candidaturas."""
    from supabase_client import _get
    apps = _get("aplicaciones_career", "order=created_at.desc&limit=50")
    return TrackerResponse(total=len(apps), aplicaciones=apps)

@app.post("/career/scan")
def scan(req: ScanRequest):
    """Lanza el scanner de portales (Nivel 2: ATS APIs)."""
    return {"mensaje": "Scanner en desarrollo. Usa scripts/scanner.py directamente.", "status": "pendiente"}