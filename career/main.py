"""
Career-Ops Orchestrator — FastAPI | Puerto 8020
Multi-usuario: cada request puede especificar perfil_id
Flujo: Evaluador → (si score>=MIN) Sastre en background → PDF → Supabase → Make
"""
import os, json, sys, urllib.request, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

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

app = FastAPI(title="Career-Ops Orchestrator", version="1.2.0")

class EvaluarRequest(BaseModel):
    url_oferta:   Optional[str] = None
    texto_oferta: Optional[str] = None
    perfil_id:    Optional[str] = None
    idioma:       str = "ES"


def call_agent(url: str, payload: dict, timeout: int = 180) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(f"{url}/execute", data=data,
           headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
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


def run_sastre_background(app_id: str, perfil: dict, raw_analysis: dict, idioma: str):
    """Llama al sastre en un hilo separado para no bloquear la respuesta al usuario."""
    try:
        sastre_resp = call_agent(SASTRE_URL, {
            "perfil_base_json":        perfil.get("datos_json", {}),
            "analisis_evaluador_json": raw_analysis,
            "idioma":                  idioma,
            "mercado_geografico":      perfil.get("mercado", "ES"),
        }, timeout=120)

        cv_data = json.loads(sastre_resp.get("result", "{}"))

        # Intentar generar PDF
        pdf_url = None
        try:
            from generate_pdf import generar_pdf
            pdf_url = generar_pdf(cv_data, app_id)
        except Exception:
            pass

        update_application(app_id, {
            "tailored_content": cv_data,
            "keywords":         sastre_resp.get("keywords_insertadas", []),
            "pdf_url":          pdf_url or "",
            "status":           "cv_generado",
        })

        # Notificar a Make + Telegram
        empresa  = raw_analysis.get("bloque_a", {}).get("empresa", "?") if isinstance(raw_analysis.get("bloque_a"), dict) else "?"
        rol      = raw_analysis.get("bloque_a", {}).get("rol", "?")     if isinstance(raw_analysis.get("bloque_a"), dict) else "?"
        fit_sc   = raw_analysis.get("fit_score", 0.0)
        grado    = raw_analysis.get("grado", "?")
        notify_make({
            "company": empresa,
            "role":    rol,
            "score":   fit_sc,
            "grado":   grado,
            "perfil":  f"{perfil.get('nombre','')} {perfil.get('apellido','')}",
            "status":  "cv_generado",
            "mensaje": f"CV adaptado generado. PDF: {pdf_url or 'pendiente'}",
        })

    except Exception as e:
        if app_id:
            update_application(app_id, {"status": "error_sastre", "notas": str(e)})


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
    return {"status": "ok", "version": "1.2.0", "agents": agents, "min_score": MIN_SCORE}


@app.get("/career/perfiles")
def listar_perfiles():
    perfiles = list_perfiles()
    return {"total": len(perfiles), "perfiles": perfiles}


@app.post("/career/evaluar")
def evaluar(req: EvaluarRequest):
    if not req.url_oferta and not req.texto_oferta:
        raise HTTPException(400, "Proporciona url_oferta o texto_oferta")

    # Resolver perfil
    if req.perfil_id:
        perfil = get_perfil_by_id(req.perfil_id)
        if not perfil:
            raise HTTPException(404, f"Perfil {req.perfil_id} no encontrado")
    else:
        perfil = get_first_perfil()
        if not perfil:
            raise HTTPException(404, "No hay perfiles en Supabase.")

    app_record = create_application({
        "perfil_id": perfil["id"],
        "job_title": "Pendiente de evaluacion",
        "company":   "Pendiente",
        "url":       req.url_oferta or "",
        "status":    "evaluando",
    })
    app_id = app_record.get("id")

    # Llamar al evaluador
    try:
        eval_resp = call_agent(EVALUADOR_URL, {
            "url_oferta":       req.url_oferta or "",
            "texto_oferta":     req.texto_oferta or "",
            "perfil_base_json": perfil.get("datos_json", {}),
            "idioma":           req.idioma,
        })
        fit_score     = float(eval_resp.get("fit_score", 0.0))
        grado         = eval_resp.get("grado", "F")
        recomendacion = eval_resp.get("recomendacion", "Descartar")
        raw_result    = eval_resp.get("result", "{}")
        try:
            raw_analysis = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
        except Exception:
            raw_analysis = {"error_parsing": str(raw_result)}
            
        raw_analysis["fit_score"] = fit_score
        raw_analysis["grado"]     = grado

        if app_id:
            update_application(app_id, {
                "fit_score":    fit_score,
                "grado":        grado,
                "raw_analysis": raw_analysis,
                "keywords":     raw_analysis.get("keywords_clave", []),
                "status":       "en_proceso" if fit_score >= MIN_SCORE else "descartado",
            })
    except Exception as e:
        if app_id:
            update_application(app_id, {"status": "error_evaluador", "notas": str(e)})
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
        # Lanzar sastre en hilo separado (no bloquea al usuario)
        t = threading.Thread(
            target=run_sastre_background,
            args=(app_id, perfil, raw_analysis, req.idioma),
            daemon=True
        )
        t.start()
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). CV adaptado generandose en background."
        result["estado"]  = "en_proceso"
    else:
        notify_make({
            "company": "?", "role": "?", "score": fit_score, "grado": grado,
            "perfil":  result["perfil"], "status": "descartado",
            "mensaje": f"Oferta descartada (score {fit_score} < {MIN_SCORE})"
        })
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). Oferta descartada."
        result["estado"]  = "descartado"

    return result


@app.get("/career/tracker")
def tracker(perfil_id: Optional[str] = None):
    if perfil_id:
        apps = get_applications_by_perfil(perfil_id)
    else:
        apps = get_all_applications()
    return {"total": len(apps), "aplicaciones": apps}