#!/bin/bash
# mayk-cli.sh — Interfaz mayk.dev para Linux
# Versión 2.0 — Incluye módulo Career-Ops

ORCHESTRATOR="http://127.0.0.1:8000"
CAREER_URL="http://127.0.0.1:8020"

CYAN='\033[96m'; GREEN='\033[92m'; YELLOW='\033[93m'
RED='\033[91m'; BOLD='\033[1m'; RESET='\033[0m'; MAGENTA='\033[95m'

header() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "  ██████████████████████████████████████████████"
    echo "  ██                                          ██"
    echo "  ██        mayk.dev — Orquestador IA        ██"
    echo "  ██                  [Linux]                 ██"
    echo "  ██████████████████████████████████████████████"
    echo -e "${RESET}"
}

check_health() {
    if curl -sf "${ORCHESTRATOR}/health" > /dev/null 2>&1; then
        V=$(curl -sf "${ORCHESTRATOR}/health" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('version','?'))" 2>/dev/null)
        echo -e "  ${GREEN}✔ Orquestador principal${RESET} v${V}"
    else
        echo -e "  ${RED}✘ Orquestador no responde en ${ORCHESTRATOR}${RESET}"
    fi
    echo ""
}

enviar() {
    local endpoint=$1; local payload=$2; local base=${3:-$ORCHESTRATOR}
    echo -e "\n  ${YELLOW}Enviando... (puede tardar 1-3 min)${RESET}\n"
    curl -sf -X POST "${base}${endpoint}" \
         -H "Content-Type: application/json" \
         -d "$payload" \
         --max-time 300 | python3 -c "
import sys,json,textwrap
d=json.load(sys.stdin)
for k,v in d.items():
    if v and str(v).lower() not in ['none','false','']:
        print(f'  ── \033[96m{k}\033[0m')
        for l in textwrap.wrap(str(v),80): print(f'     {l}')
        print()
" 2>/dev/null || echo -e "  ${RED}Error de conexión${RESET}"
}

# ── CAREER-OPS ──────────────────────────────────────────────────

career_health() {
    if curl -sf "${CAREER_URL}/health" > /dev/null 2>&1; then
        V=$(curl -sf "${CAREER_URL}/health" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('version','?'))" 2>/dev/null)
        AGENTS=$(curl -sf "${CAREER_URL}/health" | python3 -c "import sys,json;d=json.load(sys.stdin);a=d.get('agents',{});print('Evaluador:'+('✔' if a.get('evaluador')=='ok' else '✘')+' Sastre:'+('✔' if a.get('sastre')=='ok' else '✘'))" 2>/dev/null)
        echo -e "  ${GREEN}✔ Career-Ops${RESET} v${V} | ${AGENTS}"
    else
        echo -e "  ${RED}✘ Career-Ops no responde en ${CAREER_URL}${RESET}"
        echo -e "  ${YELLOW}  Ejecuta: bash LINUX-EJECUCION/03_career_start.sh${RESET}"
    fi
}

career_evaluar() {
    echo -e "${BOLD}${MAGENTA}── Evaluar Oferta ───────────────────────────────────────────${RESET}\n"
    echo "  ¿Cómo introduces la oferta?"
    echo "    1) URL de la oferta"
    echo "    2) Pegar texto de la JD"
    read -p "  Elige [1-2]: " modo; echo ""

    if [ "$modo" = "1" ]; then
        read -p "  URL de la oferta: " url
        PAYLOAD="{\"url_oferta\":\"${url}\",\"idioma\":\"ES\"}"
    else
        echo "  Pega el texto (termina con FIN en línea nueva):"
        texto=""
        while IFS= read -r line; do
            [ "$line" = "FIN" ] && break
            texto="${texto}${line}\n"
        done
        texto_escaped=$(echo -e "$texto" | python3 -c "import sys,json;print(json.dumps(sys.stdin.read()))")
        PAYLOAD="{\"texto_oferta\":${texto_escaped},\"idioma\":\"ES\"}"
    fi

    RESP=$(curl -sf -X POST "${CAREER_URL}/career/evaluar" \
                -H "Content-Type: application/json" -d "$PAYLOAD" --max-time 180 2>/dev/null)
    if [ -n "$RESP" ]; then
        echo "$RESP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
score=d.get('fit_score',0); grado=d.get('grado','?')
rec=d.get('recomendacion','?'); estado=d.get('estado','?')
color='\033[92m' if grado in ['A','B'] else '\033[93m' if grado=='C' else '\033[91m'
print(f'\n  \033[1mScore: {color}{score}/5 ({grado})\033[0m')
print(f'  Recomendación: {rec}')
print(f'  Estado: {estado}')
if d.get('mensaje'): print(f'  \033[96m{d[\"mensaje\"]}\033[0m')
" 2>/dev/null
    else
        echo -e "  ${RED}Error al conectar con Career-Ops${RESET}"
    fi
}

