#!/bin/bash
# 04_health_check.sh — Verifica el estado de todos los servicios
GREEN='\033[92m'; RED='\033[91m'; CYAN='\033[96m'; RESET='\033[0m'
echo -e "${CYAN}=== Health Check mayk.dev ===${RESET}\n"

declare -A SERVICES=(
    ["pweb-orchestrator"]="8000"
    ["agente-auditor"]="8001"
    ["agente-estratega"]="8002"
    ["agente-visual"]="8003"
    ["agente-dev"]="8004"
    ["agente-qa-ops"]="8005"
    ["agente-hr-evaluador"]="8011"
    ["agente-hr-sastre"]="8012"
    ["career-orchestrator"]="8020"
)

for name in "${!SERVICES[@]}"; do
    port="${SERVICES[$name]}"
    if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✔${RESET} ${name} (${port})"
    else
        echo -e "  ${RED}✘${RESET} ${name} (${port}) — offline"
    fi
done

echo -e "\n${CYAN}Tailscale IP:${RESET}"
tailscale ip -4 2>/dev/null || echo "  (tailscale no disponible)"