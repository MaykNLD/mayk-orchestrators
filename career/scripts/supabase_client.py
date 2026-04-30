"""
supabase_client.py — Wrapper REST para Supabase (sin SDK externo)
Soporte multi-usuario: cada operacion puede recibir perfil_id
"""
import os, json, urllib.request, urllib.error
from typing import Optional

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip()

# Prioridad: service_role key (necesaria para Storage y operaciones admin)
# Intentamos SUPABASE_SECRET_KEY primero, luego SUPABASE_KEY, luego SUPABASE_ANON_KEY
_secret_key = (os.environ.get("SUPABASE_SECRET_KEY") or "").strip()
_key        = (os.environ.get("SUPABASE_KEY")        or "").strip()
_anon_key   = (os.environ.get("SUPABASE_ANON_KEY")   or "").strip()

# La service_role key siempre es más larga que la anon key (>200 chars)
# Usamos la primera que parezca un JWT válido (empieza con "eyJ")
def _pick_best_key(*keys):
    for k in keys:
        if k and k.startswith("eyJ") and len(k) > 100:
            return k
    for k in keys:
        if k:
            return k
    return ""

SUPABASE_KEY = _pick_best_key(_secret_key, _key, _anon_key)

# Para operaciones de Storage siempre usar la service_role key
SUPABASE_SERVICE_KEY = _pick_best_key(_secret_key, _key)


def _headers():
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }

def _get(table: str, query: str = "") -> list:
    url = f"{SUPABASE_URL}/rest/v1/{table}{'?' + query if query else ''}"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return []

def _post(table: str, data: dict) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
            return result[0] if isinstance(result, list) and result else {}
    except Exception as e:
        return {}

def _patch(table: str, eq_field: str, eq_value: str, data: dict) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{eq_field}=eq.{eq_value}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(), method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
            return result[0] if isinstance(result, list) and result else {}
    except Exception as e:
        return {}

# ─── PERFILES (multi-usuario) ────────────────────────────────────

def list_perfiles() -> list:
    """Lista todos los perfiles disponibles."""
    return _get("perfil_base", "select=id,nombre,apellido,email,mercado,idioma&order=created_at.asc")

def get_perfil_by_id(perfil_id: str) -> Optional[dict]:
    """Obtiene un perfil por su UUID."""
    result = _get("perfil_base", f"id=eq.{perfil_id}&limit=1")
    return result[0] if result else None

def get_first_perfil() -> Optional[dict]:
    """Fallback: primer perfil de la tabla (cuando solo hay uno)."""
    result = _get("perfil_base", "order=created_at.asc&limit=1")
    return result[0] if result else None

def create_perfil(data: dict) -> dict:
    return _post("perfil_base", data)

def update_perfil(perfil_id: str, data: dict) -> dict:
    """Actualiza campos del perfil base (nombre, email, cv_markdown, etc.)"""
    return _patch("perfil_base", "id", perfil_id, data)

def get_pending_cv_extractions(limit: int = 5) -> list:
    """Devuelve perfiles con cv_extraction_pending=true para que el worker procese su PDF."""
    return _get("perfil_base", f"cv_extraction_pending=eq.true&limit={limit}&select=id,nombre,apellido,datos_json,cv_markdown,idioma,mercado")

