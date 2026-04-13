# mayk-orchestrators

Repositorio privado central de gestión de proyectos, dividido por **Orquestadores**. El sistema utiliza los agentes globales alojados en el repositorio hermano `mayk-agents`.

## Orquestadores Activos

### 🌐 PWEB (Proyectos Web)
Ubicación: `/pweb`
Orquestador encargado de: Landing Pages, E-commerce, Webs Corporativas, SaaS y Blogs. Maneja el ciclo completo (de Briefing a producción con Vercel/Railway).

### 📱 APPS (Proyectos App Móviles y PWA)
Ubicación: `/apps`
Orquestador diseñado para el ecosistema móvil: PWA, React Native, Flutter, Swift y Kotlin. Preparado para QA de rendimiento nativo y publicación en App Store y Google Play.

---

## Flujo de Trabajo (Para herramientas de IA)

Si estás utilizando IDEs o herramientas como **Claude Code**, **Antigravity** o **Cursor**, navega a la carpeta del orquestador que necesites (ej. `cd pweb/`).  
La IA leerá automáticamente `.agents/workflows/maestro-<tipo>.md` para cobrar vida e iniciar el proceso metodológico de mayk.dev guiándote a lo largo de 4 fases (Fase 0 a Fase 3) pasando por el análisis, la estrategia, el diseño, desarrollo, pruebas hasta el despliegue a producción.

## Plantillas y Proyectos

Dentro de cada orquestador existen las carpetas:
- `/plantillas`: Modelos de informes, briefs del cliente, checklists de entrega y propuestas económicas específicas para ese orquestador.
- `/proyectos`: Directorios donde se guarda el estado de los proyectos reales. Cada cliente tendrá aquí su carpeta con sus respectivos documentos firmados para trackear el progreso de cada fase.

> ⚠️ IMPORTANTE: Este repositorio NO almacena credenciales de clientes, bases de código cerradas de terceros, keystores/certificados de producción, ni `.env` de producción. Dichos archivos deben proveerse externamente y gestionados con rigor.

---
**Versión del Sistema PWEB:** `v4.0.0`
**Versión del Sistema APPS:** `v1.0.0`
