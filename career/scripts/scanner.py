"""
scanner.py — Scanner multi-portal de ofertas de empleo
Nivel 1: APIs directas de ATS (Ashby, Lever, Greenhouse)
Nivel 2: Playwright (portales custom)
Nivel 3: Fallback (instrucciones manuales)

Uso:
  python career/scripts/scanner.py
  python career/scripts/scanner.py --portal ashby --company factorial
  python career/scripts/scanner.py --url https://jobs.ashbyhq.com/factorial
"""
import argparse, json, time, urllib.request, urllib.error
from pathlib import Path
from datetime import date
import sys

sys.path.insert(0, str(Path(__file__).parent))
from supabase_client import get_scan_history, upsert_scan_history, create_application, get_first_perfil

# ─── Configuracion ───────────────────────────────────────────────
PORTALS_FILE = Path(__file__).parent.parent / "data" / "portals.yml"
OUTPUT_DIR   = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Umbral maximo de dias de antiguedad de la oferta
MAX_DAYS = 30

# ─── Nivel 1: APIs directas ATS ─────────────────────────────────

def fetch_ashby(company_slug: str) -> list[dict]:
    """API publica de Ashby HQ."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mayk-career-scanner/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            jobs = data.get("jobs", [])
            results = []
            for j in jobs:
                results.append({
                    "title":   j.get("title", ""),
                    "company": company_slug,
                    "url":     j.get("jobUrl", ""),
                    "portal":  "ashby",
                    "location": j.get("location", ""),
                    "published": j.get("publishedDate", ""),
                    "department": j.get("department", ""),
                })
            return results
    except Exception as e:
        print(f"  [Ashby/{company_slug}] Error: {e}")
        return []


def fetch_lever(company_slug: str) -> list[dict]:
    """API publica de Lever."""
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mayk-career-scanner/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            jobs = json.loads(r.read().decode())
            results = []
            for j in jobs:
                results.append({
                    "title":   j.get("text", ""),
                    "company": company_slug,
                    "url":     j.get("hostedUrl", ""),
                    "portal":  "lever",
                    "location": j.get("categories", {}).get("location", ""),
                    "published": str(j.get("createdAt", "")),
                    "department": j.get("categories", {}).get("department", ""),
                })
            return results
    except Exception as e:
        print(f"  [Lever/{company_slug}] Error: {e}")
        return []


def fetch_greenhouse(company_slug: str) -> list[dict]:
    """API publica de Greenhouse."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mayk-career-scanner/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            jobs = data.get("jobs", [])
            results = []
            for j in jobs:
                dept = j.get("departments", [{}])[0].get("name", "") if j.get("departments") else ""
                results.append({
                    "title":   j.get("title", ""),
                    "company": company_slug,
                    "url":     j.get("absolute_url", ""),
                    "portal":  "greenhouse",
                    "location": j.get("location", {}).get("name", ""),
                    "published": j.get("updated_at", ""),
                    "department": dept,
                })
            return results
    except Exception as e:
        print(f"  [Greenhouse/{company_slug}] Error: {e}")
        return []


# ─── Nivel 2: Playwright ─────────────────────────────────────────

