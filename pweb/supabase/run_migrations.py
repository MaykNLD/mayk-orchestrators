#!/usr/bin/env python3
"""
run_migrations.py — Aplica las migraciones SQL contra Supabase vía API REST.
Lee las credenciales desde variables de entorno o desde /home/mayk/mayk-dev/.env

Uso:
    python3 run_migrations.py
    SUPABASE_URL=... SUPABASE_SECRET_KEY=... python3 run_migrations.py
"""

import os
import json
import urllib.request
import urllib.error
import pathlib

# ─── Cargar .env si existe ────────────────────────────────────────────────────
ENV_FILE = pathlib.Path("/home/mayk/mayk-dev/.env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            if key.strip() and val.strip():
                os.environ.setdefault(key.strip(), val.strip())

SUPABASE_URL       = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "supabase" / "migrations"


def check_config():
    if not SUPABASE_URL:
        raise RuntimeError("❌ SUPABASE_URL no configurada. Rellena /home/mayk/mayk-dev/.env")
    if not SUPABASE_SECRET_KEY:
        raise RuntimeError("❌ SUPABASE_SECRET_KEY no configurada. Rellena /home/mayk/mayk-dev/.env")


def run_sql(sql: str, label: str):
    """Ejecuta SQL contra Supabase via endpoint REST /rest/v1/rpc/exec"""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec"
    payload = json.dumps({"sql": sql}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return True, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        # 404 en /rpc/exec significa que la función no existe — usamos el modo pg
        if e.code == 404:
            return run_sql_direct(sql, label)
        return False, f"HTTP {e.code}: {body}"


def run_sql_direct(sql: str, label: str):
    """
    Alternativa: usa el endpoint de administración de Supabase.
    Requiere el service_role key y ejecuta SQL puro directamente.
    """
    # Supabase expone /pg vía el endpoint de la plataforma (no disponible en proyectos hosted vía URL pública).
    # Aquí inyectamos el SQL directamente a través del API REST con el service key
    # usando una función auxiliar que Supabase ya tiene disponible.
    url = f"{SUPABASE_URL}/rest/v1/"
    # El enfoque correcto cuando no hay RPC exec: dividir por statements e imprimir
    print(f"    ⚠️  La función RPC exec no existe. El SQL debe aplicarse manualmente.")
    print(f"    📋 Copia y pega el contenido de migrations/001_initial_schema.sql")
    print(f"       en el SQL Editor de tu proyecto Supabase.")
    print(f"    🔗 https://supabase.com/dashboard/project/[tu-ref]/sql/new")
    return False, "RPC exec no disponible"


def main():
    print("🗄️  Iniciando migraciones Supabase…\n")
    check_config()

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("⚠️  No hay archivos de migración en:", MIGRATIONS_DIR)
        return

    print(f"📁 Directorio: {MIGRATIONS_DIR}")
    print(f"📦 Archivos encontrados: {len(migration_files)}\n")

    for sql_file in migration_files:
        sql_content = sql_file.read_text()
        print(f"→ Aplicando {sql_file.name}…")
        ok, response = run_sql(sql_content, sql_file.name)
        if ok:
            print(f"  ✅ {sql_file.name} aplicado correctamente")
        else:
            print(f"  ❌ Error en {sql_file.name}: {response}")

    print("\n⚠️  Nota: Si la migración requiere aplicación manual, usa el SQL Editor de Supabase.")
    print(f"   Archivo: {migration_files[0]}")


if __name__ == "__main__":
    main()
