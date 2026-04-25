-- Tabla: cv_download_requests
-- Propósito: Job Queue para generación asíncrona de CV premium
-- El Worker del orquestador detecta jobs "pending" y genera el PDF.
-- El Dashboard hace polling hasta que status = "done" y descarga.

create table if not exists cv_download_requests (
    id          uuid primary key default gen_random_uuid(),
    perfil_id   uuid not null references perfil_base(id) on delete cascade,
    con_foto    boolean not null default true,
    idioma      text    not null default 'ES',
    status      text    not null default 'pending',  -- pending | processing | done | error
    signed_url  text,
    error_msg   text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- Índice para que el Worker encuentre los jobs pendientes rápido
create index if not exists cv_download_requests_status_idx
    on cv_download_requests (status, created_at asc);

-- RLS: el usuario solo ve sus propios jobs
alter table cv_download_requests enable row level security;

create policy "usuario_ve_sus_requests" on cv_download_requests
    for select using (
        perfil_id in (
            select id from perfil_base where auth_user_id = auth.uid()
        )
    );

create policy "usuario_crea_sus_requests" on cv_download_requests
    for insert with check (
        perfil_id in (
            select id from perfil_base where auth_user_id = auth.uid()
        )
    );

-- El service_role (Worker) puede hacer todo
-- (no necesita policy porque bypasea RLS con la service key)
