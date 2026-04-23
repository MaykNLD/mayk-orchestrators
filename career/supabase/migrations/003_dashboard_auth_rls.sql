-- ============================================================
-- Migration 003: Career-Ops Dashboard Support
-- Adds: auth integration, user_roles, backend_status,
--       missing profile fields, and granular RLS policies
-- ============================================================

-- ── 1. NUEVOS CAMPOS EN perfil_base ──────────────────────────
-- Campo auth_user_id: vincula perfil con Supabase Auth user
ALTER TABLE perfil_base ADD COLUMN IF NOT EXISTS auth_user_id  UUID REFERENCES auth.users(id) ON DELETE SET NULL;
-- Campo cv_markdown: texto plano del CV extraido del PDF
ALTER TABLE perfil_base ADD COLUMN IF NOT EXISTS cv_markdown   TEXT DEFAULT '';
-- Campo titular: titulo profesional del candidato
ALTER TABLE perfil_base ADD COLUMN IF NOT EXISTS titular       TEXT DEFAULT '';
-- Campo foto_url: URL de la foto del candidato en Storage
ALTER TABLE perfil_base ADD COLUMN IF NOT EXISTS foto_url      TEXT DEFAULT '';
-- Campo telefono: contacto
ALTER TABLE perfil_base ADD COLUMN IF NOT EXISTS telefono      TEXT DEFAULT '';

-- ── 2. TABLA: user_roles ─────────────────────────────────────
-- Relaciona auth.users con rol (admin | user)
CREATE TABLE IF NOT EXISTS user_roles (
  user_id    UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role       TEXT NOT NULL DEFAULT 'user',  -- 'admin' | 'user'
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;

-- Solo el propio usuario o un admin puede ver el rol
CREATE POLICY "user_roles_select" ON user_roles
  FOR SELECT USING (
    auth.uid() = user_id
    OR EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = auth.uid() AND ur.role = 'admin')
    OR auth.role() = 'service_role'
  );

-- Solo service_role puede insertar/modificar roles (el backend lo gestiona)
CREATE POLICY "user_roles_write" ON user_roles
  FOR ALL USING (auth.role() = 'service_role');

-- ── 3. TABLA: backend_status ─────────────────────────────────
-- El GitHub Action escribe aqui su URL al arrancar y borra al parar
CREATE TABLE IF NOT EXISTS backend_status (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url        TEXT NOT NULL,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  status     TEXT DEFAULT 'online'
);

ALTER TABLE backend_status ENABLE ROW LEVEL SECURITY;

-- Cualquier usuario autenticado puede leer el estado (para mostrar en UI)
CREATE POLICY "backend_status_read" ON backend_status
  FOR SELECT USING (
    auth.role() = 'authenticated'
    OR auth.role() = 'service_role'
  );

-- Solo service_role puede escribir (el Action usa SERVICE_KEY)
CREATE POLICY "backend_status_write" ON backend_status
  FOR ALL USING (auth.role() = 'service_role');

-- ── 4. RLS GRANULAR EN perfil_base ───────────────────────────
-- Eliminar la politica anterior permisiva y reemplazar con roles
DROP POLICY IF EXISTS "Acceso autenticado total" ON perfil_base;

-- Admin: acceso total
CREATE POLICY "perfil_admin_all" ON perfil_base
  FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles WHERE user_id = auth.uid() AND role = 'admin')
    OR auth.role() = 'service_role'
  );

-- Usuario: solo lee/edita su propio perfil (vinculado por auth_user_id)
CREATE POLICY "perfil_user_own" ON perfil_base
  FOR SELECT USING (auth_user_id = auth.uid());

CREATE POLICY "perfil_user_update" ON perfil_base
  FOR UPDATE USING (auth_user_id = auth.uid());

-- ── 5. RLS GRANULAR EN aplicaciones_career ───────────────────
DROP POLICY IF EXISTS "Acceso autenticado total" ON aplicaciones_career;

-- Admin: acceso total
CREATE POLICY "apps_admin_all" ON aplicaciones_career
  FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles WHERE user_id = auth.uid() AND role = 'admin')
    OR auth.role() = 'service_role'
  );

-- Usuario: solo ve sus propias aplicaciones (via perfil vinculado)
CREATE POLICY "apps_user_own" ON aplicaciones_career
  FOR SELECT USING (
    perfil_id IN (
      SELECT id FROM perfil_base WHERE auth_user_id = auth.uid()
    )
  );

-- ── 6. INDICES ADICIONALES ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_perfil_auth_user ON perfil_base(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role  ON user_roles(role);

-- ── 7. SUPABASE STORAGE BUCKETS ──────────────────────────────
-- NOTA: Los buckets se crean desde el dashboard de Supabase Storage
-- o via API. Esta migration solo documenta los necesarios:
-- Bucket: 'fotos-candidatos'  (privado, acceso firmado)
-- Bucket: 'cvs-pdf'           (privado, acceso firmado)
-- Bucket: 'cvs-generados'     (ya deberia existir para los PDFs de salida)
COMMENT ON TABLE backend_status IS 'Estado del backend efimero (GitHub Actions). La UI lo lee para saber si las operaciones IA estan disponibles.';
COMMENT ON TABLE user_roles IS 'Roles de acceso al dashboard Career-Ops. admin = acceso total, user = solo su perfil.';