def fetch_playwright(url: str, company: str) -> list[dict]:
    """Usa Playwright para portales sin API publica."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [Playwright] No instalado. Ejecuta: pip install playwright && playwright install chromium")
        return []

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Extraer enlaces que parezcan ofertas de trabajo
            links = page.evaluate("""() => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                return anchors
                    .filter(a => {
                        const href = a.href.toLowerCase();
                        const text = a.textContent.toLowerCase();
                        return (href.includes('job') || href.includes('career') ||
                                text.includes('developer') || text.includes('engineer') ||
                                text.includes('programador') || text.includes('backend') ||
                                text.includes('frontend') || text.includes('python'));
                    })
                    .map(a => ({ title: a.textContent.trim(), url: a.href }))
                    .filter(j => j.title.length > 3 && j.title.length < 200)
                    .slice(0, 30);
            }""")

            for link in links:
                results.append({
                    "title":   link["title"],
                    "company": company,
                    "url":     link["url"],
                    "portal":  "playwright",
                    "location": "",
                    "published": str(date.today()),
                    "department": "",
                })
            browser.close()
    except Exception as e:
        print(f"  [Playwright/{company}] Error: {e}")
    return results


# ─── Filtro de relevancia ────────────────────────────────────────

POSITIVE = ["developer","engineer","backend","frontend","fullstack","full-stack",
            "python","java","javascript","typescript","react","node","qa","testing",
            "devops","software","programador","desarrollador","junior","mid","associate"]
NEGATIVE = ["principal","staff","vp ","director","manager","head of","cto","c-level","lead"]

def is_relevant(title: str) -> bool:
    t = title.lower()
    if any(neg in t for neg in NEGATIVE): return False
    return any(pos in t for pos in POSITIVE)


# ─── Deduplicacion contra scan_history ──────────────────────────

def is_duplicate(url: str) -> bool:
    history = get_scan_history()
    seen_urls = {h["url"] for h in history}
    return url in seen_urls


# ─── Runner principal ────────────────────────────────────────────

def load_portals_config() -> list[dict]:
    """Lee portals.yml si existe, o usa config minima por defecto."""
    if PORTALS_FILE.exists():
        import re
        text = PORTALS_FILE.read_text(encoding="utf-8")
        # Extrae las empresas activas con api_provider
        companies = []
        current = {}
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("- name:"):
                if current.get("enabled") is not False and current.get("name"):
                    companies.append(current)
                current = {"name": line.split(":",1)[1].strip().strip("'\"")}
            elif line.startswith("api_provider:"):
                current["api_provider"] = line.split(":",1)[1].strip()
            elif line.startswith("api:"):
                current["api"] = line.split(":",1)[1].strip()
            elif line.startswith("careers_url:"):
                current["careers_url"] = line.split(":",1)[1].strip().strip("'\"")
            elif line.startswith("enabled: false"):
                current["enabled"] = False
        if current.get("enabled") is not False and current.get("name"):
            companies.append(current)
        return companies
    # Fallback minimo
    return [
        {"name": "factorial", "api_provider": "ashby"},
        {"name": "adevinta", "api_provider": "lever"},
    ]


def run_scan(max_results: int = 50) -> list[dict]:
    print("\n=== mayk Career Scanner ===\n")
    companies = load_portals_config()
    all_jobs  = []
    new_jobs  = []

    fetchers = {
        "ashby":      fetch_ashby,
        "lever":      fetch_lever,
        "greenhouse": fetch_greenhouse,
    }

    for company in companies:
        name     = company.get("name", "")
        provider = company.get("api_provider", "")
        url      = company.get("careers_url", "")
        print(f"  Escaneando: {name} [{provider or 'playwright'}]")

        if provider in fetchers:
            jobs = fetchers[provider](name)
        elif url:
            jobs = fetch_playwright(url, name)
        else:
            print(f"    Sin metodo disponible para {name}")
            continue

        print(f"    {len(jobs)} ofertas encontradas")
        for job in jobs:
            if not is_relevant(job["title"]):
                continue
            if is_duplicate(job["url"]):
                continue
            job["nuevo"] = True
            new_jobs.append(job)
            all_jobs.append(job)
            if len(all_jobs) >= max_results:
                break

        time.sleep(1)  # Rate limit educado
        if len(all_jobs) >= max_results:
            break

    # Persistir en scan_history
    for job in new_jobs:
        try:
            upsert_scan_history({
                "url":       job["url"],
                "portal":    job.get("portal", ""),
                "company":   job.get("company", ""),
                "job_title": job.get("title", ""),
                "status":    "nuevo",
            })
        except Exception:
            pass

    # Guardar resultado en JSON
    out_file = OUTPUT_DIR / f"scan_{date.today()}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(new_jobs, f, ensure_ascii=False, indent=2)

    print(f"\n  Nuevas ofertas relevantes: {len(new_jobs)}")
    print(f"  Resultado guardado en: {out_file}")

    # Imprimir resumen
    if new_jobs:
        print("\n  ┌─────────────────────────────────────────────────────────────────")
        for j in new_jobs[:10]:
            print(f"  │ {j['company']:<15} | {j['title'][:40]:<40} | {j.get('location','')}")
        if len(new_jobs) > 10:
            print(f"  │ ... y {len(new_jobs)-10} mas")
        print("  └─────────────────────────────────────────────────────────────────")

    return new_jobs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="mayk Career Scanner")
    parser.add_argument("--portal", choices=["ashby","lever","greenhouse","playwright"], help="Portal especifico")
    parser.add_argument("--company", help="Slug de empresa (ej: factorial)")
    parser.add_argument("--url", help="URL directa para Playwright")
    parser.add_argument("--max", type=int, default=50, help="Maximo de resultados")
    args = parser.parse_args()

    if args.company and args.portal:
        fetchers = {"ashby": fetch_ashby, "lever": fetch_lever, "greenhouse": fetch_greenhouse}
        if args.portal in fetchers:
            jobs = fetchers[args.portal](args.company)
        elif args.url:
            jobs = fetch_playwright(args.url, args.company)
        else:
            jobs = []
        filtered = [j for j in jobs if is_relevant(j["title"])]
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
    elif args.url:
        jobs = fetch_playwright(args.url, args.url.split("/")[2])
        print(json.dumps(jobs, ensure_ascii=False, indent=2))
    else:
        run_scan(max_results=args.max)