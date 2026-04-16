"""
supabase_client.py — Wrapper Supabase para el modulo career
Usa la API REST de Supabase directamente (sin SDK externo).
"""
import os, json, urllib.request, urllib.error
from typing import Optional, Dict, Any, List

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def _get(table: str, filters: str = "") -> List[Dict]:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filters}"
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def _post(table: str, data: Dict) -> Dict:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.loads(r.read().decode())
        return result[0] if isinstance(result, list) else result

def _patch(table: str, filters: str, data: Dict) -> Dict:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filters}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(), method="PATCH")
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.loads(r.read().decode())
        return result[0] if isinstance(result, list) else result

# ── Funciones de alto nivel ──────────────────────────────────────

def get_pending_applications(limit: int = 10) -> List[Dict]:
    """Devuelve aplicaciones con status=pendiente."""
    return _get("aplicaciones_career", f"status=eq.pendiente&order=created_at.asc&limit={limit}")

def get_perfil_base(perfil_id: str) -> Optional[Dict]:
    """Devuelve el perfil base de un candidato por ID."""
    results = _get("perfil_base", f"id=eq.{perfil_id}")
    return results[0] if results else None

def get_first_perfil() -> Optional[Dict]:
    """Devuelve el primer perfil disponible (sistema mono-candidato)."""
    results = _get("perfil_base", "order=created_at.asc&limit=1")
    return results[0] if results else None

def create_application(data: Dict) -> Dict:
    """Crea una nueva candidatura."""
    return _post("aplicaciones_career", data)

def update_application(app_id: str, data: Dict) -> Dict:
    """Actualiza una candidatura por ID."""
    return _patch("aplicaciones_career", f"id=eq.{app_id}", data)

def log_ejecucion(data: Dict) -> Dict:
    """Registra una ejecucion del pipeline."""
    return _post("career_ejecuciones", data)

def url_seen(url: str) -> bool:
    """Verifica si una URL ya fue vista por el scanner."""
    results = _get("scan_history", f"url=eq.{urllib.request.quote(url, safe='')}")
    return len(results) > 0

def add_scan_history(url: str, portal: str, company: str, title: str, status: str):
    """Registra una URL en el historial del scanner."""
    try:
        _post("scan_history", {"url": url, "portal": portal, "company": company,
                                "job_title": title, "status": status})
    except Exception:
        pass  # Ignorar duplicados (UNIQUE constraint)