def delete_perfil(perfil_id: str) -> bool:
    """Elimina un perfil de la tabla perfil_base. Devuelve True si tuvo exito."""
    url = f"{SUPABASE_URL}/rest/v1/perfil_base?id=eq.{perfil_id}"
    req = urllib.request.Request(url, headers=_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in [200, 204]
    except Exception as e:
        print(f"[supabase_client] Error eliminando perfil {perfil_id}: {e}")
        return False

# ─── APLICACIONES ────────────────────────────────────────────────

def create_application(data: dict) -> dict:
    return _post("aplicaciones_career", data)

def update_application(app_id: str, data: dict) -> dict:
    return _patch("aplicaciones_career", "id", app_id, data)

def get_application(app_id: str) -> dict:
    result = _get("aplicaciones_career", f"id=eq.{app_id}&limit=1")
    return result[0] if result else {}

def delete_application(app_id: str) -> bool:
    """Elimina una aplicacion (historial) de la base de datos."""
    url = f"{SUPABASE_URL}/rest/v1/aplicaciones_career?id=eq.{app_id}"
    req = urllib.request.Request(url, headers=_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in [200, 204]
    except Exception as e:
        print(f"[supabase_client] Error eliminando app {app_id}: {e}")
        return False

def get_applications_by_perfil(perfil_id: str, limit: int = 50) -> list:
    return _get("aplicaciones_career",
                f"perfil_id=eq.{perfil_id}&order=created_at.desc&limit={limit}")

def get_application_by_url(perfil_id: str, offer_url: str) -> Optional[dict]:
    import urllib.parse
    safe_url = urllib.parse.quote(offer_url, safe='')
    result = _get("aplicaciones_career", f"perfil_id=eq.{perfil_id}&url=eq.{safe_url}&limit=1")
    return result[0] if result else None

def get_all_applications(limit: int = 50) -> list:
    return _get("aplicaciones_career", f"order=created_at.desc&limit={limit}")

def get_pending_applications(perfil_id: Optional[str] = None) -> list:
    base = "status=eq.pendiente&order=created_at.desc&limit=20"
    if perfil_id:
        base = f"perfil_id=eq.{perfil_id}&{base}"
    return _get("aplicaciones_career", base)

def get_evaluando_applications(limit: int = 5) -> list:
    """Obtiene las candidaturas que el dashboard marcó para ser procesadas."""
    return _get("aplicaciones_career", f"status=eq.evaluando&order=created_at.asc&limit={limit}")

def get_todays_processed_count(perfil_id: str) -> int:
    """
    Cuenta cuántas candidaturas de ese perfil han sido procesadas hoy
    (excluyendo pendiente/evaluando — solo las que ya pasaron por la IA).
    Usado para rate limiting diario por usuario.
    """
    import datetime
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    results = _get(
        "aplicaciones_career",
        f"perfil_id=eq.{perfil_id}"
        f"&status=not.in.(pendiente,evaluando)"
        f"&created_at=gte.{today}T00:00:00Z"
        f"&select=id"
    )
    return len(results)


def update_heartbeat() -> None:
    """Actualiza el heartbeat del backend en Supabase para que el dashboard sepa que está vivo."""
    import datetime
    url = f"{SUPABASE_URL}/rest/v1/backend_status?on_conflict=id"
    h = _headers()
    h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    data = json.dumps({
        "id": "career-orchestrator",
        "last_seen": datetime.datetime.utcnow().isoformat() + "Z",
        "status": "online"
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()
    except Exception as e:
        print(f"[heartbeat] Error actualizando heartbeat: {e}")

# ─── SCAN HISTORY ────────────────────────────────────────────────

def get_scan_history() -> list:
    return _get("scan_history", "select=url&limit=5000")

def upsert_scan_history(data: dict) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/scan_history"
    h = _headers()
    h["Prefer"] = "resolution=merge-duplicates,return=representation"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}

# ─── LOG EJECUCIONES ─────────────────────────────────────────────

def log_ejecucion(data: dict) -> dict:
    return _post("career_ejecuciones", data)

# ─── STORAGE ─────────────────────────────────────────────────────

def upload_file_to_storage(bucket: str, path: str, file_bytes: bytes, content_type: str = "application/pdf") -> bool:
    """Sube un archivo binario a un bucket de Supabase."""
    safe_path = urllib.parse.quote(path)
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{safe_path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": content_type
    }
    req = urllib.request.Request(url, data=file_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status in [200, 201]
    except Exception as e:
        print(f"[supabase_client] Error subiendo archivo a storage: {e}")
        # Intentar forzar actualizacion (UPSERT)
        try:
            req_put = urllib.request.Request(url, data=file_bytes, headers=headers, method="PUT")
            with urllib.request.urlopen(req_put, timeout=30) as r:
                return r.status in [200, 201]
        except Exception as e2:
            print(f"[supabase_client] Supabase Upsert Storage error: {e2}")
            return False

def get_storage_signed_url(bucket: str, path: str, expires_in: int = 1800) -> str:
    """Solicita una URL firmada de un bucket cerrado que expira en X segundos."""
    safe_path = urllib.parse.quote(path)
    url = f"{SUPABASE_URL}/storage/v1/object/sign/{bucket}/{safe_path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    body = json.dumps({"expiresIn": expires_in}).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            
            result = json.loads(r.read().decode())
            signed_path = result.get("signedURL")
            if signed_path:
                if not signed_path.startswith("/storage/v1"):
                    if signed_path.startswith("/"):
                        return f"{SUPABASE_URL}/storage/v1{signed_path}"
                    return f"{SUPABASE_URL}/storage/v1/{signed_path}"
                return f"{SUPABASE_URL}{signed_path}"
            return ""
    except Exception as e:
        print(f"[supabase_client] Error generando signed url: {e}")
        return ""

def delete_storage_file(bucket: str, path: str) -> bool:
    """Elimina físicamente un archivo de storage (ej. para limpiar residuos tras el envío)"""
    safe_path = urllib.parse.quote(path)
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{safe_path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in [200, 204]
    except Exception as e:
        print(f"[supabase_client] Error eliminando archivo temp de storage: {e}")
        return False


# ─── PDF STORAGE (usado por el worker tras generar PDF con Playwright) ─────────

def upload_pdf_to_storage(pdf_bytes: bytes, perfil_id: str) -> str:
    """Sube un PDF a Supabase Storage (bucket cvs-pdf) y devuelve la ruta del archivo.
    Usa SUPABASE_SERVICE_KEY (service_role) para saltarse RLS.
    Lanza RuntimeError si falla — nunca devuelve None.
    """
    import time as _time
    import urllib.error as _ue

    key = SUPABASE_SERVICE_KEY
    if not SUPABASE_URL or not key:
        raise RuntimeError(
            f"Credenciales Storage no configuradas. "
            f"URL={'OK' if SUPABASE_URL else 'FALTA'} KEY={'OK' if key else 'FALTA'} "
            f"(SUPABASE_SECRET_KEY={bool(os.environ.get('SUPABASE_SECRET_KEY'))} "
            f"SUPABASE_KEY={bool(os.environ.get('SUPABASE_KEY'))})"
        )

    if not pdf_bytes:
        raise RuntimeError("pdf_bytes esta vacio, no hay nada que subir")

    filename   = f"{perfil_id}/{int(_time.time())}_cv.pdf"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/cvs-pdf/{filename}"
    headers    = {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/pdf",
        "x-upsert":      "true",
    }
    print(f"[supabase_client] Upload Storage con key[0:20]={key[:20]}...")
    req = urllib.request.Request(upload_url, data=pdf_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status not in (200, 201):
                raise RuntimeError(f"Storage upload HTTP {r.status}")
        print(f"[supabase_client] PDF subido OK: {filename} ({len(pdf_bytes)} bytes)")
        return filename
    except _ue.HTTPError as e:
        body = e.read().decode(errors="ignore")[:400]
        raise RuntimeError(f"Storage upload HTTP {e.code}: {body}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Storage upload error: {e}")


def get_signed_url_for_pdf(filename: str, expires_in: int = 86400) -> str:
    """Genera una URL firmada para un archivo en el bucket cvs-pdf.
    Usa SUPABASE_SERVICE_KEY (service_role) para saltarse RLS.
    Lanza RuntimeError si falla — nunca devuelve None.
    """
    import urllib.error as _ue

    key = SUPABASE_SERVICE_KEY
    if not SUPABASE_URL or not key:
        raise RuntimeError("Credenciales Storage no configuradas para firmar URL")

    sign_url   = f"{SUPABASE_URL}/storage/v1/object/sign/cvs-pdf/{filename}"
    body_bytes = json.dumps({"expiresIn": expires_in}).encode()
    headers    = {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }
    req = urllib.request.Request(sign_url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data        = json.loads(r.read().decode())
            signed_path = (data.get("signedURL") or "").strip()
            if not signed_path:
                raise RuntimeError(f"signedURL vacio. Respuesta completa: {data}")
            if signed_path.startswith("/"):
                return f"{SUPABASE_URL}/storage/v1{signed_path}"
            return signed_path
    except _ue.HTTPError as e:
        body = e.read().decode(errors="ignore")[:400]
        raise RuntimeError(f"Storage sign HTTP {e.code}: {body}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Storage sign error: {e}")


# ─── CV DOWNLOAD REQUESTS (Job Queue) ───────────────────────────────────────

def create_cv_download_request(perfil_id: str, con_foto: bool = True, idioma: str = "ES") -> dict:
    """Crea un job de descarga de CV. El Worker lo procesará en el siguiente ciclo."""
    return _post("cv_download_requests", {
        "perfil_id": perfil_id,
        "con_foto":  con_foto,
        "idioma":    idioma,
        "status":    "pending",
    })

def get_pending_cv_download_requests(limit: int = 3) -> list:
    """Obtiene los jobs de descarga pendientes ordenados por antigüedad."""
    return _get("cv_download_requests",
                f"status=eq.pending&order=created_at.asc&limit={limit}")

def update_cv_download_request(request_id: str, data: dict) -> dict:
    """Actualiza el estado del job (processing / done / error + signed_url)."""
    import datetime
    data["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    return _patch("cv_download_requests", "id", request_id, data)

def cleanup_old_cv_download_requests(older_than_days: int = 7) -> int:
    """Borra cv_download_requests con status done/error mas antiguos de N dias.
    Evita que la tabla acumule datos base64 pesados sin utilidad.
    Devuelve el numero de registros borrados (0 si no hay o si falla).
    """
    import datetime
    cutoff = (
        datetime.datetime.utcnow() - datetime.timedelta(days=older_than_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Supabase REST: DELETE con filtros compuestos en query string
    url = (
        f"{SUPABASE_URL}/rest/v1/cv_download_requests"
        f"?status=in.(done,error)&created_at=lt.{cutoff}"
    )
    req = urllib.request.Request(
        url, method="DELETE",
        headers={**_headers(), "Prefer": "return=representation"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            deleted = json.loads(r.read().decode())
            count = len(deleted) if isinstance(deleted, list) else 0
            if count:
                print(f"[supabase] 🧹 Limpieza TTL: {count} cv_download_requests borrados (>7 dias)")
            return count
    except Exception as e:
        print(f"[supabase] Advertencia: cleanup_old_cv_download_requests fallo: {e}")
        return 0


def log_error(context: str, error: str, app_id: Optional[str] = None, extra: Optional[dict] = None) -> dict:
    """Persiste un error critico del pipeline en Supabase (tabla career_errores)
    Y envia una alerta al webhook de Make.com para notificacion proactiva.
    No lanza excepciones — si falla el log o el webhook, no rompe el flujo principal.
    """
    import datetime

    result = {}
    try:
        data = {
            "context":  context,
            "error":    error[:2000],  # truncar para evitar payloads gigantes
            "app_id":   app_id,
            "extra":    extra or {},
        }
        result = _post("career_errores", data)
    except Exception as e:
        print(f"[supabase_client] No se pudo loguear error en Supabase: {e}")

    # ── Alerta proactiva a Make.com ────────────────────────────────────
    # Si MAKE_WEBHOOK_URL está definida, notificar el error para Telegram/Email.
    # Se usa un payload de tipo ERROR_CRITICO para que Make.com lo distinga
    # de cualquier otro mensaje y ejecute el escenario de alerta.
    try:
        make_url = os.environ.get("MAKE_WEBHOOK_URL", "")
        if make_url:
            import urllib.request as _ureq
            payload = {
                "tipo":          "ERROR_CRITICO",
                "contexto":      context,
                "mensaje_error": error[:500],  # resumen para Telegram
                "app_id":        app_id or "N/A",
                "timestamp":     datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "extra":         str(extra or {}),
            }
            body = json.dumps(payload).encode()
            req  = _ureq.Request(
                make_url, data=body,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            _ureq.urlopen(req, timeout=8)
            print(f"[supabase_client] Alerta de error enviada a Make.com: {context}")
    except Exception as e_make:
        print(f"[supabase_client] No se pudo enviar alerta a Make.com: {e_make}")

    return result