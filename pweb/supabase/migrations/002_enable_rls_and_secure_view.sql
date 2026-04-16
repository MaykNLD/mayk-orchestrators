-- 002_enable_rls_and_secure_view.sql
-- Aseguriza las tablas y la vista para que desaparezca la advertencia "UNRESTRICTED"

-- 1. Activar Row Level Security (RLS) en todas las tablas
ALTER TABLE proyectos ENABLE ROW LEVEL SECURITY;
ALTER TABLE ejecuciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE make_webhooks_log ENABLE ROW LEVEL SECURITY;

-- Nota: Como nuestro Orquestador usa la `SUPABASE_SECRET` (Service Role Key),
-- esto NO bloqueará la API del orquestador (la clave de servicio ignora RLS), 
-- pero SÍ bloqueará cualquier acceso público no autorizado a tu base de datos.
-- Por tanto, es una medida de seguridad perfecta.

-- 2. Asegurizar la Vista
-- En Supabase/PostgreSQL 15+, las vistas se deben crear con `security_invoker = true`
-- para que hereden las reglas RLS de las tablas subyacentes.

DROP VIEW IF EXISTS resumen_proyectos;

CREATE VIEW resumen_proyectos WITH (security_invoker = true) AS
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

COMMENT ON VIEW resumen_proyectos IS 'Vista de dashboard (Security Invoker activo).';
