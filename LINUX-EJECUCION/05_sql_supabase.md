# SQL Career-Ops para Supabase
# Pega esto en: supabase.com → SQL Editor → New Query → Run

## PASO 1 — Crear tablas Career-Ops (NO toca las tablas existentes)

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS perfil_base (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nombre        TEXT NOT NULL,
  apellido      TEXT NOT NULL,
  email         TEXT,
  linkedin      TEXT,
  portfolio_url TEXT,
  datos_json    JSONB NOT NULL DEFAULT '{}',
  idioma        TEXT NOT NULL DEFAULT 'ES',
  mercado       TEXT NOT NULL DEFAULT 'ES',
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aplicaciones_career (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  perfil_id        UUID REFERENCES perfil_base(id) ON DELETE CASCADE,
  job_title        TEXT NOT NULL,
  company          TEXT NOT NULL,
  url              TEXT,
  portal_type      TEXT DEFAULT 'desconocido',
  status           TEXT NOT NULL DEFAULT 'pendiente',
  fit_score        FLOAT,
  grado            TEXT,
  legitimacy       TEXT,
  raw_analysis     JSONB DEFAULT '{}',
  tailored_content JSONB DEFAULT '{}',
  keywords         JSONB DEFAULT '[]',
  pdf_url          TEXT,
  notas            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scan_history (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  url        TEXT UNIQUE NOT NULL,
  portal     TEXT,
  company    TEXT,
  job_title  TEXT,
  status     TEXT,
  first_seen DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS career_ejecuciones (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  aplicacion_id UUID REFERENCES aplicaciones_career(id) ON DELETE CASCADE,
  etapa         TEXT NOT NULL,
  modelo_ia     TEXT,
  tokens_usados INT,
  duracion_ms   INT,
  resultado     TEXT NOT NULL DEFAULT 'ok',
  error_detalle TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aplicaciones_status  ON aplicaciones_career(status);
CREATE INDEX IF NOT EXISTS idx_aplicaciones_perfil  ON aplicaciones_career(perfil_id);
CREATE INDEX IF NOT EXISTS idx_aplicaciones_created ON aplicaciones_career(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_history_url     ON scan_history(url);

ALTER TABLE perfil_base         ENABLE ROW LEVEL SECURITY;
ALTER TABLE aplicaciones_career ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_history        ENABLE ROW LEVEL SECURITY;
ALTER TABLE career_ejecuciones  ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='perfil_base' AND policyname='service_role_all') THEN
    CREATE POLICY "service_role_all" ON perfil_base FOR ALL USING (auth.role() IN ('service_role','authenticated'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='aplicaciones_career' AND policyname='service_role_all') THEN
    CREATE POLICY "service_role_all" ON aplicaciones_career FOR ALL USING (auth.role() IN ('service_role','authenticated'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='scan_history' AND policyname='service_role_all') THEN
    CREATE POLICY "service_role_all" ON scan_history FOR ALL USING (auth.role() IN ('service_role','authenticated'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='career_ejecuciones' AND policyname='service_role_all') THEN
    CREATE POLICY "service_role_all" ON career_ejecuciones FOR ALL USING (auth.role() IN ('service_role','authenticated'));
  END IF;
END $$;

CREATE OR REPLACE FUNCTION update_career_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_perfil_updated ON perfil_base;
CREATE TRIGGER trg_perfil_updated
  BEFORE UPDATE ON perfil_base FOR EACH ROW EXECUTE FUNCTION update_career_updated_at();

DROP TRIGGER IF EXISTS trg_aplicaciones_updated ON aplicaciones_career;
CREATE TRIGGER trg_aplicaciones_updated
  BEFORE UPDATE ON aplicaciones_career FOR EACH ROW EXECUTE FUNCTION update_career_updated_at();
```

## PASO 2 — Insertar tu perfil base
> ⚠️ Edita `email` y `linkedin` con tus datos reales antes de ejecutar.

```sql
INSERT INTO perfil_base (nombre, apellido, email, linkedin, portfolio_url, idioma, mercado, datos_json)
VALUES (
  'Michael',
  'Lascano',
  'TU_EMAIL_AQUI',
  'TU_LINKEDIN_AQUI',
  'https://github.com/MaykNLD',
  'ES',
  'ES',
  '{
    "titular": "Full Stack Developer — Python · Java · AI Systems",
    "resumen": "Desarrollador Full Stack con experiencia en sistemas de IA distribuidos y microservicios FastAPI. Construyo ecosistemas de agentes inteligentes con Supabase, Docker, OpenRouter y Tailscale.",
    "experiencia": [
      {
        "empresa": "mayk.dev (Proyecto Propio)",
        "rol": "Full Stack Developer",
        "periodo": "2026 - Presente",
        "descripcion_adaptada": "Ecosistema de agentes IA especializados: orquestadores FastAPI, pipeline multi-agente con OpenRouter, infraestructura Docker + Tailscale, Supabase y Make.com.",
        "logros": [
          "5+ agentes IA especializados (Auditor, Estratega, Visual, Dev, QA-Ops)",
          "Módulo Career-Ops: evaluación de ofertas A-F, CV ATS-optimizado, PDF automático",
          "CI/CD via GitHub Actions + deploy automático via Tailscale a VPS Linux"
        ]
      }
    ],
    "proyectos": [
      {
        "nombre": "mayk-agents + mayk-orchestrators",
        "descripcion_adaptada": "Ecosistema de microservicios IA: agentes FastAPI especializados, LLMs via OpenRouter, Supabase, Docker Compose, red segura Tailscale, CLI multiplataforma.",
        "tecnologias": ["Python", "FastAPI", "Docker", "Supabase", "OpenRouter", "Tailscale", "GitHub Actions"],
        "url": "https://github.com/MaykNLD"
      },
      {
        "nombre": "AI Career Showcase V4",
        "descripcion_adaptada": "Pipeline de 5 agentes IA secuenciales para búsqueda de empleo: CV técnico, diseño visual HTML/CSS, análisis de mercado, despliegue y feedback delta.",
        "tecnologias": ["Python", "IA Agents", "HTML/CSS", "JSON handoff"],
        "url": "https://github.com/MaykNLD/AI_Career_Showcase"
      },
      {
        "nombre": "Seora CRM MongoDB",
        "descripcion_adaptada": "CRM para instrumentos musicales con Hybrid Storage Adapter (MongoDB + JSON fallback), despliegue Docker.",
        "tecnologias": ["Python", "MongoDB", "Docker", "REST API"],
        "url": "https://github.com/MaykNLD/seora-crm-mongodb"
      },
      {
        "nombre": "App Planning (Android)",
        "descripcion_adaptada": "App Android con Firebase: CRUD completo, autenticación de usuarios, arquitectura MVC, seguridad R8/ProGuard.",
        "tecnologias": ["Java", "Android", "Firebase", "MVC"],
        "url": "https://github.com/MaykNLD/App_Planning"
      }
    ],
    "skills": {
      "principales": ["Python", "FastAPI", "Docker", "Supabase", "Java", "Android"],
      "secundarias": ["GitHub Actions", "Tailscale", "Make.com", "Playwright", "OpenRouter", "MongoDB", "PostgreSQL"],
      "idiomas": ["Español (nativo)", "Inglés (B2)"]
    },
    "educacion": [
      {
        "titulo": "Desarrollo de Aplicaciones Multiplataforma (DAM)",
        "institucion": "EDITAR con tu instituto",
        "año": "2026"
      }
    ],
    "roles_objetivo": ["Full Stack Developer", "Backend Developer", "Python Developer"],
    "nivel": "Junior",
    "modalidad": "Remoto / Híbrido",
    "mercados": ["España", "Europa (remoto)"]
  }'
);
```

## PASO 3 — Verificar

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('perfil_base','aplicaciones_career','scan_history','career_ejecuciones');

SELECT id, nombre, apellido, idioma, mercado FROM perfil_base;
```

## Instrucciones
1. `supabase.com` → tu proyecto → **SQL Editor** → **New Query**
2. Pega PASO 1 → Run
3. Edita email, linkedin e instituto → Pega PASO 2 → Run
4. Pega PASO 3 → Run para confirmar