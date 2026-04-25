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
import os, json, sys, urllib.request, threading, re, time
from pathlib import Path
from html.parser import HTMLParser
from fastapi import UploadFile, File,  FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from supabase_client import (
    list_perfiles, get_perfil_by_id, get_first_perfil,
    create_perfil, get_pending_applications, create_application, update_application,
    upload_file_to_storage, get_storage_signed_url, delete_storage_file,
    get_all_applications, get_applications_by_perfil, get_application_by_url, get_application, log_ejecucion, log_error
)

# URLs de los agentes (inyectadas desde docker-compose / entorno)
EVALUADOR_URL = os.environ.get("AGENTE_HR_EVALUADOR_URL", "http://localhost:8011")
SASTRE_URL    = os.environ.get("AGENTE_HR_SASTRE_URL",    "http://localhost:8012")
RRHH_URL      = os.environ.get("AGENTE_HR_RRHH_URL",      "http://localhost:8013")
DISENO_URL    = os.environ.get("AGENTE_HR_DISENO_URL",     "http://localhost:8014")
MAKE_WEBHOOK  = os.environ.get("MAKE_WEBHOOK_URL", "")
MIN_SCORE     = float(os.environ.get("CAREER_MIN_SCORE", "3.0"))

app = FastAPI(title="Career-Ops Orchestrator", version="2.0.0")

# ── Worker imports ────────────────────────────────────────────────────
from scripts.supabase_client import (
    get_evaluando_applications, update_heartbeat,
    get_pending_cv_extractions, update_perfil,
    get_todays_processed_count
)

MAX_APPS_PER_DAY = int(os.environ.get("MAX_APPS_PER_DAY", "10"))  # limite diario por usuario

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


CV_EXTRACTION_PROMPT = """
Eres un experto en recursos humanos. Extrae TODA la informacion del siguiente CV y devuelve SOLO un JSON valido, sin texto extra, sin markdown, sin explicaciones.

Estructura EXACTA que debes devolver:
{
  "resumen": "Resumen profesional de 2-4 frases",
  "habilidades": ["habilidad1", "habilidad2", ...],
  "experiencia": [
    {
      "empresa": "Nombre empresa",
      "puesto": "Titulo del puesto",
      "fecha_inicio": "MM/YYYY o YYYY",
      "fecha_fin": "MM/YYYY o Presente",
      "descripcion": "Descripcion de responsabilidades y logros"
    }
  ],
  "educacion": [
    {
      "institucion": "Nombre universidad/instituto",
      "titulo": "Titulo obtenido",
      "fecha": "YYYY o YYYY-YYYY"
    }
  ],
  "certificaciones": [
    {
      "nombre": "Nombre certificacion",
      "emisor": "Organizacion emisora",
      "fecha": "YYYY"
    }
  ],
  "idiomas": [
    {
      "idioma": "Nombre idioma",
      "nivel": "Nativo|Avanzado|Intermedio|Basico"
    }
  ]
}

Si no hay datos para un campo, usa lista vacia [] o string vacio "". NO inventes datos.

CV A EXTRAER:
{cv_texto}
"""

