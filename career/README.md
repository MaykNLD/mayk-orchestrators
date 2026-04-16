# 💼 Career-Ops — Orquestador de Busqueda de Empleo

Modulo del ecosistema **mayk.dev** para automatizar la busqueda de trabajo:
evaluacion de ofertas con scoring A-F, adaptacion de CV para ATS,
generacion de PDF y seguimiento de candidaturas.

## Inicio rapido

**Windows** (interfaz principal):
```powershell
python RUN/windows/mayk-cli.py
# → Opcion 3: Busqueda de trabajo
```

**Linux** (servidor):
```bash
bash RUN/linux/mayk-cli.sh
```

## Comandos del orquestador

| Comando | Accion |
|---|---|
| Pegar URL/texto JD | Pipeline completo automatico |
| `EVALUAR [url]` | Solo evaluacion A-G |
| `SCAN` | Escanear portales de empleo |
| `TRACKER` | Ver estado de candidaturas |
| `PDF` | Regenerar PDF del ultimo CV |
| `FBK` | Diagnostico de rechazos |

## Arquitectura

```
mayk-cli.py → POST /career/ejecutar (puerto 8020, Tailscale)
    → agente-hr-evaluador (8011) → scoring A-F
    → agente-hr-sastre (8012) → CV adaptado
    → generate_pdf.py → PDF
    → Supabase → registro + storage
    → Make webhook → Telegram (notificacion)
```

## Seguridad

- Todo el trafico va por **Tailscale** (IP 100.117.70.65)
- En **Windows**: nunca se escriben credenciales en disco
- En **Linux**: `.env` local gitignored
- `data/`, `output/`, `perfiles-candidatos/` son gitignored