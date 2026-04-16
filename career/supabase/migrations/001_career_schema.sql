-- ============================================================
-- Career-Ops Schema v1.0 — mayk.dev
-- Ejecutar en Supabase SQL Editor
-- ============================================================

-- Extension necesaria para uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Perfil base del candidato (Master CV) ────────────────────
CREATE TABLE IF NOT EXISTS perfil_base (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nombre        TEXT NOT NULL,
  apellido      TEXT NOT NULL,
  email         TEXT,
  linkedin      TEXT,
  portfolio_url TEXT,
  datos_json    JSONB NOT NULL DEFAULT '{}',   -- CV estructurado completo
  idioma        TEXT NOT NULL DEFAULT 'ES',    -- ES | EN
  mercado       TEXT NOT NULL DEFAULT 'ES',    -- ES | EU | LATAM | US
  portals_config JSONB DEFAULT '{}',           -- config de portales del candidato
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Registro de candidaturas ────────────────────────────────
CREATE TABLE IF NOT EXISTS aplicaciones_career (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  perfil_id        UUID REFERENCES perfil_base(id) ON DELETE CASCADE,
  job_title        TEXT NOT NULL,
  company          TEXT NOT NULL,
  url              TEXT,
  portal_type      TEXT DEFAULT 'desconocido',  -- ashby | greenhouse | lever | bamboohr | custom
  status           TEXT NOT NULL DEFAULT 'pendiente',
  -- Estados canonicos (ver career/plantillas/estados.yml):
  -- pendiente | evaluando | cv_generado | aplicado | respondido | entrevista | oferta | aceptado | rechazado | descartado
  fit_score        FLOAT,                        -- 0.0 - 5.0
  grado            TEXT,                         -- A | B | C | D | F
  legitimacy       TEXT,                         -- High Confidence | Proceed with Caution | Suspicious
  raw_analysis     JSONB DEFAULT '{}',           -- Output completo agente-hr-evaluador (7 bloques)
  tailored_content JSONB DEFAULT '{}',           -- Output agente-hr-sastre (cv_adaptado_json)
  keywords         JSONB DEFAULT '[]',           -- Keywords ATS extraidas del JD
  pdf_url          TEXT,                         -- URL Supabase Storage
  notas            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── Historial del scanner (dedup) ───────────────────────────
CREATE TABLE IF NOT EXISTS scan_history (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  url         TEXT UNIQUE NOT NULL,
  portal      TEXT,       -- ashby | greenhouse | lever | custom
  company     TEXT,
  job_title   TEXT,
  status      TEXT,       -- added | skipped_dup | skipped_title | skipped_expired
  first_seen  DATE NOT NULL DEFAULT CURRENT_DATE
);

-- ── Log de ejecuciones del pipeline ─────────────────────────
CREATE TABLE IF NOT EXISTS career_ejecuciones (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  aplicacion_id  UUID REFERENCES aplicaciones_career(id) ON DELETE CASCADE,
  etapa          TEXT NOT NULL,  -- evaluacion | adaptacion | generacion_pdf | scan
  modelo_ia      TEXT,
  tokens_usados  INT,
  duracion_ms    INT,
  resultado      TEXT NOT NULL DEFAULT 'ok',  -- ok | error
  error_detalle  TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indices de rendimiento ───────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_aplicaciones_status    ON aplicaciones_career(status);
CREATE INDEX IF NOT EXISTS idx_aplicaciones_perfil    ON aplicaciones_career(perfil_id);
CREATE INDEX IF NOT EXISTS idx_aplicaciones_created   ON aplicaciones_career(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_history_url       ON scan_history(url);
CREATE INDEX IF NOT EXISTS idx_ejecuciones_aplicacion ON career_ejecuciones(aplicacion_id);

-- ── Row Level Security (RLS) ─────────────────────────────────
ALTER TABLE perfil_base           ENABLE ROW LEVEL SECURITY;
ALTER TABLE aplicaciones_career   ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_history          ENABLE ROW LEVEL SECURITY;
ALTER TABLE career_ejecuciones    ENABLE ROW LEVEL SECURITY;

-- Politica: acceso total autenticado (ajustar segun multi-tenant si es necesario)
CREATE POLICY "Acceso autenticado total" ON perfil_base
  FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Acceso autenticado total" ON aplicaciones_career
  FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Acceso autenticado total" ON scan_history
  FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY "Acceso autenticado total" ON career_ejecuciones
  FOR ALL USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');

-- ── Trigger: updated_at automatico ──────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_perfil_base_updated
  BEFORE UPDATE ON perfil_base FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_aplicaciones_updated
  BEFORE UPDATE ON aplicaciones_career FOR EACH ROW EXECUTE FUNCTION update_updated_at();