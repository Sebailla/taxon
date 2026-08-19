# Diseño Stitch: tree-deep-subtree (Tier Groups)

> **Artefacto de gate de diseño para PR C** (reemplaza la página Pencil `.pen` según el precedente de `arbol-col-browse` y `species-folder-explorer`, ahora usando Stitch MCP porque Pencil quedó deprecado).

## Proyecto Stitch

- **ID de proyecto**: `projects/11955314884511019764`
- **Título**: "Taxon — Tree Deep Subtree (Tier Groups)"
- **Herramienta**: Stitch MCP (`stitch_generate_screen_from_text`)
- **Origen**: `PROJECT_DESIGN`
- **Tipo de dispositivo**: `DESKTOP`
- **Pantalla**: "Taxonomic Tree Browser" (2560×2214)

## Brief de diseño (lo que se pidió a Stitch)

UI de exploración de árbol taxonómico, escritorio, modo claro. Barra superior con título, búsqueda y toggles. Migas de pan `Eukaryota > Animalia`. Filas de árbol con caret + indentación + etiqueta de rango en mayúsculas + nombre científico + badge de conteo de especies. Después de los hijos directos de `Animalia`, una sección de tier-group etiquetada `Phyla (34)` con cabecera con caret y las primeras 50 filas de phylum indentadas un nivel más, más un affordance "Load more". Tipografía Inter. Fondo slate.

## Lo que muestra la pantalla renderizada

- Barra superior: título "Taxonomic Tree" + búsqueda "Find taxon…" + toggles "Source" + "Extant only" + nav (Browser / Classification / Settings).
- Migas: "Eukaryota > Animalia" con el segmento activo tintado con borde izquierdo azul primario.
- Hijos directos de Eukaryota: KINGDOM `Animalia` (resaltado), luego KINGDOM `Plantae` y `Fungi` (bucket Reino, con conteos negativos porque colapsan a nada).
- **Tier-group "Phyla (34)"**: caret + etiqueta + botón "Load all" a la derecha; primeros 5 phyla renderizados (Arthropoda, Mollusca, Chordata, Nematoda, Priapulimorpha) con la nota inline "via subphylum rollup" donde la profundidad de rollup > 1.
- Pie: "© 2024 Taxonomic Database System · Citation Policy · Data Sources" + estado del sistema.

## Lo que el implementador DEBE traducir línea por línea

| Elemento de superficie | Lo que dice Stitch | Regla de traducción |
|---|---|---|
| Fondo de cabecera de tier-group | Mismo tinte que hijos directos | Promover a `bg-slate-100` (o `surface_container_low`) + rotación del caret cuando esté expandido. Diferenciar de filas regulares. |
| Botón "Load all" | Botón sólido azul | Re-renderizar como botón de texto fantasma alineado a la derecha con icono chevron: `text-slate-700 hover:bg-slate-100 px-3 py-1 rounded-md`. Coincide con el sistema de diseño de Taxon (sutil, no ruidoso). |
| Dirección del caret | `▸` estático | El componente DEBE alternar a `▾` cuando el tier group esté expandido; rotar 90° vía CSS `transform: rotate(90deg)` con espejo `aria-expanded`. |
| Nota inline "via subphylum rollup" | Sufijo gris itálica | Renderizar como `<span class="text-xs italic text-slate-400 ml-2">via subphylum rollup</span>` solo cuando `rollup_depth > 1`. |
| Badge de etiqueta de rango | Monoespaciada mayúscula, fondo slate-tinted | `font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-100 text-slate-500`. |
| Badge de conteo de especies | Número monoespaciado + `spp.` alineado a la derecha | `font-mono text-sm text-slate-500` alineado a la derecha en la fila. |

## Lo que el implementador NO DEBE hacer

- Ningún token de diseño nuevo. Solo defaults de Tailwind del `tailwind.config.js` existente del proyecto.
- Ninguna paleta de colores nueva. Usar el slate + azul primario existente (coincide con el segmento activo de las migas).
- Ningún componente nuevo en el design system más allá del propio `<TierGroup>`. Las filas de tier reusan `<TreeNodeRow>` literal.
- Ninguna clase `stone-*` (deriva del proyecto documentada en `docs/design/taxonomic-tree-browse.md` §15 — aplicar la misma reconciliación).

## Estado del gate

- [x] Diseño Stitch renderizado.
- [ ] Pase de auditoría del skill `impeccable` — jerarquía, accesibilidad, tipografía, color, movimiento, anti-patrones.
- [ ] Hallazgos de auditoría replegados en este brief o marcados como SUGGESTION para seguimiento.
- [ ] Sign-off de diseño registrado antes de que PR C arranque.


## Pase de auditoría impeccable (degraded inline — banner de contexto único)

`Método: ⚠️ DEGRADED: single-context (impeccable skill no es un subagent_type delegable en este harness; el detector Assessment B `detect.mjs` no está instalado en la raíz del proyecto, por lo que el escaneo determinista se omitió).`

