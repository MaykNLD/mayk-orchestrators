#!/bin/bash
# 01_setup.sh — Primer despliegue completo en Linux (mayk-hp)
# Ejecutar: bash LINUX-EJECUCION/01_setup.sh
set -e

CYAN='\033[96m'; GREEN='\033[92m'; YELLOW='\033[93m'; RED='\033[91m'; RESET='\033[0m'

echo -e "${CYAN}=== mayk.dev — Setup Inicial Linux ===${RESET}"

# 1. Verificar Tailscale
echo -e "${CYAN}[1/6] Verificando Tailscale...${RESET}"
if tailscale status | grep -q "100\."; then
    echo -e "  ${GREEN}✔ Tailscale activo${RESET}"
else
    echo -e "  ${YELLOW}⚠ Tailscale no parece estar conectado. Verifica con 'tailscale up'${RESET}"
fi

# 2. Verificar Docker
echo -e "${CYAN}[2/6] Verificando Docker...${RESET}"
docker --version && docker-compose --version
echo -e "  ${GREEN}✔ Docker disponible${RESET}"

# 3. Crear .env si no existe
echo -e "${CYAN}[3/6] Configurando .env...${RESET}"
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "  ${YELLOW}⚠ .env creado desde .env.example${RESET}"
    echo -e "  ${YELLOW}  EDITA los valores antes de continuar:${RESET}"
    echo -e "  ${YELLOW}  nano .env${RESET}"
    echo -e "\n  Pulsa ENTER cuando hayas rellenado el .env..."
    read
else
    echo -e "  ${GREEN}✔ .env ya existe${RESET}"
fi

# 4. Crear carpetas de datos (gitignored)
echo -e "${CYAN}[4/6] Creando carpetas de datos...${RESET}"
mkdir -p career/output career/data career/perfiles-candidatos
echo -e "  ${GREEN}✔ Carpetas creadas${RESET}"

# 5. Instalar Playwright Chromium (para PDF)
echo -e "${CYAN}[5/6] Instalando Playwright Chromium...${RESET}"
pip install playwright --quiet
playwright install chromium
echo -e "  ${GREEN}✔ Chromium instalado${RESET}"

# 6. Levantar todos los contenedores
echo -e "${CYAN}[6/6] Levantando contenedores...${RESET}"
docker-compose up -d --build
sleep 5

echo -e "\n${GREEN}=== Setup completo ===${RESET}"
bash LINUX-EJECUCION/04_health_check.sh