career_tracker() {
    echo -e "\n${BOLD}  Candidaturas registradas:${RESET}"
    RESP=$(curl -sf "${CAREER_URL}/career/tracker" 2>/dev/null)
    if [ -n "$RESP" ]; then
        echo "$RESP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
apps=d.get('aplicaciones',[])
print(f'  Total: {d.get(\"total\",0)}\n')
print(f'  {\"#\":<4} {\"Empresa\":<20} {\"Rol\":<25} {\"Score\":<7} {\"Grado\":<6} Status')
print('  ' + '-'*75)
for i,a in enumerate(apps[:15],1):
    score=str(a.get('fit_score','-')) if a.get('fit_score') else '-'
    print(f'  {i:<4} {a.get(\"company\",\"?\"):<20} {a.get(\"job_title\",\"?\"):<25} {score:<7} {a.get(\"grado\",\"-\"):<6} {a.get(\"status\",\"-\")}')
" 2>/dev/null
    else
        echo -e "  ${RED}No se pudo contactar con Career-Ops${RESET}"
    fi
}

career_scan() {
    echo -e "\n${CYAN}  Lanzando scanner desde servidor local...${RESET}"
    cd "$(dirname "$0")/.." && python3 career/scripts/eval_oferta.py --help 2>/dev/null || \
    echo -e "  ${YELLOW}Ejecuta directamente: python3 career/scripts/eval_oferta.py --url [URL]${RESET}"
}

menu_career() {
    while true; do
        echo -e "\n${BOLD}${MAGENTA}── Búsqueda de Trabajo (Career-Ops) ─────────────────────────${RESET}\n"
        career_health; echo ""
        echo "    1) 🔍  Evaluar una oferta (URL o texto)"
        echo "    2) 📊  Ver tracker de candidaturas"
        echo "    3) 🌐  Escanear portales (local)"
        echo "    4) 🔙  Volver al menú principal"
        echo ""
        read -p "  Opción [1-4]: " op; echo ""
        case $op in
            1) career_evaluar ;;
            2) career_tracker ;;
            3) career_scan ;;
            4) break ;;
            *) echo -e "  ${RED}Opción no válida${RESET}" ;;
        esac
        read -p "  Pulsa Enter para continuar..."
    done
}

salud_agentes() {
    echo -e "\n${BOLD}  Estado de los agentes:${RESET}"
    bash LINUX-EJECUCION/04_health_check.sh 2>/dev/null || \
    echo -e "  ${YELLOW}Ejecuta: bash LINUX-EJECUCION/04_health_check.sh${RESET}"
    echo ""
}

# ─── MENÚ PRINCIPAL ─────────────────────────────────────────────
while true; do
    header; check_health
    echo -e "${BOLD}  ¿Qué quieres hacer?${RESET}\n"
    echo "    1) 🌐  Nuevo proyecto web"
    echo "    2) 📱  Nuevo proyecto app móvil"
    echo "    3) 💼  Búsqueda de trabajo (Career-Ops)"
    echo "    4) 🔍  Ver estado de los agentes"
    echo "    5) 🚪  Salir"
    echo ""
    read -p "  Opción [1-5]: " opcion; echo ""

    case $opcion in
        1)
            read -p "  Nombre del proyecto: " nombre
            read -p "  Objetivo: " objetivo
            PAYLOAD="{\"nombre_proyecto\":\"${nombre}\",\"tipo_proyecto\":\"web\",\"objetivo\":\"${objetivo}\",\"notify_make\":true}"
            enviar "/proyecto/ejecutar" "$PAYLOAD"
            ;;
        2)
            read -p "  Nombre de la app: " nombre
            read -p "  Objetivo: " objetivo
            PAYLOAD="{\"nombre_proyecto\":\"${nombre}\",\"tipo_proyecto\":\"app-movil\",\"objetivo\":\"${objetivo}\",\"notify_make\":true}"
            enviar "/proyecto/ejecutar" "$PAYLOAD"
            ;;
        3) menu_career ;;
        4) salud_agentes ;;
        5) echo -e "  ${CYAN}Hasta luego.${RESET}"; exit 0 ;;
        *) echo -e "  ${RED}Opción no válida${RESET}" ;;
    esac
    [ "$opcion" != "3" ] && read -p "  Pulsa Enter para volver al menú..."
done