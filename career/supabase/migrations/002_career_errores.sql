-- Migración 002: Tabla de errores críticos del pipeline Career-Ops
-- Propósito: Persistir errores graves (saturación LLM, PDF, Supabase) para
--            posterior análisis y notificación por Telegram en futuras fases.

CREATE TABLE IF NOT EXISTS career_errores (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context     TEXT        NOT NULL,               -- Ej: "run_sastre_background", "evaluar_endpoint"
    error       TEXT        NOT NULL,               -- Mensaje de error (truncado a 2000 chars)
    app_id      UUID        REFERENCES aplicaciones_career(id) ON DELETE SET NULL,
    extra       JSONB       NOT NULL DEFAULT '{}'   -- Datos adicionales de contexto
);

-- Índice para consultas por fecha y contexto
CREATE INDEX IF NOT EXISTS idx_career_errores_created_at ON career_errores (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_career_errores_context     ON career_errores (context);

-- RLS: Solo el service_role puede escribir y leer (nunca el anon key)
ALTER TABLE career_errores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Solo service_role puede gestionar errores"
    ON career_errores
    FOR ALL
    USING (auth.role() = 'service_role');

COMMENT ON TABLE career_errores IS
    'Registro de errores criticos del pipeline Career-Ops. Usado para alertas Telegram y auditoria.';
