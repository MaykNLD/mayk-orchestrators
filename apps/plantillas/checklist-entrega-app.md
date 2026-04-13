# Checklist de Entrega — Proyecto App
> Plantilla v1.0 · mayk.dev · Orquestador APPS

---

**Proyecto:** 
**Cliente:** 
**ID:** `APPS-YYYY-NNN`
**Stack:** `[ ] React Native/Expo   [ ] Flutter   [ ] Swift   [ ] Kotlin   [ ] PWA`
**Plataformas:** `[ ] iOS   [ ] Android   [ ] Web`
**Fecha de entrega:** 

---

## ✅ Métricas de calidad móvil (mínimos requeridos)

| Métrica | Herramienta | Mínimo | Resultado | ✓ |
|---|---|---|---|---|
| Startup Time (cold start) | Profiler nativo | < 3s | | |
| Frame Rate en scroll | Flipper / Instruments | > 55 FPS | | |
| Crash Rate | Firebase Crashlytics | < 1% | | |
| ANR Rate (Android) | Play Console | < 0.47% | | |
| Bundle JS (si React Native) | Metro Bundler | < 5MB | | |
| Cobertura de tests | Jest/XCTest/JUnit | > 70% lógica | | |
| E2E críticos pasando | Detox/XCUITest | 100% (3 flujos) | | |

---

## ✅ Pruebas funcionales

### Flujos E2E críticos (todos deben pasar al 100%)
- [ ] Flujo 1: Onboarding + registro / login
- [ ] Flujo 2: Flujo principal (pedido / reserva / publicación / ...)
- [ ] Flujo 3: Cierre de sesión + volver a entrar

### Pruebas en dispositivos físicos
**iOS:**
- [ ] iPhone SE (pantalla pequeña — el más restrictivo)
- [ ] iPhone 14/15 (tamaño estándar)
- [ ] iPad (si la app soporta tablet)

**Android:**
- [ ] Gama baja (API 26-28, RAM 2GB)
- [ ] Gama media (API 30-33)

### Funcional
- [ ] Login / registro ✓
- [ ] Roles y permisos: cada rol accede solo a lo que le corresponde ✓
- [ ] Tokens/sesiones expiran correctamente ✓
- [ ] Notificaciones push en primer y segundo plano ✓ (si aplica)
- [ ] Tap en notificación lleva a la pantalla correcta ✓ (si aplica)
- [ ] Swipe back iOS sin conflictos ✓
- [ ] Back button Android manejado correctamente ✓
- [ ] Comportamiento sin conexión documentado ✓ (si aplica)
- [ ] Integraciones externas: pagos, APIs, email ✓

---

## ✅ Seguridad

- [ ] Tokens en Keychain (iOS) / EncryptedSharedPreferences (Android) — nunca AsyncStorage plano
- [ ] Sin API keys hardcodeadas en el código fuente
- [ ] ProGuard/R8 activado en build de producción (Android)
- [ ] Permisos: solo los necesarios, con texto de razón claro
- [ ] `npm audit` (React Native): 0 vulnerabilidades críticas
- [ ] Certificate pinning implementado (si maneja datos financieros o sanitarios)

---

## ✅ Accesibilidad

- [ ] Tamaños de toque mínimos: 44×44px (iOS) / 48×48dp (Android)
- [ ] Labels de accesibilidad en todos los elementos interactivos
- [ ] Contraste de texto: mínimo 4.5:1
- [ ] Dark mode funcional sin romper el layout (si aplica)

---

## ✅ Distribución en tiendas

### iOS — App Store / TestFlight
- [ ] Icono de app completo (todos los tamaños: 1024×1024px master + AppIcon set)
- [ ] Splash screen correcto
- [ ] Capturas de pantalla para App Store (mínimo 3 por tamaño de dispositivo)
- [ ] Descripción de la app redactada
- [ ] Política de privacidad en URL pública
- [ ] Build firmado con certificado de producción (Distribution, no Development)
- [ ] Subido a App Store Connect
- [ ] Aprobado en revisión de Apple → [ ] Pendiente · [ ] Aprobado · [ ] En tienda
- [ ] Disponible en TestFlight para el cliente ✓

### Android — Google Play Console
- [ ] Icono adaptativo (foreground + background en 108dp)
- [ ] Capturas de pantalla (mínimo 2 por tipo de dispositivo)
- [ ] Descripción corta (< 80 caracteres) y larga (< 4000 caracteres)
- [ ] Política de privacidad en URL pública
- [ ] Build .aab firmado con keystore de producción (¡guardar el keystore de forma segura!)
- [ ] Subido a Internal Testing → Closed Testing → Production
- [ ] Aprobado en revisión de Google → [ ] Pendiente · [ ] Aprobado · [ ] En tienda

---

## ✅ Entregables finales

### Técnicos
- [ ] Código fuente en repositorio privado
- [ ] README técnico completo (instalación, build, variables)
- [ ] `.env.example` con todas las variables (sin valores reales)
- [ ] `eas.json` (React Native/Expo) o equivalente de build configurado
- [ ] Guía de build y distribución (cómo publicar futuras versiones)

### Documentación
- [ ] Informe QA completo con métricas y resultados
- [ ] Manual de administración (si hay panel web)
- [ ] Plan de mantenimiento (actualizaciones de OS anuales, dependencias)
- [ ] Guía de actualización para el cliente: cómo publicar nuevas versiones

### Accesos (entregados de forma segura)
- [ ] Acceso a App Store Connect (cuenta Apple Developer)
- [ ] Acceso a Google Play Console
- [ ] **Keystore de Android + contraseña** (crítico — sin esto no se pueden publicar futuras versiones)
- [ ] Certificados y perfiles de aprovisionamiento iOS
- [ ] Accesos a Firebase / Crashlytics / Analytics
- [ ] Credenciales de servicios externos (backend, BBDD, APIs)

---

## ✅ Cierre del proyecto

- [ ] El cliente ha instalado y probado la app en su dispositivo
- [ ] El cliente ha aprobado la app en producción (o en TestFlight/Internal Testing)
- [ ] Archivos privados del cliente extraídos del repositorio antes del cierre
- [ ] Proyecto archivado en `proyectos/` con estado: **ENTREGADO**

**Aprobación final del cliente:** [ ] SÍ · Fecha: ___________ · Por: ___________

---

*🟢 Proyecto cerrado correctamente. Estado: ENTREGADO.*
