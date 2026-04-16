#!/bin/bash
# 02_start.sh — Arranque normal de todos los servicios
set -e
GREEN='\033[92m'; CYAN='\033[96m'; RESET='\033[0m'
echo -e "${CYAN}=== Arrancando mayk.dev ===${RESET}"
docker-compose up -d
sleep 3
echo -e "${GREEN}✔ Todos los servicios arrancados${RESET}"
bash LINUX-EJECUCION/04_health_check.sh