def _call_openrouter(prompt: str, model: str = "anthropic/claude-3-haiku") -> str:
    """Llama directamente a OpenRouter con el modelo indicado. Devuelve el texto de la respuesta."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY no configurada")
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 3000,
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://career-ops.vercel.app",
            "X-Title": "Career-Ops",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        resp = json.loads(r.read().decode())
    return resp["choices"][0]["message"]["content"]

def _extract_cv_from_pdf(perfil: dict) -> dict:
    """
    Extrae datos estructurados del CV usando Claude Haiku directamente via OpenRouter.
    Rellena completamente datos_json: resumen, habilidades, experiencia, educacion,
    certificaciones e idiomas.
    """
    perfil_id = perfil.get("id", "?")
    print(f"[cv-extractor] Iniciando extraccion para perfil {perfil_id}")

    # 1. Obtener el texto del CV
    cv_texto = (perfil.get("cv_markdown") or "").strip()
    datos_json = perfil.get("datos_json") or {}
    if isinstance(datos_json, str):
        try: datos_json = json.loads(datos_json)
        except: datos_json = {}

    # 2. Si no hay cv_markdown suficiente, intentar descargar el PDF
    pdf_url = datos_json.get("cv_pdf_url", "")
    if pdf_url and len(cv_texto) < 500:
        try:
            req = urllib.request.Request(pdf_url, headers={"User-Agent": "Career-Ops/2.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                pdf_bytes = r.read()
            try:
                from io import BytesIO
                from pdfminer.high_level import extract_text as pdf_extract
                cv_texto = pdf_extract(BytesIO(pdf_bytes))[:8000]
                print(f"[cv-extractor] PDF descargado: {len(cv_texto)} chars")
            except ImportError:
                print("[cv-extractor] pdfminer no disponible")
        except Exception as e:
            print(f"[cv-extractor] No se pudo descargar el PDF: {e}")

    if len(cv_texto) < 50:
        print(f"[cv-extractor] Sin texto suficiente. Abortando.")
        update_perfil(perfil_id, {"cv_extraction_pending": False})
        return {}

    # 3. Llamar a Claude Haiku para extraccion estructurada completa
    prompt = CV_EXTRACTION_PROMPT.replace("{cv_texto}", cv_texto[:7000])
    raw_json = ""
    # Intentar primero con Claude Haiku, fallback a Gemini Flash
    for model in ["anthropic/claude-3-haiku", "google/gemini-2.0-flash-001"]:
        try:
            raw_json = _call_openrouter(prompt, model=model)
            print(f"[cv-extractor] LLM ({model}) respondio: {len(raw_json)} chars")
            break
        except Exception as e:
            print(f"[cv-extractor] Fallo con {model}: {e}")

    if not raw_json:
        print("[cv-extractor] Todos los modelos fallaron. Abortando.")
        update_perfil(perfil_id, {"cv_extraction_pending": False})
        return {}

    # 4. Parsear el JSON de la respuesta (limpiar markdown si el LLM lo inyecto)
    clean = raw_json.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```[a-z]*\n?", "", clean)
        clean = re.sub(r"```$", "", clean).strip()
    try:
        extracted = json.loads(clean)
    except Exception as e:
        print(f"[cv-extractor] No se pudo parsear JSON: {e}\nRespuesta: {clean[:300]}")
        update_perfil(perfil_id, {"cv_extraction_pending": False})
        return {}

    # 5. Construir datos_json preservando foto y pdf ya subidos
    nuevo_datos = {
        "foto_url":        datos_json.get("foto_url", ""),
        "cv_pdf_url":      datos_json.get("cv_pdf_url", ""),
        "telefono":        datos_json.get("telefono", ""),
        "resumen":         extracted.get("resumen", ""),
        "habilidades":     extracted.get("habilidades", []),
        "experiencia":     extracted.get("experiencia", []),
        "educacion":       extracted.get("educacion", []),
        "certificaciones": extracted.get("certificaciones", []),
        "idiomas":         extracted.get("idiomas", []),
    }

    # 6. Guardar en Supabase y resetear flag
    update_perfil(perfil_id, {
        "datos_json":            nuevo_datos,
        "cv_extraction_pending": False,
    })
    print(f"[cv-extractor] Extraccion completada: {len(nuevo_datos['experiencia'])} exp, {len(nuevo_datos['habilidades'])} skills")
    return nuevo_datos


def worker_polling_loop():
    print("[orchestrator-worker] Inicializando Worker Polling Loop...")
    heartbeat_counter = 0
    while True:
        try:
            # Heartbeat cada 30 segundos (6 ciclos de 5s)
            heartbeat_counter += 1
            if heartbeat_counter >= 6:
                update_heartbeat()
                heartbeat_counter = 0

            # ── Job tipo 1: Candidaturas a evaluar ──
            apps = get_evaluando_applications(limit=3)
            for app_db in apps:
                app_id    = app_db.get("id")
                perfil_id = app_db.get("perfil_id")
                if not app_id: continue

                # Rate limiting diario por usuario
                daily_count = get_todays_processed_count(perfil_id) if perfil_id else 0
                if daily_count >= MAX_APPS_PER_DAY:
                    print(f"[orchestrator-worker] Limite diario alcanzado para perfil {perfil_id} ({daily_count}/{MAX_APPS_PER_DAY}). Saltando.")
                    update_application(app_id, {"status": "pendiente", "notas": f"Limite diario de {MAX_APPS_PER_DAY} solicitudes alcanzado. Reintentara manana."})
                    continue

                print(f"\n[orchestrator-worker] Candidatura: {app_id} [{daily_count+1}/{MAX_APPS_PER_DAY} hoy]")
                update_application(app_id, {"status": "procesando_ia"})
                try:
                    req = EvaluarRequest(
                        url_oferta=app_db.get("url", ""),
                        perfil_id=perfil_id,
                        app_id=app_id,
                        forzar=True
                    )
                    evaluar(req)
                    print(f"[orchestrator-worker] Candidatura completada: {app_id}")
                except Exception as e:
                    print(f"[orchestrator-worker] Error candidatura {app_id}: {e}")
                    update_application(app_id, {"status": "error_ia", "notas": str(e)})

            # ── Job tipo 2: Extraccion de CV desde PDF ──
            pending_extractions = get_pending_cv_extractions(limit=2)
            for perfil_row in pending_extractions:
                try:
                    _extract_cv_from_pdf(perfil_row)
                except Exception as e:
                    print(f"[cv-extractor] ❌ Error extrayendo CV para {perfil_row.get('id')}: {e}")
                    update_perfil(perfil_row.get('id'), {"cv_extraction_pending": False})

            # ── Job tipo 3: Generacion de CV principal para descarga ──
            # Arquitectura:
            #   1. El orquestador construye/recupera el cv_markdown del perfil
            #   2. Llama al agente-hr-diseno que genera SOLO el HTML (sin WeasyPrint)
            #   3. El orquestador convierte el HTML a PDF con Playwright (Chromium)
            #   4. El orquestador sube el PDF a Supabase Storage y obtiene signed_url
            from scripts.supabase_client import (
                get_pending_cv_download_requests,
                update_cv_download_request,
                update_perfil as _upd_perfil,
            )
            pending_downloads = get_pending_cv_download_requests(limit=2)
            for dl_job in pending_downloads:
                job_id    = dl_job.get("id")
                perfil_id = dl_job.get("perfil_id")
                if not job_id or not perfil_id:
                    continue

                # Leer opciones con fallback seguro (Supabase puede devolver None)
                con_foto = dl_job.get("con_foto")
                if con_foto is None:
                    con_foto = True
                idioma = (dl_job.get("idioma") or "ES").strip() or "ES"

                print(f"[orchestrator-worker] CV download request: {job_id} perfil={perfil_id}")
                update_cv_download_request(job_id, {"status": "processing"})

                try:
                    perfil_dl = get_perfil_by_id(perfil_id)
                    if not perfil_dl:
                        raise ValueError(f"Perfil {perfil_id} no encontrado en la BD")

                    # ── Helper: extraer campo como string, nunca None ──
                    def _s(v):
                        return str(v).strip() if v is not None else ""

                    # ── Helper: extraer campo como lista, nunca None ──
                    def _l(v):
                        if isinstance(v, list): return v
                        if v is None: return []
                        try: return list(v)
                        except: return []

                    # ── Parsear datos_json de forma 100% segura ──
                    raw_datos = perfil_dl.get("datos_json")
                    if isinstance(raw_datos, str):
                        try:    datos_dl = json.loads(raw_datos)
                        except: datos_dl = {}
                    elif isinstance(raw_datos, dict):
                        datos_dl = raw_datos
                    else:
                        datos_dl = {}

                    # ── Construir/recuperar cv_markdown ──
                    # El agente-hr-diseno lee cv_markdown del perfil en Supabase.
                    # Si es None o vacio (perfil importado via PDF), lo construimos
                    # desde datos_json y lo persistimos para que el agente lo encuentre.
                    cv_markdown = _s(perfil_dl.get("cv_markdown"))

                    if not cv_markdown:
                        if not datos_dl:
                            raise ValueError(
                                "El perfil no tiene cv_markdown ni datos_json. "
                                "Importa tu CV en PDF primero desde 'Mi CV'."
                            )
                        nombre_dl = (
                            _s(perfil_dl.get("nombre")) + " " +
                            _s(perfil_dl.get("apellido"))
                        ).strip()

                        habilidades_str = ", ".join(
                            str(h) for h in _l(datos_dl.get("habilidades")) if h
                        )

                        def _json_safe(v):
                            return json.dumps(_l(v), ensure_ascii=False, indent=2)

                        cv_markdown = (
                            f"Candidato: {nombre_dl}\n"
                            f"Email: {_s(perfil_dl.get('email'))}\n"
                            f"Telefono: {_s(datos_dl.get('telefono'))}\n"
                            f"Resumen: {_s(datos_dl.get('resumen'))}\n"
                            f"Habilidades: {habilidades_str}\n"
                            f"Experiencia:\n{_json_safe(datos_dl.get('experiencia'))}\n"
                            f"Educacion:\n{_json_safe(datos_dl.get('educacion'))}\n"
                            f"Certificaciones:\n{_json_safe(datos_dl.get('certificaciones'))}\n"
                            f"Idiomas:\n{_json_safe(datos_dl.get('idiomas'))}"
                        )
                        try:
                            _upd_perfil(perfil_id, {"cv_markdown": cv_markdown})
                            print(f"[orchestrator-worker] cv_markdown construido y persistido para {perfil_id}")
                        except Exception as e_save:
                            print(f"[orchestrator-worker] Advertencia: no se pudo persistir cv_markdown: {e_save}")

                    # ── Preparar foto ──
                    foto_modo = "con_foto" if con_foto else "sin_foto"
                    foto_url  = _s(datos_dl.get("foto_url")) if con_foto else None
                    if con_foto and not foto_url:
                        foto_modo = "sin_foto"
                        foto_url  = None
                        print(f"[orchestrator-worker] con_foto=True pero foto_url vacia. Usando sin_foto.")

                    # ── Paso 1: Agente genera el HTML ──
                    print(f"[orchestrator-worker] Llamando agente-hr-diseno para HTML...")
                    diseno_resp = call_agent(DISENO_URL, "/generar-cv-html", {
                        "perfil_id": perfil_id,
                        "foto_modo": foto_modo,
                        "foto_url":  foto_url or None,
                        "idioma":    idioma,
                    }, timeout=180)

                    html_cv = _s(diseno_resp.get("html_cv"))
                    if not html_cv:
                        raise ValueError(
                            "El agente de diseno devolvio html_cv vacio. "
                            f"Respuesta: {str(diseno_resp)[:200]}"
                        )
                    print(f"[orchestrator-worker] HTML recibido OK ({len(html_cv)} chars)")

                    # ── Paso 2: Playwright convierte HTML → PDF ──
                    # Usamos 'load' en vez de 'networkidle' para evitar timeout
                    # si el HTML carga Google Fonts u otros recursos externos.
                    print(f"[orchestrator-worker] Generando PDF con Playwright...")
                    pdf_bytes = None
                    try:
                        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
                        with sync_playwright() as pw:
                            browser = pw.chromium.launch(
                                args=["--no-sandbox", "--disable-dev-shm-usage",
                                      "--disable-gpu", "--single-process"]
                            )
                            try:
                                page = browser.new_page()
                                # 'load' espera el evento load del DOM (no networkidle que puede colgar)
                                page.set_content(html_cv, wait_until="load", timeout=30_000)
                                pdf_bytes = page.pdf(
                                    format="A4",
                                    print_background=True,
                                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                                )
                            finally:
                                browser.close()
                    except PWTimeout:
                        raise ValueError("Playwright: timeout esperando que el HTML cargara (>30s). Revisa recursos externos en el HTML.")
                    except Exception as e_pw:
                        raise ValueError(f"Playwright fallo al generar PDF: {e_pw}")

                    if not pdf_bytes or len(pdf_bytes) < 1000:
                        raise ValueError(
                            f"PDF generado invalido ({len(pdf_bytes) if pdf_bytes else 0} bytes). "
                            "El HTML puede estar vacio o mal formado."
                        )
                    print(f"[orchestrator-worker] PDF generado OK ({len(pdf_bytes)} bytes)")

                    # ── Paso 3: Guardar PDF como data URL en Supabase DB ──
                    # Evitamos Supabase Storage (auth/JWT issues) guardando el PDF
                    # codificado en base64 directamente en la BD.
                    # El frontend lo convierte a Blob para la descarga.
                    import base64 as _b64
                    data_url = "data:application/pdf;base64," + _b64.b64encode(pdf_bytes).decode()
                    print(f"[orchestrator-worker] PDF codificado en base64 ({len(data_url)} chars)")

                    # ── Paso 4: Marcar job como completado ──
                    update_cv_download_request(job_id, {
                        "status":     "done",
                        "signed_url": data_url,
                    })
                    print(f"[orchestrator-worker] ✅ CV download completado: {job_id}")

                except Exception as e:
                    err = str(e)
                    print(f"[orchestrator-worker] ❌ ERROR CV download {job_id}: {err}")
                    try:
                        update_cv_download_request(job_id, {
                            "status":    "error",
                            "error_msg": err[:500],
                        })
                    except Exception as e_upd:
                        print(f"[orchestrator-worker] No se pudo marcar job como error: {e_upd}")
                    log_error("worker_cv_download", err,
                              extra={"job_id": job_id, "perfil_id": perfil_id})

        except Exception as e:
            print(f"[orchestrator-worker] Error en el loop principal: {e}")
        time.sleep(5)


@app.on_event("startup")
def start_background_worker():
    t = threading.Thread(target=worker_polling_loop, daemon=True)
    t.start()
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
    except urllib.error.HTTPError as e:
        print(f"[orchestrator] Scraping bloqueado o fallido para {url}: HTTP {e.code}")
        if e.code in [403, 405, 401]:
            raise ValueError(f"Acceso denegado (HTTP {e.code}). La web bloquea bots.")
        return ""
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
    app_id:       Optional[str] = None
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
    
    # ── SANITIZACIÓN PARA TELEGRAM MARKDOWN V2 ──
    # Telegram MarkdownV2 falla severamente (HTTP 400 Bad Request) si detecta caracteres
    # especiales sin escapar en CUALQUIER campo de texto (. - ! etc).
    import re
    escape_chars = r'([_*\[\]()~`>#+\-=|{}.!])'
    
    for key, val in payload.items():
        if isinstance(val, str) and key != "pdf_url":
            # Reemplazar '_' por espacio en el status para que sea legible
            if key == "status":
                val = val.replace("_", " ")
            payload[key] = re.sub(escape_chars, r'\\\1', val)
            
        
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
            from scripts.generate_pdf import generate_pdf

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
                upload_res = upload_file_to_storage("cvs-pdf", obj_path, f.read(), "application/pdf")
            
            # Zero-Residue Guarantee
            try:
                os.remove(out_path)
            except Exception:
                pass
            
            if upload_res:
                pdf_url = get_storage_signed_url("cvs-pdf", obj_path, 3600)
                print(f"[orchestrator] PDF subido a Supabase Storage (bucket: cvs-pdf): {pdf_url}")

                # Destructor programado: Eliminar archivo de Supabase Storage en 3600s (1 hora)
                def kill_residue():
                    import time
                    time.sleep(3600)
                    delete_storage_file("pdfs", obj_path)
                    print(f"[orchestrator] Residuo eliminado del Storage: {obj_path}")

                t_clean = threading.Thread(target=kill_residue, daemon=True)
                t_clean.start()

            else:
                print(f"[orchestrator] Error crítico subiendo PDF temporal a Supabase Storage.")
                
        except Exception as e:
            import traceback
            print(f"[orchestrator] Error fatal generando/subiendo PDF:\n{traceback.format_exc()}")
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

        nombre_candidato = f"{perfil.get('nombre','')} {perfil.get('apellido','')}".strip()
        empresa = get_application(app_id).get("company", "") if app_id else ""
        rol     = get_application(app_id).get("job_title", "") if app_id else ""
        fit_sc  = raw_analysis.get("fit_score", 0.0)
        grado   = raw_analysis.get("grado", "?")
        print(f"[orchestrator] CV generado para {nombre_candidato} — {empresa} ({rol}). Score {fit_sc}/5 ({grado}).")

    except Exception as e:
        error_msg = str(e)
        print(f"[orchestrator] ERROR CRITICO en sastre background: {error_msg}")
        if app_id:
            update_application(app_id, {"status": "error_sastre", "notas": error_msg})
        # log_error persiste en Supabase Y notifica a Make.com (sin duplicados)
        log_error("run_sastre_background", error_msg, app_id=app_id,
                  extra={"empresa": raw_analysis.get("empresa") if raw_analysis else "?",
                         "rol":     raw_analysis.get("rol")     if raw_analysis else "?"})


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

        # Exito: no se notifica (Make.com solo recibe errores)
        print(f"[orchestrator] Diseno completado para {perfil_nombre}.")
    except Exception as e:
        err_msg = str(e)
        print(f"[orchestrator] Error en diseno background: {err_msg}")
        log_error("run_diseno_background", err_msg,
                  extra={"perfil_nombre": perfil_nombre})


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


@app.delete("/career/tracker/{app_id}")
def eliminar_aplicacion(app_id: str):
    from scripts.supabase_client import delete_application
    ok = delete_application(app_id)
    if not ok:
        raise HTTPException(404, f"Aplicacion {app_id} no encontrada o no se pudo eliminar")
    return {"status": "ok", "eliminado": app_id}


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

            # ── Fase 3: Guardar datos_json estructurado para que el PDF nunca falle ──
            try:
                datos_json_struct = {
                    "nombre":    perfil.get("nombre", ""),
                    "apellido":  perfil.get("apellido", ""),
                    "email":     perfil.get("email", ""),
                    "telefono":  perfil.get("telefono", ""),
                    "ubicacion": perfil.get("ubicacion", ""),
                    "linkedin":  perfil.get("linkedin", ""),
                    "titular":   rrhh_resp.get("objetivo_profesional", ""),
                    "resumen":   rrhh_resp.get("resumen_ejecutivo", ""),
                    "skills": {
                        "principales": rrhh_resp.get("skills_clave", [])[:6],
                        "secundarias":  rrhh_resp.get("skills_clave", [])[6:],
                    },
                    "experiencia": [],  # El Sastre lo rellena al adaptar el CV
                    "educacion":   [],  # El Sastre lo rellena al adaptar el CV
                    "cv_markdown_base": cv_markdown,
                }
                from scripts.supabase_client import update_perfil
                update_perfil(req.perfil_id, {"datos_json": json.dumps(datos_json_struct, ensure_ascii=False)})
                print(f"[orchestrator] datos_json estructurado guardado para perfil {req.perfil_id}")
            except Exception as e_json:
                print(f"[orchestrator] Advertencia: no se pudo guardar datos_json: {e_json}")
        except Exception as e:
            log_error("analizar_perfil_rrhh", str(e),
                      extra={"perfil_id": req.perfil_id, "perfil": nombre})
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

    # Obligar a enviar perfil_id para evitar cruce de datos
    if not req.perfil_id:
        raise HTTPException(400, "perfil_id es obligatorio. No se puede evaluar sin un perfil de candidato específico.")
        
    perfil = get_perfil_by_id(req.perfil_id)
    if not perfil:
        raise HTTPException(404, "Perfil no encontrado en Supabase.")

    # BUG 2 GUARD: Bloquear evaluacion si el candidato no tiene CV cargado
    cv_markdown = perfil.get("cv_markdown") or ""
    datos_json_raw = perfil.get("datos_json") or {}
    if isinstance(datos_json_raw, str):
        try: datos_json_raw = json.loads(datos_json_raw)
        except: datos_json_raw = {}
    tiene_cv = cv_markdown.strip() or datos_json_raw.get("cv_pdf_url") or datos_json_raw.get("resumen")
    if not tiene_cv:
        nombre_c = f"{perfil.get('nombre','')} {perfil.get('apellido','')}".strip()
        raise HTTPException(400, f"El candidato '{nombre_c}' no tiene CV cargado. Sube tu CV en Mi CV primero.")

    # Usar cv_markdown si existe, fallback a datos_json formateado
    if cv_markdown.strip():
        cv_base_dict = {"cv_markdown": cv_markdown}
    else:
        # Construir texto del CV desde datos_json para el evaluador
        dj = datos_json_raw
        cv_construido = f"""Candidato: {perfil.get('nombre','')} {perfil.get('apellido','')}
