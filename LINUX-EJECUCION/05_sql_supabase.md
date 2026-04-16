# SQL Career-Ops para Supabase
# Pega esto en: supabase.com → SQL Editor → New Query → Run

## PASO 1 — Ejecutar en SQL Editor

```sql
-- ============================================================
-- Career-Ops Schema — Añade tablas a tu Supabase existente
-- NO modifica: proyectos, ejecuciones, make_webhooks_log, resumen_proyectos
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Perfil base del candidato (Master CV)
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

-- Registro de candidaturas
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

-- Historial scanner (dedup)
CREATE TABLE IF NOT EXISTS scan_history (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  url        TEXT UNIQUE NOT NULL,
  portal     TEXT,
  company    TEXT,
  job_title  TEXT,
  status     TEXT,
  first_seen DATE NOT NULL DEFAULT CURRENT_DATE
);

-- Log de ejecuciones career
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

-- RLS
ALTER TABLE perfil_base         ENABLE ROW LEVEL SECURITY;
ALTER TABLE aplicaciones_career ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_history        ENABLE ROW LEVEL SECURITY;
ALTER TABLE career_ejecuciones  ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "service_role_all" ON perfil_base
  FOR ALL USING (auth.role() IN ('service_role','authenticated'));
CREATE POLICY IF NOT EXISTS "service_role_all" ON aplicaciones_career
  FOR ALL USING (auth.role() IN ('service_role','authenticated'));
CREATE POLICY IF NOT EXISTS "service_role_all" ON scan_history
  FOR ALL USING (auth.role() IN ('service_role','authenticated'));
CREATE POLICY IF NOT EXISTS "service_role_all" ON career_ejecuciones
  FOR ALL USING (auth.role() IN ('service_role','authenticated'));

-- Trigger updated_at
CREATE OR REPLACE FUNCTION update_career_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_perfil_updated
  BEFORE UPDATE ON perfil_base FOR EACH ROW EXECUTE FUNCTION update_career_updated_at();
CREATE TRIGGER trg_aplicaciones_updated
  BEFORE UPDATE ON aplicaciones_career FOR EACH ROW EXECUTE FUNCTION update_career_updated_at();
```

## PASO 2 — Insertar tu perfil base (ejecutar después del PASO 1)

```sql
INSERT INTO perfil_base (nombre, apellido, email, linkedin, portfolio_url, idioma, mercado, datos_json)
VALUES (
  'Michael',
  'Lascano',
  '',
  'https://linkedin.com/in/michael-lascano',
  'https://github.com/MaykNLD',
  'ES',
  'ES',
  '{
    "titular": "Full Stack Developer — Python · Java · AI Systems",
    "resumen": "Desarrollador Full Stack con experiencia en sistemas de IA distribuidos, microservicios FastAPI y arquitecturas event-driven. Construyo ecosistemas de agentes inteligentes sobre Supabase, Docker y OpenRouter. Proyectos reales en producción con Tailscale, GitHub Actions y Make.com.",
    "experiencia": [
      {
        "empresa": "mayk.dev (Proyecto Propio)",
        "rol": "Full Stack Developer & AI Systems Architect",
        "periodo": "2026 - Presente",
        "descripcion_adaptada": "Diseño e implementación de un ecosistema de agentes IA especializados: orquestadores FastAPI (Python), pipeline multi-agente con OpenRouter, infraestructura Docker + Tailscale VPN, integración Supabase y automatización Make.com + Telegram.",
        "logros": [
          "Ecosistema de 5+ agentes IA especializados (Auditor, Estratega, Visual, Dev, QA-Ops, HR)",
          "Pipeline Career-Ops: evaluación de ofertas A-F con scoring 7 bloques y generación de CV ATS-optimizado",
          "Zero-trace Docker en Windows: secrets solo en memoria de sesión PowerShell",
          "CI/CD via GitHub Actions + deploy automático via Tailscale a VPS Linux"
        ]
      }
    ],
    "proyectos": [
      {
        "nombre": "mayk-agents + mayk-orchestrators",
        "descripcion_adaptada": "Ecosistema de microservicios IA: orquestadores FastAPI, agentes especializados con LLMs via OpenRouter, base de datos Supabase, Docker Compose, red segura Tailscale. CLI multiplataforma (Python/Bash).",
        "tecnologias": ["Python", "FastAPI", "Docker", "Supabase", "OpenRouter", "Tailscale", "GitHub Actions"],
        "url": "https://github.com/MaykNLD"
      },
      {
        "nombre": "Seora CRM MongoDB",
        "descripcion_adaptada": "CRM premium para instrumentos musicales con MongoDB. Implementa Hybrid Storage Adapter (MongoDB + JSON fallback), autenticación segura y despliegue containerizado.",
        "tecnologias": ["Python", "MongoDB", "Docker", "REST API"],
        "url": "https://github.com/MaykNLD/seora-crm-mongodb"
      },
      {
        "nombre": "App Planning (Android)",
        "descripcion_adaptada": "App Android con Firebase: CRUD completo, autenticación de usuarios, arquitectura MVC, seguridad R8/ProGuard.",
        "tecnologias": ["Java", "Android", "Firebase", "MVC"],
        "url": "https://github.com/MaykNLD/App_Planning"
      },
      {
        "nombre": "API Entrenamiento Fitness",
        "descripcion_adaptada": "API REST de entrenamiento fitness con gestión de rutinas, usuarios y progreso.",
        "tecnologias": ["Python", "REST API", "FastAPI"],
        "url": "https://github.com/MaykNLD/API-Entrenamiento-Fitness"
      }
    ],
    "skills": {
      "principales": ["Python", "FastAPI", "Docker", "Supabase", "Java", "Android", "JavaScript", "REST APIs"],
      "secundarias": ["GitHub Actions", "Tailscale", "Make.com", "Playwright", "OpenRouter", "MongoDB", "PostgreSQL", "Kotlin"],
      "idiomas": ["Español (nativo)", "Inglés (B2)"]
    },
    "educacion": [
      {
        "titulo": "Desarrollo de Aplicaciones Multiplataforma (DAM)",
        "institucion": "Instituto",
        "año": "2026"
      }
    ],
    "roles_objetivo": ["Full Stack Developer", "Backend Developer", "Python Developer", "AI/ML Engineer"],
    "nivel": "Junior-Mid",
    "salario_objetivo": "22000-30000 EUR",
    "modalidad": "Remoto / Híbrido",
    "mercados": ["España", "Europa (remoto)"]
  }'
);
```

## PASO 3 — Verificar que todo está correcto

```sql
-- Ver las 4 tablas nuevas
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN
('perfil_base','aplicaciones_career','scan_history','career_ejecuciones');

-- Ver tu perfil
SELECT id, nombre, apellido, idioma, mercado FROM perfil_base;
```

## ¿Dónde ejecutar?
1. Abre https://supabase.com → tu proyecto
2. Menú izquierdo → **SQL Editor**
3. **New Query**
4. Pega el PASO 1 → Run
5. Pega el PASO 2 → Run (puede que necesites editar email y linkedin)
6. Pega el PASO 3 → Run para verificar