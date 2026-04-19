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

# ─── APLICACIONES ────────────────────────────────────────────────

def create_application(data: dict) -> dict:
    return _post("aplicaciones_career", data)

def update_application(app_id: str, data: dict) -> dict:
    return _patch("aplicaciones_career", "id", app_id, data)

def get_application(app_id: str) -> dict:
    result = _get("aplicaciones_career", f"id=eq.{app_id}&limit=1")
    return result[0] if result else {}

def get_applications_by_perfil(perfil_id: str, limit: int = 50) -> list:
    return _get("aplicaciones_career",
                f"perfil_id=eq.{perfil_id}&order=created_at.desc&limit={limit}")

def get_all_applications(limit: int = 50) -> list:
    return _get("aplicaciones_career", f"order=created_at.desc&limit={limit}")

def get_pending_applications(perfil_id: Optional[str] = None) -> list:
    base = "status=eq.pendiente&order=created_at.desc&limit=20"
    if perfil_id:
        base = f"perfil_id=eq.{perfil_id}&{base}"
    return _get("aplicaciones_career", base)

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
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
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

def get_storage_public_url(bucket: str, path: str) -> str:
    """Devuelve la URL publica de un archivo en Supabase Storage"""
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"


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