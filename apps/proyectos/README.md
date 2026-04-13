# Proyectos App — mayk.dev

Esta carpeta contiene un subdirectorio por cada proyecto de app completado o en curso.

## Estructura de cada proyecto

```
proyectos/
└── nombre-cliente-YYYY/
    ├── brief-cliente-app.md      ← Brief completado en Fase 0
    ├── informe-fase-1.md         ← Estrategia y stack aprobados
    ├── informe-fase-2.md         ← Diseño y construcción aprobados
    ├── informe-fase-3.md         ← QA y distribución en tiendas
    ├── checklist-entrega-app.md  ← Firmado por el cliente
    └── README.md                 ← Estado actual del proyecto
```

## Estados posibles

| Estado | Descripción |
|---|---|
| 🔴 EN CURSO — Fase X | Proyecto activo en la fase indicada |
| 🟡 EN REVISIÓN DE TIENDA | App enviada a Apple/Google, esperando aprobación |
| 🟢 ENTREGADO | App en producción y aceptada por el cliente |
| ⚫ ARCHIVADO | Proyecto pausado o cancelado |

## Nota de privacidad

Los archivos de cliente (assets, keystores, certificados, credenciales) **no se incluyen en este repositorio**.
Son gestionados fuera del repo y entregados al cliente de forma segura al cierre del proyecto.

⚠️ **Importante:** Los keystores de Android son críticos. Sin ellos no se pueden publicar
futuras versiones de la app. Se entregan al cliente y se almacenan en lugar seguro.
