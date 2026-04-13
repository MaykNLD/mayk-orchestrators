# Checklist de Entrega — Proyecto Web
> Plantilla v4.0 · mayk.dev · Orquestador PWEB

---

**Proyecto:** 
**Cliente:** 
**ID:** `PWEB-YYYY-NNN`
**URL de producción:** 
**Fecha de entrega:** 

---

## ✅ Fase 3 — Control de Calidad

### Lighthouse (mínimo > 85 en cada categoría)

| Página | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|
| Home | | | | |
| (página crítica 2) | | | | |
| (página crítica 3) | | | | |

- [ ] Todas las páginas principales superan 85 en las 4 categorías
- [ ] Core Web Vitals: LCP < 2.5s · FID/INP < 200ms · CLS < 0.1

### Responsive
- [ ] Móvil 375px ✓
- [ ] Tablet 768px ✓
- [ ] Desktop 1280px ✓
- [ ] Desktop 1920px ✓

### Funcional
- [ ] Flujos críticos probados de principio a fin
- [ ] Login / registro (si aplica) ✓
- [ ] Flujo de compra / formulario principal ✓
- [ ] Panel de administración (si aplica) ✓
- [ ] Integraciones externas (pagos, email, CRM) ✓
- [ ] 0 errores en consola del navegador

### Seguridad
- [ ] HTTPS activo con certificado válido
- [ ] Headers de seguridad configurados (CSP, HSTS, X-Frame-Options)
- [ ] Variables de entorno en producción (no hardcodeadas)
- [ ] `npm audit`: 0 vulnerabilidades críticas
- [ ] Banner de cookies / RGPD (si aplica)

### Navegadores
- [ ] Chrome (última versión) ✓
- [ ] Firefox (última versión) ✓
- [ ] Safari (si base de usuarios Mac/iOS) ✓

---

## ✅ Entregables finales

### Técnicos
- [ ] URL de producción accesible y verificada
- [ ] Código fuente en repositorio privado del cliente
- [ ] README técnico completo (instalación, ejecución, variables)
- [ ] `.env.example` con todas las variables (sin valores reales)
- [ ] Manual de administración (si hay panel admin)

### Documentación
- [ ] Informe QA completo (Lighthouse + pruebas funcionales)
- [ ] Plan de mantenimiento básico (actualizaciones, backups, monitorización)
- [ ] Guía de despliegue paso a paso

### Accesos (entregados de forma segura)
- [ ] Credenciales del panel de hosting
- [ ] Credenciales de BBDD (si aplica)
- [ ] Accesos a servicios externos (Stripe, SendGrid, etc.)
- [ ] Dominio y DNS → transferidos o documentados

---

## ✅ Cierre del proyecto

- [ ] El cliente ha revisado y aprobado el proyecto en producción
- [ ] El cliente ha firmado (o confirmado por correo) la aceptación
- [ ] Archivos privados del cliente extraídos del repositorio antes del cierre
- [ ] Proyecto archivado en `proyectos/` con estado: **ENTREGADO**

**Aprobación final del cliente:** [ ] SÍ · Fecha: ___________ · Por: ___________

---

*🟢 Proyecto cerrado correctamente. Estado: ENTREGADO.*
