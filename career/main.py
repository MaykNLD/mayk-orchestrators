"""
Career-Ops Orchestrator — FastAPI | Puerto 8020
Sistema Unificado v2.0

Flujos disponibles:
  POST /career/analizar-perfil  → RRHH-01 analiza el CV → Diseño genera HTML/PDF → Telegram
  POST /career/evaluar          → Evaluador puntúa oferta → (si score>=MIN) Sastre adapta CV en BG
  GET  /career/perfiles         → Lista perfiles de Supabase
  GET  /career/tracker          → Historial de aplicaciones
  GET  /health                  → Estado de todos los agentes
"""
import os, json, sys, urllib.request, threading, re
from pathlib import Path
from html.parser import HTMLParser
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from supabase_client import (
    list_perfiles, get_perfil_by_id, get_first_perfil,
    create_perfil, get_pending_applications, create_application, update_application,
    upload_file_to_storage, get_storage_public_url,
    get_all_applications, get_applications_by_perfil, get_application, log_ejecucion, log_error
)

# URLs de los agentes (inyectadas desde docker-compose / entorno)
EVALUADOR_URL = os.environ.get("AGENTE_HR_EVALUADOR_URL", "http://localhost:8011")
SASTRE_URL    = os.environ.get("AGENTE_HR_SASTRE_URL",    "http://localhost:8012")
RRHH_URL      = os.environ.get("AGENTE_HR_RRHH_URL",      "http://localhost:8013")
DISENO_URL    = os.environ.get("AGENTE_HR_DISENO_URL",     "http://localhost:8014")
MAKE_WEBHOOK  = os.environ.get("MAKE_WEBHOOK_URL", "")
MIN_SCORE     = float(os.environ.get("CAREER_MIN_SCORE", "3.0"))

app = FastAPI(title="Career-Ops Orchestrator", version="2.0.0")


# ── Scraping de URLs de ofertas (stdlib puro, sin dependencias externas) ──
class _TextExtractor(HTMLParser):
    """Extrae texto plano de HTML ignorando scripts, estilos y atributos."""
    def __init__(self):
        super().__init__()
        self._skip = False
        self.chunks = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = True
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = False
    def handle_data(self, data):
        if not self._skip:
            t = data.strip()
            if t:
                self.chunks.append(t)

