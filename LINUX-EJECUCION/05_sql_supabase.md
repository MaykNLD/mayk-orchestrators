# SQL para ejecutar en Supabase Dashboard

## Instrucciones

1. Abre https://supabase.com → Tu proyecto → **SQL Editor**
2. Haz clic en "New Query"
3. Copia y pega el contenido de `career/supabase/migrations/001_career_schema.sql`
4. Haz clic en "Run" (o Ctrl+Enter)
5. Verifica que aparecen las 4 tablas:
   - `perfil_base`
   - `aplicaciones_career`
   - `scan_history`
   - `career_ejecuciones`

## Cargar tu perfil base (Master CV)

Después de crear las tablas, inserta tu perfil en `perfil_base`:

```sql
INSERT INTO perfil_base (nombre, apellido, email, idioma, mercado, datos_json)
VALUES (
  'Tu Nombre',
  'Tu Apellido',
  'tu@email.com',
  'ES',
  'ES',
  '{
    "resumen": "Desarrollador con experiencia en...",
    "experiencia": [],
    "proyectos": [],
    "skills": { "principales": ["Python", "Java"], "secundarias": [] },
    "educacion": []
  }'
);
```

Puedes también usar el onboarding del maestro-career.md cuando conectes desde el CLI.