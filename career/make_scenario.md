# Make.com — Escenario Career-Ops

## Propósito
Recibir notificaciones en Telegram cuando:
- Una oferta supera el umbral de score (fit_score >= 3.0)
- El CV adaptado ha sido generado correctamente
- El scanner encuentra nuevas ofertas relevantes

## Estructura del escenario (1 webhook → 1 Telegram)

```
[Webhook: career-notify] → [Router] → [Telegram: Bot mayk.dev]
```

El `career/main.py` ya llama a `MAKE_WEBHOOK_URL` automáticamente en cada evaluación.

## Configuración en Make.com

### Paso 1 — Crear el escenario
1. make.com → Create a new scenario
2. Primer módulo: **Webhooks → Custom Webhook**
3. Click "Add" → nombrar: `career-notify` → Copy webhook URL
4. Pegar esa URL en tu `.env` como `MAKE_WEBHOOK_URL`

### Paso 2 — Conectar Telegram
1. Segundo módulo: **Telegram Bot → Send a Text Message**
2. Conectar tu bot (usa el token de @BotFather)
3. Chat ID: tu ID personal (consíguelo con @userinfobot)

### Paso 3 — Formatear el mensaje
En el campo "Text" del módulo Telegram, usa este template:

```
💼 *Nueva Candidatura Career-Ops*

🏢 Empresa: {{company}}
📋 Rol: {{role}}
📊 Score: {{score}}/5 (Grado {{grado}})
✅ Estado: {{status}}

{{mensaje}}
```

### Paso 4 — Activar el escenario
- Scheduling: **Instantly** (se activa con cada webhook)
- Guardar y hacer clic en **ON**

## Payload que envía career/main.py

```json
{
  "company": "Factorial",
  "role": "Backend Developer",
  "score": 4.2,
  "grado": "B",
  "status": "cv_generado",
  "mensaje": "CV adaptado generado. PDF disponible en /app/output/"
}
```

## Variables de entorno necesarias
```bash
MAKE_WEBHOOK_URL=https://hook.eu2.make.com/xxxxxxxxxxxx
```
Esta variable ya está en `career/.env.example` y en `docker-compose.yml`.