Resumen: {dj.get('resumen','')}
Habilidades: {', '.join(dj.get('habilidades',[]))}
Experiencia: {json.dumps(dj.get('experiencia',[]), ensure_ascii=False)}
Educacion: {json.dumps(dj.get('educacion',[]), ensure_ascii=False)}"""
        cv_base_dict = {"cv_markdown": cv_construido}

    empresa_inicial, rol_inicial = _get_empresa_rol({})
    
    # ── Deduplicacion por URL o ID ──
    app_id = req.app_id
    if not app_id and req.url_oferta:
        ext_app = get_application_by_url(perfil["id"], req.url_oferta)
        if ext_app:
            app_id = ext_app["id"]

    # ── Scraping previo: si hay URL y no hay texto_oferta, leer la web ──
    texto_oferta = req.texto_oferta or ""
    # Intentar obtener el texto de la candidatura existente (notas del usuario) como fallback
    app_notas = ""
    if app_id:
        app_record_pre = get_application(app_id)
        if app_record_pre:
            app_notas = app_record_pre.get("notas") or ""
    if req.url_oferta and not texto_oferta.strip():
        print(f"[orchestrator] Scraping URL: {req.url_oferta}")
        try:
            texto_oferta = _scrape_url(req.url_oferta)
            if texto_oferta and len(texto_oferta) >= 300:
                print(f"[orchestrator] Texto extraido: {len(texto_oferta)} caracteres")
            elif texto_oferta and len(texto_oferta) < 300:
                print(f"[orchestrator] AVISO: texto muy corto ({len(texto_oferta)} chars) — posible pagina JS-renderizada")
                raise ValueError(f"Texto insuficiente ({len(texto_oferta)} chars). La pagina puede requerir JavaScript.")
            else:
                raise ValueError("No se pudo extraer texto util de la pagina.")
        except Exception as e:
            print(f"[orchestrator] Scraping fallo: {e}")
            if app_notas.strip():
                texto_oferta = app_notas
                print(f"[orchestrator] Usando notas como fallback: {len(texto_oferta)} chars")
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"SCRAPING_FAILED: {str(e)} Anade el texto de la oferta en Notas."
                )

    # Llamar al evaluador ANTES de guardar en base de datos para no generar basura
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

        # Solo ahora (si el evaluador no falló) creamos o actualizamos la aplicación en la BD
        empresa_eval, rol_eval = _get_empresa_rol(raw_analysis)
        
        if not app_id:
            app_record = create_application({
                "perfil_id": perfil["id"],
                "job_title": rol_eval if rol_eval not in ("?", "No especificado", "") else "Oferta",
                "company":   empresa_eval if empresa_eval not in ("?", "Desconocida", "") else "Pendiente",
                "url":       req.url_oferta or "",
                "status":    "en_proceso" if fit_score >= MIN_SCORE else "descartado",
            })
            app_id = app_record.get("id")

        # Actualizar la candidatura: NUNCA sobreescribir company/job_title del usuario
        if app_id:
            update_application(app_id, {
                "fit_score":    fit_score,
                "grado":        grado,
                "raw_analysis": raw_analysis,
                "keywords":     raw_analysis.get("keywords_clave", []),
                "status":       "en_proceso" if fit_score >= MIN_SCORE else "descartado",
                # company y job_title NO se tocan: son datos que puso el usuario
            })
    except Exception as e:
        if app_id:
            update_application(app_id, {"status": "error_evaluador", "notas": str(e)})
        # log_error persiste en Supabase Y notifica a Make.com
        log_error("evaluar_endpoint", str(e), app_id=app_id)
        raise HTTPException(500, f"Error en agente evaluador: {e}")

    # Evaluar la empresa y rol antes de armar result
    empresa_r, rol_r = _get_empresa_rol(raw_analysis)

    result = {
        "aplicacion_id": app_id,
        "perfil":        f"{perfil['nombre']} {perfil['apellido']}",
        "fit_score":     fit_score,
        "grado":         grado,
        "recomendacion": recomendacion,
        "empresa":       empresa_r,
        "rol":           rol_r,
        "bloques":       raw_analysis,
    }

    # Lanzar Sastre si score >= MIN_SCORE o si el usuario forzó Y la evaluación produjo algo real
    score_real = fit_score > 0.0 and grado != "F"
    if (fit_score >= MIN_SCORE or (req.forzar and score_real)):
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
        print(f"[orchestrator] Oferta descartada para {candidato_nombre}: {empresa_r} — {rol_r}. Score {fit_score}/{MIN_SCORE}.")
        result["mensaje"] = f"Score {fit_score}/5 ({grado}). Oferta {empresa_r} — {rol_r} descartada."
        result["estado"]  = "descartado"

    print(f"[DEBUG_ORCHESTRATOR] Final result: {json.dumps(result, ensure_ascii=False)}")
    return result


@app.get("/career/tracker")
def tracker(perfil_id: Optional[str] = None):
    if perfil_id:
        apps = get_applications_by_perfil(perfil_id)
    else:
        apps = get_all_applications()
    return {"total": len(apps), "aplicaciones": apps}


# ══════════════════════════════════════════════════════════════
# NUEVOS ENDPOINTS — Dashboard Career-Ops v3.0
# ══════════════════════════════════════════════════════════════

import os as _os

# ── API Key middleware ────────────────────────────────────────
CAREER_API_KEY = _os.getenv("CAREER_API_KEY", "")

@app.middleware("http")
async def api_key_guard(request, call_next):
    """Protege todos los endpoints excepto /health y /docs."""
    open_paths = ["/health", "/docs", "/openapi.json", "/redoc"]
    if any(request.url.path.startswith(p) for p in open_paths):
        return await call_next(request)
    if CAREER_API_KEY:
        key = request.headers.get("X-API-Key", "")
        if key != CAREER_API_KEY:
            from starlette.responses import JSONResponse
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


# ── GET perfil individual ─────────────────────────────────────
@app.get("/career/perfiles/{perfil_id}")
def obtener_perfil(perfil_id: str):
    """Devuelve un perfil completo por su UUID."""
    from scripts.supabase_client import get_perfil_by_id
    perfil = get_perfil_by_id(perfil_id)
    if not perfil:
        raise HTTPException(404, f"Perfil {perfil_id} no encontrado")
    return perfil


# ── PATCH perfil (actualizar campos) ─────────────────────────
class PerfilUpdateRequest(BaseModel):
    nombre:    Optional[str] = None
    apellido:  Optional[str] = None
    email:     Optional[str] = None
    titular:   Optional[str] = None
    telefono:  Optional[str] = None
    linkedin:  Optional[str] = None
    mercado:   Optional[str] = None
    idioma:    Optional[str] = None
    datos_json: Optional[dict] = None

@app.patch("/career/perfiles/{perfil_id}")
def actualizar_perfil(perfil_id: str, req: PerfilUpdateRequest):
    """Actualiza campos del perfil. Solo actualiza los campos enviados."""
    from scripts.supabase_client import update_perfil
    cambios = {k: v for k, v in req.dict().items() if v is not None}
    if not cambios:
        raise HTTPException(400, "No se enviaron campos a actualizar")
    resultado = update_perfil(perfil_id, cambios)
    return {"status": "ok", "perfil_id": perfil_id, "actualizado": cambios}


# ── POST cv-pdf (subir PDF → texto → JSON estructurado) ───────
@app.post("/career/perfiles/{perfil_id}/cv-pdf")
async def subir_cv_pdf(perfil_id: str, file: UploadFile = File(...)):
    """
    Acepta un PDF, extrae el texto con pdfminer, lo convierte a JSON
    estructurado via IA y lo guarda en perfil_base.datos_json y cv_markdown.
    """
    from scripts.supabase_client import get_perfil_by_id, update_perfil, upload_file_to_storage
    import io

    # Validar tipo
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos PDF")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 10 * 1024 * 1024:  # 10MB max
        raise HTTPException(400, "El archivo supera el limite de 10MB")

    # Verificar que el perfil existe
    perfil = get_perfil_by_id(perfil_id)
    if not perfil:
        raise HTTPException(404, f"Perfil {perfil_id} no encontrado")

    # Extraer texto del PDF con pdfminer
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(io.BytesIO(pdf_bytes))
        text = text.strip()
        if not text or len(text) < 50:
            raise ValueError("No se pudo extraer texto util del PDF")
    except Exception as e:
        raise HTTPException(422, f"Error extrayendo texto del PDF: {str(e)}")

    # Subir el PDF original a Storage
    storage_path = f"{perfil_id}/cv_original.pdf"
    upload_file_to_storage("cvs-pdf", storage_path, pdf_bytes, "application/pdf")

    # Llamar al endpoint existente analizar-perfil con el texto extraido
    try:
        analizar_resp = call_agent(
            f"http://127.0.0.1:{_os.getenv('PORT', '8020')}",
            "/career/analizar-perfil",
            {
                "perfil_id": perfil_id,
                "cv_texto":  text,
                "idioma":    perfil.get("idioma", "ES")
            }
        )
    except Exception as e:
        # Si el analisis IA falla, al menos guardamos el texto plano
        update_perfil(perfil_id, {"cv_markdown": text})
        return {
            "status":    "partial",
            "perfil_id": perfil_id,
            "mensaje":   f"PDF subido y texto guardado. Analisis IA fallo: {str(e)}",
            "chars":     len(text)
        }

    return {
        "status":    "ok",
        "perfil_id": perfil_id,
        "mensaje":   "PDF procesado y CV estructurado correctamente",
        "chars":     len(text),
        "analisis":  analizar_resp
    }


# ── POST foto (subir imagen → Supabase Storage) ───────────────
@app.post("/career/perfiles/{perfil_id}/foto")
async def subir_foto(perfil_id: str, file: UploadFile = File(...)):
    """Sube una foto del candidato a Supabase Storage y actualiza foto_url."""
    from scripts.supabase_client import get_perfil_by_id, update_perfil, upload_file_to_storage, get_storage_signed_url

    # Validar tipo MIME
    allowed = ["image/jpeg", "image/png", "image/webp"]
    ct = file.content_type or ""
    if ct not in allowed and not file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        raise HTTPException(400, "Solo se aceptan imagenes JPG, PNG o WebP")

    img_bytes = await file.read()
    if len(img_bytes) > 3 * 1024 * 1024:  # 3MB max para fotos
        raise HTTPException(400, "La imagen supera el limite de 3MB")

    perfil = get_perfil_by_id(perfil_id)
    if not perfil:
        raise HTTPException(404, f"Perfil {perfil_id} no encontrado")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    storage_path = f"{perfil_id}/foto.{ext}"

    ok = upload_file_to_storage("fotos-candidatos", storage_path, img_bytes, ct or f"image/{ext}")
    if not ok:
        raise HTTPException(500, "Error subiendo la imagen a Storage")

    # Generar URL firmada (24h) y guardar en perfil
    signed_url = get_storage_signed_url("fotos-candidatos", storage_path, expires_in=86400)
    update_perfil(perfil_id, {"foto_url": signed_url})

    return {
        "status":    "ok",
        "perfil_id": perfil_id,
        "foto_url":  signed_url,
        "mensaje":   "Foto actualizada correctamente"
    }


# ── GET backend status (para el dashboard) ───────────────────
@app.get("/career/backend-status")
def backend_status_info():
    """Informa al dashboard que el backend esta activo y devuelve su URL."""
    import socket
    return {
        "status":  "online",
        "version": "2.0.0",
        "host":    socket.gethostname()
    }


# ── POST generar-cv-principal (descarga CV base con diseño premium) ───
class GenerarCVPrincipalRequest(BaseModel):
    perfil_id: str
    con_foto:  bool = True
    idioma:    str  = "ES"

@app.post("/career/generar-cv-principal")
def generar_cv_principal(req: GenerarCVPrincipalRequest):
    """
    Genera el CV principal del candidato con el diseño premium (agente-hr-diseno).
    Devuelve una URL firmada de Supabase Storage válida 30 minutos.
    El archivo se elimina del bucket automáticamente tras 30 minutos.
    No requiere oferta de trabajo — es el CV base listo para descargar.
    """
    from scripts.supabase_client import (
        get_perfil_by_id, upload_file_to_storage,
        get_storage_signed_url, delete_storage_file
    )

    perfil = get_perfil_by_id(req.perfil_id)
    if not perfil:
        raise HTTPException(404, f"Perfil {req.perfil_id} no encontrado")

    datos_json_raw = perfil.get("datos_json") or {}
    if isinstance(datos_json_raw, str):
        try:
            datos_json_raw = json.loads(datos_json_raw)
        except Exception:
            datos_json_raw = {}

    # Verificar que hay CV para generar
    if not perfil.get("cv_markdown") and not datos_json_raw.get("resumen"):
        raise HTTPException(400, "No hay CV cargado. Sube tu PDF en Mi CV primero.")

    foto_modo = "con_foto" if req.con_foto else "sin_foto"
    foto_url  = datos_json_raw.get("foto_url") if req.con_foto else None

    nombre = f"{perfil.get('nombre', '')} {perfil.get('apellido', '')}".strip()

    try:
        # Llamar al agente de diseño de forma sincrona
        diseno_resp = call_agent(DISENO_URL, "/generar-cv-html", {
            "perfil_id":     req.perfil_id,
            "foto_modo":     foto_modo,
            "foto_url":      foto_url,
            "idioma":        req.idioma,
        }, timeout=180)

        # El agente devuelve la URL firmada directamente si ya subio el PDF a Storage
        pdf_url = diseno_resp.get("pdf_url") or diseno_resp.get("signed_url") or ""

        if not pdf_url:
            raise HTTPException(500, "El agente de diseño no devolvió una URL de PDF.")

        return {
            "status":   "ok",
            "perfil":   nombre,
            "pdf_url":  pdf_url,
            "expira_en": "30 minutos",
            "mensaje":  f"CV de {nombre} generado correctamente. La URL expira en 30 minutos.",
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("generar_cv_principal", str(e), extra={"perfil_id": req.perfil_id})
        raise HTTPException(500, f"Error generando CV: {e}")