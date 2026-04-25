"""
supabase_client.py — Wrapper REST para Supabase (sin SDK externo)
Soporte multi-usuario: cada operacion puede recibir perfil_id
"""
import os, json, urllib.request, urllib.error
from typing import Optional

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

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

def update_heartbeat() -> None:
    """Actualiza el heartbeat del backend en Supabase para que el dashboard sepa que está vivo."""
    import datetime
    url = f"{SUPABASE_URL}/rest/v1/backend_status"
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


def log_error(context: str, error: str, app_id: Optional[str] = None, extra: Optional[dict] = None) -> dict:
    """Persiste un error critico del pipeline en Supabase (tabla career_errores).
    No lanza excepciones — si falla el log, no debe romper el flujo principal.
    """
    try:
        data = {
            "context":  context,
            "error":    error[:2000],  # truncar para evitar payloads gigantes
            "app_id":   app_id,
            "extra":    extra or {},
        }
        return _post("career_errores", data)
    except Exception as e:
        print(f"[supabase_client] No se pudo loguear error en Supabase: {e}")
        return {}