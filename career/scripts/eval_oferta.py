"""
eval_oferta.py — CLI rapido para evaluar una oferta sin pipeline completo
Uso: python eval_oferta.py --url https://... [--perfil perfil.json]
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from supabase_client import get_first_perfil

EVALUADOR_URL = os.environ.get("AGENTE_HR_EVALUADOR_URL", "http://localhost:8011")

def main():
    parser = argparse.ArgumentParser(description="Evalua una oferta de trabajo")
    parser.add_argument("--url", help="URL de la oferta")
    parser.add_argument("--texto", help="Texto de la JD (alternativa a URL)")
    parser.add_argument("--perfil", help="JSON file del perfil (si no hay Supabase)")
    parser.add_argument("--idioma", default="ES")
    args = parser.parse_args()

    if not args.url and not args.texto:
        print("Proporciona --url o --texto")
        sys.exit(1)

    if args.perfil:
        perfil = json.loads(Path(args.perfil).read_text(encoding="utf-8"))
    else:
        perfil = get_first_perfil()
        if not perfil:
            print("No hay perfil en Supabase. Usa --perfil perfil.json")
            sys.exit(1)
        perfil = perfil.get("datos_json", {})

    payload = {"perfil_base_json": perfil, "idioma": args.idioma}
    if args.url:    payload["url_oferta"] = args.url
    if args.texto:  payload["texto_oferta"] = args.texto

    print(f"Evaluando oferta... (puede tardar 30-60 segundos)")
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{EVALUADOR_URL}/execute", data=data,
          headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode())
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Score:        {resp.get('fit_score', 0)}/5  ({resp.get('grado', '?')})")
    print(f"Recomendacion: {resp.get('recomendacion', '?')}")
    print(f"{'='*60}")

    try:
        detail = json.loads(resp.get("result", "{}"))
        print(f"\nArquetipo: {detail.get('arquetipo', '?')}")
        print(f"Legitimidad: {detail.get('bloque_g', {}).get('assessment', '?') if isinstance(detail.get('bloque_g'), dict) else '?'}")
        kws = detail.get("keywords_clave", [])
        if kws:
            print(f"\nKeywords ATS ({len(kws)}): {', '.join(kws[:10])}")
    except Exception:
        print(resp.get("result",""))

if __name__ == "__main__":
    main()