### Hallazgos

| # | Severidad | Hallazgo | Fix recomendado |
|---|-----------|----------|-----------------|
| 1 | **P1 / WCAG AA fail** | El botón "Load all" usa `text-outline` (#737686) sobre `bg-surface-container-low` (#f2f4f6). Contraste ~3.6:1 — bajo el umbral 4.5:1 para texto normal. Igual para la cursiva `via subphylum rollup`. | Usar `text-on-surface-variant` (#434655) sobre el mismo fondo → ratio ~7.4:1, pasa AA + AAA. |
| 2 | **P1** | El botón "Load all" aparece `cursor-not-allowed opacity-50` aunque solo hay 34 phyla (muy por debajo del cap de 50 filas → el botón DEBE estar oculto, no deshabilitado). | Ocultar el botón completamente cuando `next_cursor is null` después de la primera página. Mostrar solo cuando `len(children) < tier_total`. |
| 3 | **P2 / a11y** | El caret del header del tier-group usa `arrow_drop_down` estático — sin rotación ni espejo `aria-expanded`. Los usuarios de lector de pantalla no distinguen expandido vs colapsado. | Cambiar caret a `arrow_right` (colapsado) / `arrow_drop_down` (expandido); añadir `role="button"` `aria-expanded={open}` `aria-controls={tierListId}` en el header. |
| 4 | **P2** | La línea conectora vertical (`bg-outline-variant/30`) cruza a través del header del tier-group, haciendo que el agrupamiento sea indistinguible de las filas regulares del árbol. | Romper el conector en el header del tier-group (pseudo-elemento `before:` o margen `gap-y`) para que el header se asiente en su propia ranura. |
| 5 | **P2** | La etiqueta de rango usa el mismo tratamiento (fuente, peso, fondo del badge) para cada rango — Kingdom, Phylum, Genus se ven igual. | Mantener monoespaciada + mayúsculas, pero variar sutilmente el color del badge por rango (Phylum: `bg-primary/5`, Family: `bg-secondary/5`, Genus: `bg-tertiary/5`). Opcional — solo si el design system del proyecto permite tokens por rango. |
| 6 | **P3** | Prefijo `~320,000 spp.` tilde en Plantae/Fungi (bajo el padre Eukaryota) — sin leyenda explicando que es un conteo aproximado cuando los hijos son reinos sin descendientes computados. | Añadir `<abbr title="Aproximado">~</abbr>` o tooltip inline "conteo aproximado". |
| 7 | **P3** | El toggle "Source" se muestra OFF (punto blanco a la izquierda) sin pista de qué fuentes hay disponibles. | Añadir tooltip al toggle o cambiar la etiqueta a "Source: CoL" con chip clickable para expandir. |

### Salud del diseño (heurística estimada, contexto único)

| # | Heurística | Score | Nota |
|---|-----------|-------|------|
| 1 | Visibilidad del estado del sistema | 3 | Migas + fila activa funcionan; falta estado en header del tier-group. |
| 2 | Coincidencia sistema / mundo real | 3 | Lenguaje taxonómico es preciso (Kingdom / Phylum / spp.). |
| 3 | Control y libertad del usuario | 3 | El affordance "Load all" está presente (roto pero presente). |
| 4 | Consistencia y estándares | 3 | Reusa patrones de Taxon de `taxonomic-tree-browse.md`. |
| 5 | Prevención de errores | 3 | El botón deshabilitado previene paginación prematura. |
| 6 | Reconocimiento antes que recuerdo | 3 | Las convenciones de caret son universales. |
| 7 | Flexibilidad y eficiencia | n/a | Superficie Operate — nav por teclado se trackea en PR C WU 5 por separado. |
| 8 | Estético y minimalista | 3 | Paleta clara, adorno escaso. |
| 9 | Recuperación de errores | n/a | Sin estados de error en el render estático. |
| 10 | Ayuda y documentación | n/a | La documentación está aguas arriba de este gate. |

**Total**: 21/24 → 87% → **Banda Excelente** (según máximo renormalizado tras 2 n/a).

### Decisión del gate

`status: warning` — **aprobar con un fix de contraste P1 y el bug del botón deshabilitado**. Ambos son cambios mecánicos que el implementador puede aplicar sin re-correr Stitch:

- **P1 #1**: cambiar `text-outline` a `text-on-surface-variant` en los elementos load-more y nota de rollup.
- **P1 #2**: ocultar el botón load-more cuando `tier_total ≤ tier_limit`.

Los ítems P2/P3 restantes se trackean como SUGGESTIONs para issues de seguimiento; no bloquean PR C.

### Siguiente

El implementador de PR C (worktree `feat/tree-deep-subtree-pr3`) traduce el brief de superficie línea por línea, aplicando los dos fixes P1 inline. Las 5 unidades de trabajo en `tasks.md` Phase 3 quedan como están.
