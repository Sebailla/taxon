# Aprobación del diseño — Fase 3

## Estado

**Aprobado para traducción a código.** El diseño de la interfaz en cascada generado por `pen --agent codex --model gpt-5.5` pasa la auditoría de impeccable con una puntuación de 17/20.

## Resumen de aprobación

| Elemento | Valor |
| --- | --- |
| Archivo de diseño | `taxon.pen` (109 KB) |
| Generador | Pencil CLI vía Codex |
| Puntuación de auditoría | 17/20 (Buena) |
| Documento de auditoría | [`design-audit.md`](../design/design-audit.md) |
| Componentes | 4 reutilizables (Toggle Chip, Dropdown Field, Source Link Button, Species Row) |
| Viewports | 2 (Escritorio 1440, Móvil 390) |
| Estados cubiertos | 8 (carga, vacío, 404, 409, error de red, deshabilitado, foco, toggle activo) |
| Tokens de color | 9 semánticos + 10 hex (fondos de badge) |
| Tipografía | Inter + IBM Plex Mono (Pencil rechazó `system-ui`) |

## Decisiones

1. **Aprobado.** El diseño expresa un sistema coherente y específico del producto, con componentes reutilizables y una matriz de estados paralela.
2. **Extracción de tokens diferida al código.** Los 10 valores hex codificados para los fondos de los badges se reemplazarán con tokens de Tailwind durante la implementación en React. Marcado como seguimiento P2.
3. **Fallback tipográfico documentado.** Inter + IBM Plex Mono fueron elegidos porque Pencil rechazó `system-ui`. El CSS de producción declarará `system-ui, Inter, sans-serif` para que la fuente del sistema operativo del usuario gane antes de que Inter cargue.
4. **Revisión visual diferida.** Se recomienda una revisión visual final interactiva en `Pen.app`, pero no es bloqueante. El usuario tiene el diseño abierto en `Pen.app` y puede tomar capturas cuando lo desee.

## Firmas

- Fecha: 2026-08-11
- Fase: 3 (Diseño de frontend — Pencil + impeccable)
- Aprobado por: orquestador + usuario
- Próxima fase: 4 (Implementación del frontend en React)

## Criterios de aceptación

- [x] El archivo de diseño existe (`taxon.pen`).
- [x] El diseño cubre los 8 requisitos (cabecera, toggles, cascada, lista de especies, breadcrumb, enlaces, selector de ambigüedad, estados).
- [x] Paridad móvil + escritorio.
- [x] Componentes reutilizables aislados en Component Shelf.
- [x] Tokens de color utilizados para la paleta principal.
- [x] Dimensiones de auditoría cubiertas (jerarquía, accesibilidad, tipografía, color, integridad).
- [ ] Revisión visual final en Pen.app (diferida al usuario).
- [ ] Extracción de tokens en el código React (diferida a la Fase 4).

## Próximos pasos

Comienza la Fase 4 (frontend en React + Vite + Tailwind). El frontend:

- Usa la misma paleta de colores y tipografía que `taxon.pen`.
- Implementa la cascada como una máquina de estados `useReducer` de 6 pasos para que cada transición sea testeable.
- Renderiza la cuadrícula de 12 enlaces con el mismo tratamiento visual (4×3 en escritorio, 2 columnas en móvil).
- Usa tokens de Tailwind para sustituir los 10 colores hex codificados para badges del diseño.
- Auditado con el comando `audit` de impeccable durante la revisión de código.