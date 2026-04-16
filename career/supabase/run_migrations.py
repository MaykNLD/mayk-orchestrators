"""
run_migrations.py — Ejecuta las migraciones SQL en Supabase
Uso: python career/supabase/run_migrations.py
"""
import os
import sys
from pathlib import Path

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Configura SUPABASE_URL y SUPABASE_KEY como variables de entorno.")
    sys.exit(1)

import urllib.request, json

migrations_dir = Path(__file__).parent / "migrations"
sql_files = sorted(migrations_dir.glob("*.sql"))

for sql_file in sql_files:
    print(f"Ejecutando: {sql_file.name}")
    sql = sql_file.read_text(encoding="utf-8")
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    data = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                 "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  OK: {sql_file.name}")
    except Exception as e:
        print(f"  NOTA: Ejecuta {sql_file.name} manualmente en el SQL Editor de Supabase.")
        print(f"  (La API REST de Supabase no permite SQL arbitrario — usa el Dashboard)")