def _scrape_url(url: str, max_chars: int = 8000) -> str:
    """Descarga la URL y extrae el texto legible. Devuelve string vacío si falla."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Career-Ops/2.0)"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            raw_html = r.read().decode("utf-8", errors="replace")
        parser = _TextExtractor()
        parser.feed(raw_html)
        text = " ".join(parser.chunks)
        # Colapsar espacios múltiples
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception as e:
        print(f"[orchestrator] Scraping fallido para {url}: {e}")
        return ""


# ── Helper: extrae empresa y rol de cualquier dict (eval_resp o raw_analysis) ──
def _get_empresa_rol(source: dict) -> tuple:
    """Lee empresa/rol desde los campos raíz del dict (como ahora devuelve el evaluador).
    Si no existen en raíz, intenta extraerlos de bloque_a con regex.
    Nunca lanza excepciones.
    """
    import re as _re
    empresa = (source.get("empresa") or "").strip()
    rol     = (source.get("rol")     or "").strip()
    if empresa and rol:
        return empresa, rol
    bloque_a = source.get("bloque_a", "")
    if isinstance(bloque_a, dict):
        empresa = empresa or (bloque_a.get("empresa") or bloque_a.get("company") or "").strip()
        rol     = rol     or (bloque_a.get("rol")     or bloque_a.get("role")    or "").strip()
    elif isinstance(bloque_a, str) and len(bloque_a) > 5:
        tab_e = _re.search(r"\|\s*(?:empresa|company)\s*\|\s*([^|\n]+)", bloque_a, _re.IGNORECASE)
        tab_r = _re.search(r"\|\s*(?:rol|role|posici[oó]n|puesto)\s*\|\s*([^|\n]+)", bloque_a, _re.IGNORECASE)
        kv_e  = _re.search(r"(?:empresa|company)[:\s]+([^\n|]+)", bloque_a, _re.IGNORECASE)
        kv_r  = _re.search(r"(?:rol|role|posici[oó]n|puesto)[:\s]+([^\n|]+)", bloque_a, _re.IGNORECASE)
        empresa = empresa or (tab_e.group(1).strip() if tab_e else (kv_e.group(1).strip() if kv_e else ""))
        rol     = rol     or (tab_r.group(1).strip() if tab_r else (kv_r.group(1).strip() if kv_r else ""))
    return empresa or "Desconocida", rol or "No especificado"


# ── Modelos ──────────────────────────────────────────────────────────
class EvaluarRequest(BaseModel):
    url_oferta:   Optional[str] = None
    texto_oferta: Optional[str] = None
    perfil_id:    Optional[str] = None
    idioma:       str = "ES"
    forzar:       bool = False   # Si True, genera CV adaptado aunque el score sea bajo

class AnalizarPerfilRequest(BaseModel):
    perfil_id:   str
    cv_texto:    str            # CV bruto del candidato (texto o markdown)
    foto_modo:   Optional[str] = "sin_foto"   # sin_foto | placeholder | con_foto
    foto_url:    Optional[str] = None
    idioma:      Optional[str] = "ES"


# ── Helpers de comunicación entre agentes ────────────────────────────
def call_agent(url: str, endpoint: str, payload: dict, timeout: int = 240) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{url}{endpoint}", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def notify_make(payload: dict):
    if not MAKE_WEBHOOK:
        return
    
    # ── SANITIZACIÓN PARA TELEGRAM MARKDOWN ──
    # Telegram Markdown falla (Bad Request) si hay '_' o '*' sin cerrar en los valores.
    # Reemplazamos '_' con espacio en 'status' y sanitizamos el mensaje general.
    if "status" in payload and isinstance(payload["status"], str):
        payload["status"] = payload["status"].replace("_", " ")
    
    if "mensaje" in payload and isinstance(payload["mensaje"], str):
        payload["mensaje"] = payload["mensaje"].replace("_", "\\_").replace("*", "")
        
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            MAKE_WEBHOOK, data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"[orchestrator] Error enviando webhook a Make.com: {e}")


def _agent_health(name: str, url: str) -> str:
    try:
        req = urllib.request.Request(f"{url}/health")
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read().decode()).get("status", "unknown")
    except Exception:
        return "offline"


# ── Sastre en background (no bloquea respuesta al usuario) ───────────
def run_sastre_background(app_id: str, perfil: dict, raw_analysis: dict, idioma: str, forzar: bool = False):
    try:
        # Priorizar datos_json (extracón Lossless del RRHH) sobre cv_markdown
        datos_json = perfil.get("datos_json") or {}
        if isinstance(datos_json, str):
            try:
                datos_json = json.loads(datos_json)
            except Exception:
                datos_json = {}
        cv_base_dict = datos_json if datos_json else {"cv_markdown": perfil.get("cv_markdown", "")}
        
        sastre_resp = call_agent(SASTRE_URL, "/execute", {
            "perfil_base_json":        cv_base_dict,
            "analisis_evaluador_json": raw_analysis,
            "idioma":                  idioma,
            "mercado_geografico":      perfil.get("mercado", "ES"),
            "forzar":                  forzar
        }, timeout=200)

        cv_data = {}
        raw_result = sastre_resp.get("result", "{}")
        try:
            parsed = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            # El Sastre envuelve el CV dentro de 'cv_adaptado_json'
            inner = parsed.get("cv_adaptado_json", {})
            # Si el Sastre devolvio datos reales, usarlos; si no, usar el perfil base directamente
            cv_data = inner if inner and isinstance(inner, dict) and len(inner) > 2 else datos_json
        except Exception:
            cv_data = datos_json  # Fallback 100% seguro: usar el CV base guardado por RRHH

        # Enriquecer cv_data con datos personales del perfil (siempre con str para evitar None)
        def _s(v): return str(v) if v is not None else ""
        cv_data["nombre"]    = _s(f"{perfil.get('nombre', '')} {perfil.get('apellido', '')}".strip()) or cv_data.get("nombre", "")
        cv_data["titular"]   = cv_data.get("titular") or _s(perfil.get("titular", ""))
        cv_data["email"]     = _s(perfil.get("email", ""))
        cv_data["telefono"]  = _s(perfil.get("telefono", ""))
        cv_data["ubicacion"] = _s(perfil.get("ubicacion", ""))
        cv_data["linkedin"]  = _s(perfil.get("linkedin", ""))
        cv_data["portfolio"] = _s(perfil.get("github_url", ""))
        # Resumen: garantizar string
        if not cv_data.get("resumen"):
            cv_data["resumen"] = _s(datos_json.get("resumen", ""))

        # Generar PDF directamente desde el CV adaptado del Sastre con Playwright
        pdf_url = None
        try:
            import uuid
            from pathlib import Path as _Path
            from generate_pdf import generate_pdf

            # Seleccionar template segun idioma
            tmpl_name = "cv-template-en.html" if idioma == "EN" else "cv-template.html"
            tmpl_path = str(_Path(__file__).parent / "plantillas" / tmpl_name)

            uid = uuid.uuid4().hex[:8]
            perfil_id = perfil.get("id", "unknown")
            out_dir = _Path("/app/output")
            # Nombre limpio y profesional (Primer nombre + Primer apellido)
            nom_raw = cv_data.get("nombre", "").strip().split()
            ape_raw = perfil.get("apellido", "").strip().split()
            
            first_name = nom_raw[0] if nom_raw else "Candidato"
            first_surname = ape_raw[0] if len(ape_raw) > 0 else (nom_raw[1] if len(nom_raw) > 1 else "")
            
            import re as _re_fn
            rol_p = raw_analysis.get("rol", "Rol")
            # Limpiar el rol para usarlo como nombre de archivo
            rol_p = _re_fn.sub(r'[^\w]', '_', rol_p)   # reemplaza no-alfanum
            rol_p = _re_fn.sub(r'_+', '_', rol_p).strip('_')  # colapsa ___ en _
            
            clean_filename = f"{first_name}_{first_surname}_CV_{rol_p}.pdf"
            
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(out_dir / clean_filename)

            generate_pdf(cv_data, tmpl_path, out_path, idioma)
            
            # Subir a Supabase Storage
            obj_path = clean_filename
            with open(out_path, "rb") as f:
                upload_res = upload_file_to_storage("pdfs", obj_path, f.read(), "application/pdf")
            
            # Zero-Residue Guarantee
            try:
                os.remove(out_path)
            except Exception:
                pass
            
            if upload_res:
                pdf_url = get_storage_public_url("pdfs", obj_path)
                print(f"[orchestrator] PDF subido a Supabase de forma segura: {pdf_url}")
            else:
                print(f"[orchestrator] Error crítico subiendo PDF a Supabase Storage.")
                
        except Exception as e:
            print(f"[orchestrator] Error generando/subiendo PDF: {e}")
            # Ensure cleanup on crash
            if 'out_path' in locals():
                try:
                    os.remove(out_path)
                except Exception:
                    pass

        update_application(app_id, {
            "tailored_content": cv_data,
            "keywords":         sastre_resp.get("keywords_insertadas", []),
            "pdf_url":          pdf_url or "",
            "status":           "cv_generado",
        })

        # Leer empresa y rol desde la BD (fuente de verdad) — no desde raw_analysis que puede ser incompleto
        app_db = get_application(app_id) if app_id else {}
        empresa = app_db.get("company") or _get_empresa_rol(raw_analysis)[0]
        rol     = app_db.get("job_title") or _get_empresa_rol(raw_analysis)[1]
        # Filtrar valores placeholder y aplicar heuristicas de URL si fallan
        if empresa in ("Pendiente", "", "?", "Desconocida", None): 
            empresa = _get_empresa_rol(raw_analysis)[0]
        if rol in ("Oferta", "", "?", "No especificado", None): 
            rol = _get_empresa_rol(raw_analysis)[1]

        # HEURÍSTICA DE URL (ÚLTIMO RECURSO): Si sigue siendo Desconocida/No especificado
        if app_db.get("url"):
            from urllib.parse import urlparse
            import re
            parsed_url = urlparse(app_db["url"])
            heuristica_aplicada = False
            if empresa in ("?", "Desconocida", "Pendiente"):
                empresa = "Desconocida"
                heuristica_aplicada = True
            if rol in ("?", "No especificado", "Oferta"):
                path_parts = parsed_url.path.strip("/").split("/")
                if path_parts:
                    raw_path = path_parts[-1].split("-ID-")[0] # Buscojobs spec
                    raw_path = raw_path.split("?")[0]
                    rol = re.sub(r'[-_]', ' ', raw_path).title()
                    heuristica_aplicada = True
            
            if heuristica_aplicada and app_id:
                update_application(app_id, {
                    "company": empresa,
                    "job_title": rol
                })

        fit_sc = raw_analysis.get("fit_score", 0.0)
        grado  = raw_analysis.get("grado", "?")

        nombre_candidato = f"{perfil.get('nombre','')} {perfil.get('apellido','')}".strip()
        notify_make({
            "candidato": nombre_candidato,
            "company": empresa,
            "role":    rol,
            "score":   fit_sc,
            "grado":   grado,
            "perfil":  nombre_candidato,
            "status":  "cv_generado",
            "pdf_url": pdf_url or "pendiente",
            "mensaje": f"[{nombre_candidato}] CV adaptado generado para {empresa} — {rol}. Score {fit_sc}/5 ({grado}). PDF: {pdf_url or 'pendiente (error al generar)'}" ,
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[orchestrator] ERROR CRITICO en sastre background: {error_msg}")
        if app_id:
            update_application(app_id, {"status": "error_sastre", "notas": error_msg})
            log_error("run_sastre_background", error_msg, app_id=app_id)
        # SIEMPRE notificar a Telegram — nunca dejar al usuario sin respuesta
        notify_make({
            "company": raw_analysis.get("empresa", "Desconocida") if raw_analysis else "Desconocida",
            "role":    raw_analysis.get("rol",     "?")           if raw_analysis else "?",
            "score":   raw_analysis.get("fit_score", 0.0)         if raw_analysis else 0.0,
            "grado":   raw_analysis.get("grado",    "?")          if raw_analysis else "?",
            "status":  "error_critico",
            "mensaje": f"ERROR en generacion de CV adaptado: {error_msg[:300]}",
        })


# ── Background para flujo analizar-perfil ────────────────────────────
def run_diseno_background(perfil_id: str, version_id: Optional[str],
                          foto_modo: str, foto_url: Optional[str],
                          idioma: str, perfil_nombre: str):
    try:
        diseno_resp = call_agent(DISENO_URL, "/generar-cv-html", {
            "perfil_id":    perfil_id,
            "cv_version_id": version_id,
            "foto_modo":    foto_modo,
            "foto_url":     foto_url,
            "idioma":       idioma,
        }, timeout=240)

        # Exito: no se notifica por Telegram, el usuario ya ve el resultado en la CLI
        print(f"[orchestrator] Diseno completado para {perfil_nombre}. PDF: {pdf_url or 'sin PDF'}")
    except Exception as e:
        print(f"[orchestrator] Error en diseno background: {e}")
        notify_make({
            "candidato": perfil_nombre,
            "perfil":    perfil_nombre,
            "status":    "error_diseno",
            "mensaje":   f"[{perfil_nombre}] Error al generar el diseno del CV: {str(e)}",
        })


# ── Endpoints ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    agents = {
        "evaluador": _agent_health("evaluador", EVALUADOR_URL),
        "sastre":    _agent_health("sastre",    SASTRE_URL),
        "rrhh":      _agent_health("rrhh",      RRHH_URL),
        "diseno":    _agent_health("diseno",    DISENO_URL),
    }
    return {
        "status":    "ok",
        "version":   "2.0.0",
        "agents":    agents,
        "min_score": MIN_SCORE,
    }


@app.get("/career/perfiles")
def listar_perfiles():
    perfiles = list_perfiles()
    return {"total": len(perfiles), "perfiles": perfiles}

class PerfilCreateRequest(BaseModel):
    nombre: str = "Nuevo"
    apellido: str = "Candidato"
    email: str = "nuevo@candidato.com"

@app.post("/career/perfiles")
def crear_nuevo_perfil(req_data: PerfilCreateRequest):
    resultado = create_perfil({
        "nombre": req_data.nombre,
        "apellido": req_data.apellido,
        "email": req_data.email
    })
    # create_perfil puede devolver el objeto completo o solo el id
    if isinstance(resultado, dict):
        perfil_id = resultado.get("id", str(resultado))
    else:
        perfil_id = str(resultado)
    return {"status": "ok", "id": perfil_id}


@app.delete("/career/perfiles/{perfil_id}")
def eliminar_perfil(perfil_id: str):
    from scripts.supabase_client import delete_perfil
    ok = delete_perfil(perfil_id)
    if not ok:
        raise HTTPException(404, f"Perfil {perfil_id} no encontrado o no se pudo eliminar")
    return {"status": "ok", "eliminado": perfil_id}


@app.post("/career/analizar-perfil")
def analizar_perfil(req: AnalizarPerfilRequest):
    """
    CAPA 1: Construir perfil del candidato.
    1. agente-hr-rrhh analiza el CV bruto → guarda cv_markdown en Supabase
    2. agente-hr-diseno genera HTML/PDF en background → notifica por Telegram
    """
    perfil = get_perfil_by_id(req.perfil_id)
    if not perfil:
        raise HTTPException(404, f"Perfil {req.perfil_id} no encontrado")

    nombre = f"{perfil.get('nombre', '')} {perfil.get('apellido', '')}".strip()

    # Paso 1: Dependiendo de si hay cv_texto, analizamos con RRHH o recuperamos el CV existente
    version_id = None
    cv_markdown = perfil.get("cv_markdown") or ""
    
    if req.cv_texto and req.cv_texto.strip():
        try:
            rrhh_resp = call_agent(RRHH_URL, "/analizar-cv", {
                "perfil_id": req.perfil_id,
                "cv_texto":  req.cv_texto,
                "idioma":    req.idioma,
            }, timeout=240)
            version_id = rrhh_resp.get("version_id")
            cv_markdown = rrhh_resp.get("cv_mejorado", "")
        except Exception as e:
            notify_make({
                "perfil": nombre,
                "status": "error_ia",
                "mensaje": f"Ups, el agente HR-RRHH (OpenRouter) ha fallado al analizar tu CV: {str(e)}"
            })
            raise HTTPException(500, f"Error en agente-hr-rrhh: {e}")
        
        nivel = rrhh_resp.get("nivel_detectado", "")
        mens_estado = "CV nuevo analizado por RRHH-01. Diseño y PDF generándose."
    else:
        if not cv_markdown.strip():
            raise HTTPException(400, "No has proporcionado un CV y tampoco existe uno previo en tu perfil.")
        # Usamos el CV previamente guardado.
        nivel = perfil.get("nivel", "")
        mens_estado = "Usando CV existente en base de datos. Diseño y PDF generándose directamente."

    # Paso 2: Diseño en background (no bloquea)
    t = threading.Thread(
        target=run_diseno_background,
        args=(req.perfil_id, version_id, req.foto_modo, req.foto_url, req.idioma, nombre),
        daemon=True
    )
    t.start()

    return {
        "perfil_id":          req.perfil_id,
        "perfil":             nombre,
        "nivel_detectado":    nivel,
        "estado":             "cv_analizando_diseno",
        "mensaje":            f"{mens_estado} Recibirás notificación por Telegram.",
    }


@app.post("/career/evaluar")
def evaluar(req: EvaluarRequest):
    """
    CAPA 2: Evaluar una oferta de trabajo.
    1. Evaluador puntúa el fit candidato-oferta (A-F)
    2. Si score >= MIN_SCORE → Sastre adapta el CV en background
    """
    if not req.url_oferta and not req.texto_oferta:
        raise HTTPException(400, "Proporciona url_oferta o texto_oferta")

    # Resolver perfil
    perfil = get_perfil_by_id(req.perfil_id) if req.perfil_id else get_first_perfil()
    if not perfil:
        raise HTTPException(404, "Perfil no encontrado en Supabase.")

    # BUG 2 GUARD: Bloquear evaluacion si el candidato no tiene CV cargado
    cv_markdown = perfil.get("cv_markdown") or ""
    datos_json = perfil.get("datos_json") or {}
    if not cv_markdown.strip() and not datos_json:
        nombre_c = f"{perfil.get('nombre','')} {perfil.get('apellido','')}".strip()
        raise HTTPException(400, f"El candidato '{nombre_c}' no tiene CV cargado. Ve a la Opcion 1 (Subir CV) primero.")

    # Usar cv_markdown si existe, fallback a datos_json (retrocompatibilidad)
    cv_base_dict = {"cv_markdown": cv_markdown} if cv_markdown else datos_json

    empresa_inicial, rol_inicial = _get_empresa_rol({})
    app_record = create_application({
        "perfil_id": perfil["id"],
        "job_title": "Pendiente de evaluacion",
        "company":   "Pendiente",
        "url":       req.url_oferta or "",
        "status":    "evaluando",
    })
    app_id = app_record.get("id")

    # ── Scraping previo: si hay URL y no hay texto_oferta, leer la web ──
    texto_oferta = req.texto_oferta or ""
    if req.url_oferta and not texto_oferta.strip():
        print(f"[orchestrator] Scraping URL: {req.url_oferta}")
        texto_oferta = _scrape_url(req.url_oferta)
        if texto_oferta:
            print(f"[orchestrator] Texto extraído: {len(texto_oferta)} caracteres")
        else:
            print(f"[orchestrator] Scraping vacío, se pasa la URL directamente al LLM")

    # Llamar al evaluador
    try:
        eval_resp = call_agent(EVALUADOR_URL, "/execute", {
            "url_oferta":       req.url_oferta or "",
            "texto_oferta":     texto_oferta,
            "perfil_base_json": cv_base_dict,
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
        # Propagar empresa/rol desde el evaluador directamente al raw_analysis
        # (el evaluador ya los extrae como campos raíz en su response)
        if eval_resp.get("empresa") and eval_resp["empresa"] != "Desconocida":
            raw_analysis["empresa"] = eval_resp["empresa"]
        if eval_resp.get("rol") and eval_resp["rol"] != "No especificado":
            raw_analysis["rol"] = eval_resp["rol"]

        if app_id:
            # Guardar empresa y rol en la BD tan pronto el evaluador los extrae
            empresa_eval, rol_eval = _get_empresa_rol(raw_analysis)
            update_application(app_id, {
                "fit_score":    fit_score,
                "grado":        grado,
                "raw_analysis": raw_analysis,
                "keywords":     raw_analysis.get("keywords_clave", []),
                "status":       "en_proceso" if fit_score >= MIN_SCORE else "descartado",
                "company":      empresa_eval if empresa_eval not in ("?", "Desconocida", "") else "Pendiente",
                "job_title":    rol_eval    if rol_eval    not in ("?", "No especificado", "") else "Oferta",
            })
    except Exception as e:
        if app_id:
            update_application(app_id, {"status": "error_evaluador", "notas": str(e)})
            log_error("evaluar_endpoint", str(e), app_id=app_id)
        notify_make({
            "perfil": f"{perfil.get('nombre', '')} {perfil.get('apellido', '')}",
            "status": "error_ia",
            "company": "?",
            "role": "?",
            "score": 0.0,
            "grado": "F",
            "mensaje": f"El Evaluador IA colapso al revisar la oferta: {str(e)}"
        })
        raise HTTPException(500, f"Error en agente evaluador: {e}")

    result = {
        "aplicacion_id": app_id,
        "perfil":        f"{perfil['nombre']} {perfil['apellido']}",
        "fit_score":     fit_score,
        "grado":         grado,
        "recomendacion": recomendacion,
        "bloques":       raw_analysis,
    }

    # Lanzar Sastre si score >= MIN_SCORE  ó  si el usuario forzó el envío
    empresa_r, rol_r = _get_empresa_rol(raw_analysis)
    if fit_score >= MIN_SCORE or req.forzar:
        t = threading.Thread(
            target=run_sastre_background,
            args=(app_id, perfil, raw_analysis, req.idioma, req.forzar),
            daemon=True
        )
        t.start()
        if req.forzar and fit_score < MIN_SCORE:
            result["mensaje"] = f"Score {fit_score}/5 ({grado}) — ENVIO FORZADO. CV de {empresa_r} — {rol_r} adaptándose en background."
        else:
            result["mensaje"] = f"Score {fit_score}/5 ({grado}). CV adaptándose en background. Notificación para {empresa_r} — {rol_r} por Telegram."
        result["estado"]  = "en_proceso"
    else:
        candidato_nombre = result["perfil"]
        notify_make({
            "candidato": candidato_nombre,
            "company":   empresa_r,
            "role":      rol_r,
            "score":     fit_score,
            "grado":     grado,
            "perfil":    candidato_nombre,
            "status":    "descartado",
            "mensaje":   f"[{candidato_nombre}] Oferta de {empresa_r} — {rol_r} descartada por score bajo ({fit_score}/{MIN_SCORE})."
        })
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). Oferta {empresa_r} — {rol_r} descartada."
        result["estado"]  = "descartado"


    return result


@app.get("/career/tracker")
def tracker(perfil_id: Optional[str] = None):
    if perfil_id:
        apps = get_applications_by_perfil(perfil_id)
    else:
        apps = get_all_applications()
    return {"total": len(apps), "aplicaciones": apps}