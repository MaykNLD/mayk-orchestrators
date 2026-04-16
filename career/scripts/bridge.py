"""
bridge.py — Orquestador programatico del modulo career

Procesa candidaturas pendientes en Supabase de forma automatica:
  1. Lee aplicaciones con status=pendiente
  2. Llama a agente-hr-evaluador
  3. Si score >= MIN_SCORE: llama a agente-hr-sastre + genera PDF
  4. Actualiza Supabase + notifica Make.com/Telegram

Uso: python bridge.py [--once] [--app-id UUID]
"""
import os, json, sys, time, urllib.request, urllib.error, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from supabase_client import (get_pending_applications, get_perfil_base, get_first_perfil,
                              update_application, log_ejecucion, create_application)
from generate_pdf import generate_pdf

EVALUADOR_URL = os.environ.get("AGENTE_HR_EVALUADOR_URL", "http://localhost:8011")
SASTRE_URL    = os.environ.get("AGENTE_HR_SASTRE_URL",    "http://localhost:8012")
MAKE_WEBHOOK  = os.environ.get("MAKE_WEBHOOK_URL", "")
MIN_SCORE     = float(os.environ.get("CAREER_MIN_SCORE", "3.0"))
TEMPLATE_ES   = Path(__file__).parent.parent / "plantillas" / "cv-template.html"
OUTPUT_DIR    = Path(__file__).parent.parent / "output"

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
    except Exception as e:
        print(f"  Make.com notificacion fallida: {e}")

def process_application(app: dict, perfil: dict):
    app_id   = app["id"]
    company  = app.get("company", "desconocida")
    role     = app.get("job_title", "desconocido")
    idioma   = perfil.get("idioma", "ES")
    t_start  = time.time()

    print(f"\n→ Procesando: {company} — {role}")
    update_application(app_id, {"status": "evaluando"})

    # 1. EVALUACION
    try:
        eval_resp = call_agent(EVALUADOR_URL, {
            "url_oferta":       app.get("url", ""),
            "perfil_base_json": perfil.get("datos_json", {}),
            "idioma":           idioma,
        })
        fit_score   = eval_resp.get("fit_score", 0.0)
        grado       = eval_resp.get("grado", "F")
        raw_analysis = json.loads(eval_resp.get("result", "{}"))

        update_application(app_id, {
            "fit_score":    fit_score,
            "grado":        grado,
            "legitimacy":   raw_analysis.get("bloque_g", {}).get("assessment", ""),
            "raw_analysis": raw_analysis,
            "keywords":     raw_analysis.get("keywords_clave", []),
        })
        log_ejecucion({"aplicacion_id": app_id, "etapa": "evaluacion",
                       "modelo_ia": "gemini-2.5-pro", "resultado": "ok",
                       "duracion_ms": int((time.time()-t_start)*1000)})
        print(f"  Evaluacion: {grado} ({fit_score}/5)")
    except Exception as e:
        update_application(app_id, {"status": "descartado", "notas": f"Error evaluacion: {e}"})
        print(f"  ERROR evaluacion: {e}")
        return

    # Si score bajo: descartar
    if fit_score < MIN_SCORE:
        update_application(app_id, {"status": "descartado",
                                    "notas": f"Score {fit_score} < {MIN_SCORE} (grado {grado})"})
        notify_make({"company": company, "role": role, "score": fit_score, "grado": grado,
                     "status": "descartado", "pdf_url": None})
        print(f"  Descartado: score bajo ({fit_score})")
        return

    # 2. ADAPTACION CV
    try:
        sastre_resp = call_agent(SASTRE_URL, {
            "perfil_base_json":        perfil.get("datos_json", {}),
            "analisis_evaluador_json": raw_analysis,
            "idioma":                  idioma,
            "mercado_geografico":      perfil.get("mercado", "ES"),
        })
        tailored = json.loads(sastre_resp.get("result", "{}"))
        update_application(app_id, {"tailored_content": tailored})
        log_ejecucion({"aplicacion_id": app_id, "etapa": "adaptacion",
                       "modelo_ia": "claude-3-5-haiku", "resultado": "ok",
                       "duracion_ms": int((time.time()-t_start)*1000)})
        print(f"  CV adaptado: {len(tailored.get('keywords_insertadas',[]))} keywords insertadas")
    except Exception as e:
        print(f"  ERROR adaptacion: {e}")
        return

    # 3. GENERAR PDF
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = f"{company.lower().replace(' ','-')}-{datetime.now().strftime('%Y%m')}"
        pdf_path = str(OUTPUT_DIR / f"{slug}.pdf")
        cv_json = tailored.get("cv_adaptado_json", {})
        generate_pdf(cv_json, str(TEMPLATE_ES), pdf_path, idioma)
        update_application(app_id, {"status": "cv_generado", "pdf_url": pdf_path})
        log_ejecucion({"aplicacion_id": app_id, "etapa": "generacion_pdf",
                       "resultado": "ok", "duracion_ms": int((time.time()-t_start)*1000)})
        print(f"  PDF: {pdf_path}")
    except Exception as e:
        print(f"  PDF fallido (CV adaptado guardado de todas formas): {e}")
        update_application(app_id, {"status": "cv_generado"})

    # 4. NOTIFICAR
    notify_make({"company": company, "role": role, "score": fit_score,
                 "grado": grado, "status": "cv_generado", "pdf_url": pdf_path if "pdf_path" in dir() else None})

def main():
    parser = argparse.ArgumentParser(description="Career-Ops Bridge")
    parser.add_argument("--once", action="store_true", help="Procesar una sola vez y salir")
    parser.add_argument("--app-id", help="Procesar una candidatura especifica por ID")
    args = parser.parse_args()

    perfil = get_first_perfil()
    if not perfil:
        print("ERROR: No hay perfil base en Supabase. Ejecuta el onboarding primero.")
        sys.exit(1)
    print(f"Perfil cargado: {perfil.get('nombre')} {perfil.get('apellido')}")

    apps = get_pending_applications()
    if not apps:
        print("No hay candidaturas pendientes.")
        return
    print(f"{len(apps)} candidatura(s) pendiente(s).")

    for app in apps:
        process_application(app, perfil)

    print("\nBridge completado.")

if __name__ == "__main__":
    main()