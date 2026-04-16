"""
generate_pdf.py — Genera PDF del CV adaptado usando Playwright
Compatible con Linux y Windows. Sin dependencias de GUI.

Uso: python generate_pdf.py --cv cv_adaptado.json --template ../plantillas/cv-template.html
"""
import argparse, json, os, sys, tempfile
from pathlib import Path
from datetime import datetime

def render_cv_html(cv_json: dict, template_path: str, idioma: str = "ES") -> str:
    """Rellena el template HTML con los datos del CV adaptado."""
    tmpl = Path(template_path).read_text(encoding="utf-8")

    exp_html = ""
    for job in cv_json.get("experiencia", []):
        logros = "".join(f"<li>{l}</li>" for l in job.get("logros", []))
        exp_html += f"""
        <div class="experience-item">
          <div class="exp-header">
            <span class="company">{job.get("empresa","")}</span>
            <span class="period">{job.get("periodo","")}</span>
          </div>
          <div class="role">{job.get("rol","")}</div>
          <p>{job.get("descripcion_adaptada","")}</p>
          <ul>{logros}</ul>
        </div>"""

    proj_html = ""
    for proj in cv_json.get("proyectos", []):
        techs = ", ".join(proj.get("tecnologias", []))
        url_tag = f'<a href="{proj["url"]}">{proj["url"]}</a>' if proj.get("url") else ""
        proj_html += f"""
        <div class="project-item">
          <strong>{proj.get("nombre","")}</strong> — {techs} {url_tag}
          <p>{proj.get("descripcion_adaptada","")}</p>
        </div>"""

    skills = cv_json.get("skills", {})
    skills_html = " · ".join(skills.get("principales", []) + skills.get("secundarias", []))

    edu_html = ""
    for edu in cv_json.get("educacion", []):
        edu_html += f"<div><strong>{edu.get('titulo','')}</strong> — {edu.get('institucion','')} ({edu.get('año','')})</div>"

    filled = (tmpl
        .replace("{{RESUMEN}}", cv_json.get("resumen", ""))
        .replace("{{EXPERIENCIA}}", exp_html)
        .replace("{{PROYECTOS}}", proj_html)
        .replace("{{SKILLS}}", skills_html)
        .replace("{{EDUCACION}}", edu_html)
        .replace("{{FECHA}}", datetime.now().strftime("%Y-%m"))
    )
    return filled

def generate_pdf(cv_json: dict, template_path: str, output_path: str, idioma: str = "ES") -> str:
    """Genera un PDF a partir del CV JSON y el template HTML."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright no instalado. Ejecuta: pip install playwright && playwright install chromium")
        sys.exit(1)

    html_content = render_cv_html(cv_json, template_path, idioma)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        tmp_html = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{tmp_html}")
            page.wait_for_timeout(500)
            page.pdf(path=output_path, format="A4", margin={
                "top": "15mm", "bottom": "15mm", "left": "12mm", "right": "12mm"
            }, print_background=True)
            browser.close()
    finally:
        os.unlink(tmp_html)

    print(f"PDF generado: {output_path}")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv", required=True, help="JSON file con el CV adaptado")
    parser.add_argument("--template", default="../plantillas/cv-template.html")
    parser.add_argument("--output", default=None)
    parser.add_argument("--idioma", default="ES")
    args = parser.parse_args()

    cv_data = json.loads(Path(args.cv).read_text(encoding="utf-8"))
    out = args.output or f"../output/cv-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    generate_pdf(cv_data, args.template, out, args.idioma)