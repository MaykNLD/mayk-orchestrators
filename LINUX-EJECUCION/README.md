# LINUX-EJECUCION — Guía de Despliegue en Linux (mayk-hp)

Esta carpeta contiene los scripts de configuración y arranque para ejecutar
el ecosistema mayk.dev en el servidor Linux (`mayk-hp`, IP Tailscale: `100.117.70.65`).

## Primer Despliegue (una sola vez)

```bash
bash LINUX-EJECUCION/01_setup.sh
```

Esto instala dependencias, configura el `.env` y levanta todos los contenedores.

## Arranque normal

```bash
bash LINUX-EJECUCION/02_start.sh
```

## Solo Career-Ops

```bash
bash LINUX-EJECUCION/03_career_start.sh
```

## Verificar estado

```bash
bash LINUX-EJECUCION/04_health_check.sh
```

## Notas de seguridad
- El archivo `.env` NUNCA se sube a GitHub (gitignored)
- Los puertos solo son accesibles desde la red Tailscale
- `career/output/` y `career/data/` son gitignored — los PDFs no se sincronizan