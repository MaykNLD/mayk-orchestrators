"""
Career-Ops Orchestrator — FastAPI  | Puerto 8020
Multi-usuario: cada request puede especificar perfil_id
"""
import os, json, sys, urllib.request
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from supabase_client import (
    list_perfiles, get_perfil_by_id, get_first_perfil,
    create_application, update_application,
    get_all_applications, get_applications_by_perfil, log_ejecucion
)

EVALUADOR_URL = os.environ.get("AGENTE_HR_EVALUADOR_URL", "http://localhost:8011")
SASTRE_URL    = os.environ.get("AGENTE_HR_SASTRE_URL",    "http://localhost:8012")
MAKE_WEBHOOK  = os.environ.get("MAKE_WEBHOOK_URL", "")
MIN_SCORE     = float(os.environ.get("CAREER_MIN_SCORE", "3.0"))

app = FastAPI(title="Career-Ops Orchestrator", version="1.1.0")

class EvaluarRequest(BaseModel):
    url_oferta:   Optional[str] = None
    texto_oferta: Optional[str] = None
    perfil_id:    Optional[str] = None  # Si None → usa el primero disponible
    idioma:       str = "ES"

class TrackerRequest(BaseModel):
    perfil_id: Optional[str] = None    # Si None → todas las candidaturas

def call_agent(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(f"{url}/execute", data=data,
           headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())

def notify_make(payload: dict):
    if not MAKE_WEBHOOK:
        return
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(MAKE_WEBHOOK, data=data,
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
    return {"status": "ok", "version": "1.1.0", "agents": agents, "min_score": MIN_SCORE}

@app.get("/career/perfiles")
def listar_perfiles():
    """Lista todos los perfiles disponibles."""
    perfiles = list_perfiles()
    return {"total": len(perfiles), "perfiles": perfiles}

@app.post("/career/evaluar")
def evaluar(req: EvaluarRequest):
    if not req.url_oferta and not req.texto_oferta:
        raise HTTPException(400, "Proporciona url_oferta o texto_oferta")

    # Resolver perfil: por ID o el primero disponible
    if req.perfil_id:
        perfil = get_perfil_by_id(req.perfil_id)
        if not perfil:
            raise HTTPException(404, f"Perfil {req.perfil_id} no encontrado")
    else:
        perfil = get_first_perfil()
        if not perfil:
            raise HTTPException(404, "No hay perfiles en Supabase. Inserta al menos uno en perfil_base.")

    app_record = create_application({
        "perfil_id": perfil["id"],
        "job_title": "Pendiente de evaluacion",
        "company":   "Pendiente",
        "url":       req.url_oferta or "",
        "status":    "evaluando",
    })
    app_id = app_record.get("id")

    try:
        eval_resp = call_agent(EVALUADOR_URL, {
            "url_oferta":       req.url_oferta or "",
            "texto_oferta":     req.texto_oferta or "",
            "perfil_base_json": perfil.get("datos_json", {}),
            "idioma":           req.idioma,
        })
        fit_score     = eval_resp.get("fit_score", 0.0)
        grado         = eval_resp.get("grado", "F")
        recomendacion = eval_resp.get("recomendacion", "Descartar")
        raw_analysis  = json.loads(eval_resp.get("result", "{}"))

        if app_id:
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
        "perfil":        f"{perfil['nombre']} {perfil['apellido']}",
        "fit_score":     fit_score,
        "grado":         grado,
        "recomendacion": recomendacion,
        "bloques":       raw_analysis,
    }

    if fit_score >= MIN_SCORE:
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). Generando CV adaptado..."
        result["estado"]  = "procesando"
    else:
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). Oferta descartada (minimo {MIN_SCORE})."
        result["estado"]  = "descartado"
        notify_make({"company": "?", "role": "?", "score": fit_score, "grado": grado,
                     "perfil": result["perfil"], "status": "descartado"})
    return result

@app.get("/career/tracker")
def tracker(perfil_id: Optional[str] = None):
    """Candidaturas de un perfil concreto o de todos si no se especifica."""
    if perfil_id:
        apps = get_applications_by_perfil(perfil_id)
    else:
        apps = get_all_applications()
    return {"total": len(apps), "aplicaciones": apps}