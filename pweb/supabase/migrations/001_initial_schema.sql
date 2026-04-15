-- ═══════════════════════════════════════════════════════════════════════════
-- 001_initial_schema.sql — mayk.dev Ecosystem
-- Base de datos para el Orquestador de Proyectos Web (pweb v4.0.0)
-- Compatible con: Supabase (PostgreSQL 15+)
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── Extensiones ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- índices de búsqueda de texto

-- ─── Limpieza Previa (Idempotencia) ──────────────────────────────────────────
DROP TYPE IF EXISTS tipo_proyecto_enum CASCADE;
DROP TYPE IF EXISTS estado_ejecucion_enum CASCADE;

-- ─── ENUM: tipos de proyecto soportados ──────────────────────────────────────
CREATE TYPE tipo_proyecto_enum AS ENUM (
    'landing-page',
    'e-commerce',
    'web-corporativa',
    'saas-dashboard',
    'blog-contenido',
    'portfolio',
    'sistema-crm-apis'
);

-- ─── ENUM: estados de ejecución ──────────────────────────────────────────────
CREATE TYPE estado_ejecucion_enum AS ENUM (
    'EN_PROCESO',
    'COMPLETADO',
    'ERROR'
);

-- ═══════════════════════════════════════════════════════════════════════════
-- TABLA 1: proyectos
-- Registro maestro de cada proyecto que entra por el orquestador.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS proyectos (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre            TEXT        NOT NULL,
    tipo              tipo_proyecto_enum NOT NULL,
    objetivo          TEXT        NOT NULL,
    url_existente     TEXT,
    stack_existente   TEXT,
    presupuesto       TEXT,
    integraciones     TEXT[]      DEFAULT '{}',  -- array de strings
    creado_en         TIMESTAMPTZ DEFAULT NOW(),
    actualizado_en    TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE proyectos IS 'Registro maestro de proyectos web gestionados por mayk.dev';
COMMENT ON COLUMN proyectos.integraciones IS 'Lista de integraciones requeridas (ej: stripe, supabase, whatsapp)';

-- ═══════════════════════════════════════════════════════════════════════════
-- TABLA 2: ejecuciones
-- Cada vez que el orquestador /proyecto/ejecutar procesa un proyecto.
-- Una misma proyecto puede tener múltiples ejecuciones (iteraciones/revisiones).
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ejecuciones (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    proyecto_id       UUID        NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    estado            estado_ejecucion_enum NOT NULL DEFAULT 'EN_PROCESO',

    -- Resultados de cada fase (texto completo de la respuesta del agente)
    fase_1_auditoria  TEXT,       -- NULL si no había proyecto previo
    fase_1_estrategia TEXT,
    fase_2_diseno     TEXT,
    fase_2_dev        TEXT,
    fase_3_qa         TEXT,

    -- Trazabilidad
    make_notificado   BOOLEAN     DEFAULT FALSE,
    duracion_ms       INTEGER,    -- tiempo total de ejecución en milisegundos
    iniciado_en       TIMESTAMPTZ DEFAULT NOW(),
    completado_en     TIMESTAMPTZ
);

COMMENT ON TABLE ejecuciones IS 'Ejecuciones del orquestador por proyecto. Cada ejecución almacena los outputs de los 5 agentes.';
COMMENT ON COLUMN ejecuciones.fase_1_auditoria IS 'Solo presente si el proyecto tiene url_existente o stack_existente';
COMMENT ON COLUMN ejecuciones.make_notificado IS 'TRUE si el batch fue enviado exitosamente a Make.com';

-- ═══════════════════════════════════════════════════════════════════════════
-- TABLA 3: make_webhooks_log
-- Historial de cada payload enviado a Make.com para auditoría y reenvíos.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS make_webhooks_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ejecucion_id    UUID        NOT NULL REFERENCES ejecuciones(id) ON DELETE CASCADE,
    payload         JSONB       NOT NULL,       -- copia exacta del JSON enviado
    enviado_ok      BOOLEAN     NOT NULL DEFAULT FALSE,
    http_status     INTEGER,
    error_msg       TEXT,
    enviado_en      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE make_webhooks_log IS 'Log de cada llamada batch a Make.com. Permite auditar y reenviar si falla.';

-- ═══════════════════════════════════════════════════════════════════════════
-- ÍNDICES para rendimiento
-- ═══════════════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_proyectos_tipo
    ON proyectos (tipo);

CREATE INDEX IF NOT EXISTS idx_proyectos_nombre_trgm
    ON proyectos USING GIN (nombre gin_trgm_ops);  -- búsqueda parcial por nombre

CREATE INDEX IF NOT EXISTS idx_ejecuciones_proyecto_id
    ON ejecuciones (proyecto_id);

CREATE INDEX IF NOT EXISTS idx_ejecuciones_estado
    ON ejecuciones (estado);

CREATE INDEX IF NOT EXISTS idx_ejecuciones_iniciado_en
    ON ejecuciones (iniciado_en DESC);

CREATE INDEX IF NOT EXISTS idx_make_log_ejecucion
    ON make_webhooks_log (ejecucion_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- TRIGGER: actualizar `actualizado_en` automáticamente en proyectos
-- ═══════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.actualizado_en = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_proyectos_updated_at
    BEFORE UPDATE ON proyectos
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_updated_at();

-- RLS desactivado temporalmente para permitir testeo inicial sin problemas de privilegios.

-- ═══════════════════════════════════════════════════════════════════════════
-- VISTA: resumen_proyectos — para consultas rápidas desde Make/Dashboard
-- ═══════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW resumen_proyectos AS
SELECT
    p.id,
    p.nombre,
    p.tipo,
    p.objetivo,
    COUNT(e.id)                                             AS total_ejecuciones,
    MAX(e.iniciado_en)                                      AS ultima_ejecucion,
    SUM(CASE WHEN e.estado = 'COMPLETADO' THEN 1 ELSE 0 END) AS ejecuciones_ok,
    SUM(CASE WHEN e.estado = 'ERROR'      THEN 1 ELSE 0 END) AS ejecuciones_error,
    p.creado_en
FROM proyectos p
LEFT JOIN ejecuciones e ON e.proyecto_id = p.id
GROUP BY p.id, p.nombre, p.tipo, p.objetivo, p.creado_en
ORDER BY p.creado_en DESC;

COMMENT ON VIEW resumen_proyectos IS 'Vista de dashboard: proyectos con sus métricas de ejecución agregadas.';
