#!/bin/bash
# 03_career_start.sh — Solo los servicios Career-Ops
set -e
GREEN='\033[92m'; CYAN='\033[96m'; RESET='\033[0m'
echo -e "${CYAN}=== Arrancando Career-Ops ===${RESET}"
docker-compose up -d agente-hr-evaluador agente-hr-sastre career-orchestrator
sleep 3

echo -e "${GREEN}Verificando agentes Career-Ops...${RESET}"
for port in 8011 8012 8020; do
    if curl -sf "http://localhost:${port}/health" > /dev/null; then
        echo -e "  ${GREEN}✔ Puerto ${port} OK${RESET}"
    else
        echo -e "  \033[91m✘ Puerto ${port} no responde${RESET}"
    fi
done

echo -e "\n${GREEN}Career-Ops listo. Usa mayk-cli.py desde Windows opcion 3.${RESET}"
echo -e "Test rapido: python career/scripts/eval_oferta.py --url [URL-OFERTA]"