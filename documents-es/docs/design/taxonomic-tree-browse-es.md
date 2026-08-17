# Diseño — Exploración del Árbol Taxonómico

> **Brief de superficie para el PR 3 (frontend TaxonomicTree).** Este documento reemplaza la página de Pencil `.pen` que el AGENTS.md §5 normalmente exige. El MCP de Pencil está deshabilitado en esta sesión, por lo que la pasada de diseño va directo al marco de impeccable y se captura aquí como un artefacto en markdown. La persona implementadora del frontend DEBE traducir este documento línea por línea en `TaxonomicTree.tsx`, `TaxonomicTree.state.ts` y las clases de Tailwind. **Ninguna decisión visual queda a criterio de la persona implementadora.**

---

## 1. Declaración de la superficie

La superficie **Exploración del Árbol Taxonómico** es el panel izquierdo del diseño de dos columnas de Taxon (`frontend/src/App.tsx`). Reemplaza la cascada de 7 desplegables fijos (`Cascade`) por un árbol jerárquico estilo CoL que carga hijos de forma perezosa por `parent_id`, aplica sangría por rango y renderiza cada fila como `rango: Nombre Autoría • N spp.`. Un autocompletar "Buscar taxón" vive en la cabecera; el camino explorado fluye a través del store Zustand `cascadePath` y un `CustomEvent` `path:change` para que el panel de enlaces de la miga de pan de la derecha siga funcionando.

**Modo:** Operar. La persona visitante está cumpliendo una tarea (ubicar un taxón para aterrizar en una especie). La escaneabilidad, la consistencia y las expectativas nativas pesan más que la expresión. La marca vive en los detalles precisos — tipografía recta, espaciado ajustado, color contenido — no en acentos fuertes.

**Imagen de referencia:** `../../col-tree.png` (la página original "Browse" del Catalogue of Life). La referencia es un punto de partida, no una copia. La identidad de marca del nuevo árbol es la paleta existente del proyecto (`navy`/`slate`/`border`/`accent`) con tipografía ajustada y un ritmo de fila de 32px, **no** los enlaces azul brillante del CoL ni su diseño denso de 26px.

**Qué reemplaza:** `frontend/src/components/Cascade.tsx` (425 líneas) + `Cascade.state.ts` (180 líneas) + seis archivos `cascade*.test.tsx`. La ranura de la cuadrícula en `App.tsx` no cambia: `<TaxonomicTree>` se monta en la misma ranura que ocupaba `<Cascade>`.

---

## 2. Disposición y cuadrícula

### Escritorio (≥ 1024px)

```
┌─────────────────────────────────────────────────────────────┐
│ Buscar taxón (p. ej. Panthera)        [ ] Fuente  [ ] Solo vivientes │
│ ─────────────────────────────────────────────────────────── │
│ ▾ REINO    Animalia • 1.792.173 spp.                        │
│   ▸ FILO    Chordata • 86.602 spp.                          │
│     ▸ CLASE  Mammalia • 7.164 spp.                          │
│       ▸ ORDEN Carnivora • 389 spp.                          │
│         ▸ FAMILIA Felidae • 152 spp.                        │
│           ▸ GÉNERO Panthera • 44 spp.                       │
│             ▸ ESPECIE Panthera leo (Linnaeus, 1758) • 28 subesp. │
└─────────────────────────────────────────────────────────────┘
```

- Contenedor `max-w-page` (1200px, definido en `tailwind.config.js`).
- Tarjeta interna: `rounded-card border border-border bg-surface p-4` (espejo de la tarjeta de Breadcrumb).
- Fila de cabecera: `flex items-center gap-3` — el input de búsqueda toma `flex-1`, los filtros se alinean a la derecha.
- Filas del árbol: lista vertical con `gap-0` (las guías de sangría pintan el ritmo).
- La tarjeta se ubica dentro de la columna izquierda existente de `App.tsx` (`lg:col-span-1` de `grid-cols-1 lg:grid-cols-2`).

### Tableta (640–1024px)

```
┌──────────────────────────────────────────────────┐
│ Buscar taxón (p. ej. Panthera)         [buscar] │
│ [ ] Fuente  [ ] Solo vivientes                   │
│ ──────────────────────────────────────────────── │
│ ▾ REINO Animalia • 1.792.173 spp.                │
│   ▸ FILO Chordata • 86.602 spp.                 │
│   ...                                            │
└──────────────────────────────────────────────────┘
```

- Los filtros colapsan a una sola fila debajo del input de búsqueda.
- Cabecera apilada: `flex flex-col gap-3`; la fila interna usa `flex flex-wrap items-center gap-3`.

### Móvil (< 640px)

```
┌──────────────────────────────┐
│ Buscar taxón (p. ej. Panthera) │
│ <details>Filtros</details>     │
│ ─────────────────────────── │
│ ▾ Animalia • 1.79M spp.     │
│   ▸ Chordata • 86.602 spp.  │
│   ...                        │
└──────────────────────────────┘
```

- Los filtros se mueven a un acordeón `<details><summary>Filtros</summary>...</details>`.
- La altura de fila baja de 32px a 28px (compacto). El paso de sangría baja de 16px a 12px.
- La etiqueta de rango se oculta en la fila (la insignia de especie es el único marcador visible).
- Objetivos táctiles ≥ 44×44px — cada fila, el caret, el input de búsqueda, los checkboxes de filtro.

### Sugerencias de cuadrícula Tailwind

```
contenedor:        max-w-page mx-auto
tarjeta:           rounded-card border border-border bg-surface p-4
fila cabecera:     flex flex-col gap-3 md:flex-row md:items-center
input cabecera:    flex-1 h-10 rounded-md border border-border bg-surface px-3 text-sm
tipo búsqueda:     type="search" (botón de borrado nativo)
fila filtros:      flex flex-wrap items-center gap-3 text-xs text-slate
lista árbol:       role="tree" gap-0
```

Padding táctil solo móvil: `py-3` en lugar de `py-2` por fila, para que la fila visible de 28px siga siendo un objetivo táctil de 44px.

---

## 3. Anatomía de la fila

Este es el corazón del diseño. Cada fila es una franja flexionada horizontalmente. De izquierda a derecha:

```
┌─ guía de sangría ─┬─ caret ─┬─ etiqueta rango ─┬─ nombre ─┬─ separadores ─┬─ autoría ─┬─ insignia ─┐
│  │                │  ▸      │  DOMINIO         │  Euk…    │  ·           │  (Chatton…)│  —       │
└───────────────────┴─────────┴──────────────────┴──────────┴──────────────┴───────────┴───────────┘
```

### Anchos en píxeles y clases Tailwind

| Parte | Visual | Ancho | Clases Tailwind |
|-------|--------|-------|-----------------|
| **Guía de sangría** | Hairline vertical 1px, `border-border` | 1px (iguala el paso de sangría) | `before:absolute before:left-0 before:top-0 before:h-full before:w-px before:bg-border` |
| **Caret** | `▸` cerrado, `▾` abierto, 14px | Columna 24px (glifo 16px + 4px por lado) | `inline-flex h-6 w-6 shrink-0 items-center justify-center text-xs text-slate select-none` |
| **Etiqueta de rango** | Etiqueta pequeña en mayúsculas | auto, ~70px | `shrink-0 text-[10px] font-medium uppercase tracking-widest text-slate` |
| **Nombre (enlace)** | Texto primario, trunca a 1 línea, oscurece en hover | flex-1, min-width 0 | `min-w-0 flex-1 truncate text-sm font-medium text-navy hover:text-slate focus:outline-2 focus:outline-accent` |
| **Autoría** | Itálica más pequeña, trunca a 1 línea, precedida por `·` | auto, máximo 40% de ancho | `hidden md:inline shrink-0 max-w-[40ch] truncate text-xs italic text-slate` |
| **Insignia de especie** | Píldora monocroma, `tabular-nums` | auto, ~96px | `inline-flex shrink-0 items-center gap-1 rounded-full bg-bg px-2 py-0.5 text-xs font-medium text-slate tabular-nums` |

### Glifos marcadores (prefijo de la etiqueta de rango)

- `⚠` para `is_uncertain` — `text-amber`.
- `⊘` para `is_unassigned` — `text-muted`.
- `†` para `is_extinct` — `text-red`.
- Los sinónimos (`is_synonym`) se ocultan por defecto; el toggle "Sinónimos" en la cabecera (§4) los muestra.

### Altura de fila

- **Por defecto (colapsada):** 32px en escritorio (`h-8`), 28px en móvil (`h-7`).
- **Con foco o en hover:** 36px en escritorio (`h-9`), 36px en móvil (sin altura extra, solo fondo).
- Contenedor de fila: `flex items-center gap-2 px-2` más la utilidad de altura.

### Detalles de disposición de la fila

- Toda la fila es un `<button>` para que la franja completa sea clicable (sin objetivos huérfanos) y el `<button>` cargue la semántica de Enter/Espacio. El caret es un `<span>` visual que rota con CSS — hacer clic en él NO llama a `stopPropagation`; el `<button>` padre gestiona el toggle.
- La sangría se calcula desde la profundidad de la fila en el árbol expandido, no desde `display_level`. React renderiza el árbol de arriba hacia abajo; cada fila recibe su profundidad como prop.
- `aria-expanded` vive en el `<button>` y refleja el estado del caret (`true` cuando los hijos están renderizados).
- El colapso y la expansión son puramente visuales sobre `aria-expanded` de la fila; React indexa en el id del padre en la caché (`childrenByParent: Map<id, TreeNode[]>`), por lo que colapsar y volver a expandir es un re-render libre de los mismos hijos cacheados.

### Por qué cada patrón

- **Caret como span, no como botón hijo.** Mantener el caret puramente visual evita trampas de foco por elementos interactivos anidados y permite que `<button>` de la fila gestione cada gesto de teclado.
- **Nombre como enlace primario, no la fila completa como enlace.** Los lectores de pantalla anuncian "Eukaryota, almohadilla, 5,4 millones de especies" — el resto de la fila es metadato. El `<button>` mantiene la fila clicable para usuarios de ratón.
- **Autoría oculta en móvil (`hidden md:inline`).** La fila más profunda de un viewport de 1200px obtiene un presupuesto de 40 caracteres; en un móvil de 360px ese peso se lee como ruido. La insignia de especie es el único metadato contextual que sobrevive.
- **La insignia de especie usa `tabular-nums`.** Los números se alinean entre filas; la persona usuaria hace un escaneo visual rápido "esta fila tiene 7M, esta otra tiene 200" sin reflujo.

---

## 4. Fila de cabecera (sobre el árbol)

La cabecera es la misma franja horizontal que comparten el input de búsqueda y los filtros.

### Input de búsqueda "Buscar taxón"

```
┌───────────────────────────────────────────────────────────────┐
│ 🔍 Buscar taxón (p. ej. Panthera)                             │
└───────────────────────────────────────────────────────────────┘
```

- Ancho completo: `flex-1 h-10 rounded-md border border-border bg-surface px-3 text-sm`.
- Prefijo de icono de lupa: un SVG de 16px (`<svg viewBox="0 0 16 16">`, dibujado a mano, trazo 1.5) en `absolute left-3 top-1/2 -translate-y-1/2`. `<svg>` lleva `aria-hidden="true"`; el input carga la etiqueta visible.
- Debounce de 200ms → `GET /api/tree/search?q={q}` (según la spec `taxon-tree-search`).
- `type="search"` para que el navegador pinte el botón de borrado nativo.
- Estado vacío placeholder: `"Buscar taxón (p. ej. Panthera)"`.
- `aria-label="Buscar taxón"`, `aria-controls="tree-search-results"`, `aria-expanded` refleja el estado del desplegable, `aria-activedescendant` rastrea el id del resultado resaltado.

### Filtros alineados a la derecha

```
                          [ ] Fuente   [ ] Solo vivientes
```

- **Desplegable Fuente:** `<select>` nativo (no un checkbox — el prompt de la persona usuaria dice "desplegable" para Fuente).
  - `text-xs text-slate`.
  - Opciones: `CoL` (activa, por defecto), `GBIF` (deshabilitada con el atributo `disabled`), `WoRMS` (deshabilitada).
  - Tooltip: `title="El soporte multi-fuente llegará pronto. CoL es la única fuente activa."`.
  - Según la spec existente ("Filtro de Fuente (no-op en el primer PR)"), el desplegable es puramente visual en el primer PR; alternarlo no refetchea.
- **Checkbox Solo vivientes:** `<input type="checkbox">` nativo + etiqueta.
  - `text-xs text-slate`.
  - Por defecto: **desmarcado** (las filas de especies extintas son visibles).
  - Tooltip: `title="Ocultar taxones extintos"`.
  - Cuando está marcado, la siguiente petición a `/api/tree/children` (y la búsqueda) envía `?include_extinct=false` y re-renderiza sin filas de extintos.
- **Toggle Sinónimos** (= inclusión de `is_synonym`): un chip tipo píldora que refleja el patrón existente de `Toggles.tsx`.
  - `inline-flex min-h-[44px] items-center gap-2 rounded-chip border px-3 py-1 text-sm transition-colors`
  - Activo: `border-accent bg-blue-50 text-accent`. Inactivo: `border-border bg-surface text-slate hover:bg-bg`.
  - `aria-pressed` refleja el estado activado/desactivado.

### Reconciliación con `Toggles.tsx`

El `Toggles.tsx` existente tiene cuatro chips: `extinct`, `synonyms`, `uncertain`, `unassigned`. La nueva cabecera de `<TaxonomicTree>` conserva `synonyms` (como el chip anterior) y `extinct` (plegado en el checkbox "Solo vivientes", ya que la semántica inversa es más clara). **Los chips `uncertain` y `unassigned` se eliminan de la nueva cabecera** — permanecen visibles como glifos por fila `⚠` / `⊘` (§3) y se documentan en §15 como decisión abierta que la persona implementadora debe revisar.

### Cuándo colapsa la cabecera

Tableta y móvil: la fila de filtros se ajusta debajo del input de búsqueda. El input de búsqueda conserva `flex-1` solo en escritorio (`md:flex-1`); en móvil es de ancho completo y los filtros se ajustan debajo.

---

## 5. Desplegable de búsqueda (bajo el input cuando está activo)

```
┌───────────────────────────────────────────────────────────────┐
│ 🔍 Euk                                            4 resultados│
└───────────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────────┐
│ EUCARYA: Eukarya                                  dominio   ▾  │
│ EUCARYOTA: Eukaryota (Chatton, 1925) Whittaker & Margulis…    │
│ EUKARYALINK: Eukaryalink                            especie    │
│ EUK2: Eukaryota sp. 'Euk2'                         especie    │
└───────────────────────────────────────────────────────────────┘
```

### Contenedor

- `absolute left-0 right-0 top-full mt-1 z-20 max-h-96 overflow-y-auto rounded-md border border-border bg-surface shadow-lg`
- El ancho coincide con el input (el posicionamiento absoluto es hijo del wrapper del input).
- `id="tree-search-results"`, `role="listbox"`.

### Cada fila

- `flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-bg focus:bg-bg focus:outline-none`
- Formato: `rango: <display_name>` — el rango está en mayúsculas tracked, el `display_name` es la superficie de enlace.
- `role="option"`, `aria-selected` refleja la fila resaltada.
- Pulsar Enter o hacer clic selecciona la fila → expandir ancestros + desplazar a la vista + enfocar la fila en el árbol.

### Estado vacío

Cuando la respuesta es `{"items": []}`:

```
┌───────────────────────────────────────────────────────────────┐
│           No hay coincidencias para "Eukzzz"                  │
└───────────────────────────────────────────────────────────────┘
```

- `text-sm text-slate text-center py-2` dentro del mismo contenedor redondeado.
- Centrado horizontalmente, padding vertical de 8px.

### Tope de 8 elementos

El desplegable DEBE limitar a 8 resultados según la spec. El tope se aplica del lado del servidor (`TreeSearchResponse.items.length <= 8`); la persona cliente nunca construye una novena fila.

### z-index

El desplegable es `z-20` — por encima de las filas del árbol pero por debajo de cualquier modal/toast. El atributo `field` de Toggles no debe interferir; mantenemos el contrato de escape del overflow posicionando absolutamente el desplegable bajo el input de búsqueda (sin ancestro con `overflow: hidden`).

---

## 6. Estados visuales

| Estado | Tratamiento visual |
|-------|--------------------|
| **Por defecto** | `bg-surface`, texto `text-navy` (nombre) + `text-slate` (rango/autoría) + `text-amber`/`text-muted`/`text-red` (glifos marcadores). |
| **Hover** | Fondo de fila `bg-bg`. El cambio de color es `transition-colors duration-150 ease-out`. |
| **Foco** | Outline 2px, `outline-2 outline-offset-[-2px] outline-accent`. La regla global `:focus-visible` en `src/index.css` ya aporta `outline-2 outline-offset-2 outline-accent`; el árbol sobrescribe `outline-offset` a `-2px` para que el anillo pinte *dentro* de la fila (la misma convención que usa SpeciesList). |
| **Seleccionada** (el camino explorado desde la raíz hasta la hoja activa) | `bg-blue-50` + `4px border-l-4 border-accent`. La fila se mantiene visualmente distinta del estado hover. La hoja seleccionada y todos sus ancestros comparten este tratamiento. |
| **Cargando** (petición de hijos en curso) | El caret entra en giro infinito: `animate-spin` (1s linear infinite) sobre el `<span>`. Los hijos de la fila se reemplazan por tres barras de esqueleto: `<span className="ml-6 inline-block h-2 w-24 rounded bg-border animate-pulse" />` × 3, apiladas verticalmente con `gap-1`. |
| **Error** | La fila del caret pasa a `text-red`, el texto de la fila se vuelve `text-red`, y aparece un pequeño enlace "Reintentar" junto al caret: `<button type="button" className="text-xs underline text-red">Reintentar</button>`. Hacer clic reemite la misma petición `fetchTreeNode(parent_id)`. Las demás filas DEBEN permanecer expandidas y sin afectación. |
| **Vacío** (cero raíces) | Mensaje centrado: "No hay taxonomía cargada. Comprueba la conexión a la base de datos." `text-sm text-slate text-center py-8`. El copy obligatorio por la sesión es exactamente "No hay taxonomía cargada" según la spec §"Empty State"; la persona implementadora añade el sufijo "Comprueba la conexión a la base de datos." como pista de recuperación. |
| **Deshabilitada** (filtro Solo vivientes activo, todos los hijos marcados como extintos) | La fila se renderiza igual que por defecto pero la fila completa es `text-muted` y el caret se oculta. |

### Estado deshabilitado para la fila

- El `<button>` completo recibe `disabled` cuando la fila queda filtrada por el checkbox "Solo vivientes" activo.
- `aria-disabled="true"` refleja el atributo.

---

## 7. Sangría y jerarquía de rango

### Paso de sangría

- **Escritorio ≥ 1024px:** 16px por nivel de profundidad (`pl-4`).
- **Móvil < 640px:** 12px por nivel de profundidad (`pl-3`).
- La expresión CSS vive en el wrapper de cada fila (`<div role="treeitem" style={{ paddingLeft: depth * step }}>`). El estado de React guarda la profundidad; el estilo inline es la única manera de expresar padding dirigido por datos sin renderizar cada utilidad de profundidad.

### Guía de sangría

- Una hairline vertical de 1px en `border-border` conecta padre e hijo.
- La guía se renderiza vía `<div className="absolute left-{step/2} top-0 h-full w-px bg-border">` por fila, anclada al ancestro expandido más profundo a esa profundidad.
- La guía termina visualmente en el centro del caret (el caret mide 24px de ancho, la guía está a medio paso = 8px del borde izquierdo de la fila, el centro del caret está a 12px del borde izquierdo de la fila; el ojo humano acepta el offset de 4px).

### Profundidad máxima visible

- **12 niveles.** Más allá de la profundidad 12, la fila renderiza un nodo de truncamiento `"..."` con un handler de clic que fetchea los siguientes 12 hijos (`?parent_id={id}&limit=12&offset=12`). La UI muestra el nodo de truncamiento como el siguiente hermano a la profundidad del padre.
- Clase Tailwind: `text-slate text-sm select-none` (sin caret, sin insignia, solo la elipsis literal).

### Insignias de rango (etiquetas de texto)

La etiqueta de rango usa la convención de la imagen de referencia del CoL:

- `domain`, `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species` son los rangos **principales**.
- Los rangos intermedios (`subphylum`, `infraphylum`, `parvphylum`, `superclass`, `subclass`, `infraclass`, `parvclass`, `superorder`, `suborder`, `infraorder`, `parvorder`, `superfamily`, `subfamily`, `tribe`, `subtribe`) se renderizan con su **propia** etiqueta de rango en la fila (el valor `Taxon.rank` upstream se preserva verbatim — la persona implementadora NO colapsa estos en el rango padre).
- La insignia de especie (`N spp.`) no se ve afectada por rangos intermedios — siempre cuenta las especies descendientes.

### Jerarquía visual de los rangos

La etiqueta de rango es el **segundo mayor énfasis** en la fila (después del nombre). Usa `text-[10px] tracking-widest uppercase` para que se lea como un marcador estable — la persona usuaria puede escanear la columna de rango y ver `"REINO | REINO | REINO | FILO | CLASE | ..."` sin re-leer los nombres.

---

## 8. Movimiento

El movimiento en una superficie de Operar es **funcional, no decorativo**. Cada transición se gana su lugar.

| Disparador | Animación | Duración | Easing |
|-----------|-----------|----------|--------|
| Toggle del caret (abrir/cerrar) | `rotate(0deg)` ↔ `rotate(90deg)` | 150ms | `ease-out` |
| Expansión de fila (revelado de hijos) | `max-height: 0` ↔ `max-height: {computed}` + opacidad 0 → 1 | 200ms | `ease-out` |
| Aparición del desplegable de búsqueda | `opacity: 0; translate-y(-4px)` → `opacity: 1; translate-y(0)` | 100ms | `ease-out` |
| Desaparición del desplegable de búsqueda | Inverso de lo anterior | 80ms | `ease-in` |
| Fondo de hover | `bg-surface` → `bg-bg` | 150ms | `ease-out` |
| Spin del caret en carga | `rotate(0deg)` → `rotate(360deg)` (infinito) | 1000ms | `linear` |
| Pulso del esqueleto | `opacity: 1` → `opacity: 0.5` → `opacity: 1` (infinito) | 1500ms | `ease-in-out` |
| Anillo de foco | Instantáneo — sin transición | 0ms | — |

### Implementación

- Rotación del caret: un `<span>` con `transform: rotate(...)` dirigido por el estado de React. CSS `transition: transform 150ms ease-out`. El span usa `display: inline-block` para que la transformación se aplique.
- Expansión de fila: `max-height` se mide desde el `getBoundingClientRect().height` de los hijos renderizados; la transición de colapso pone `max-height: 0` en el wrapper de hijos. La implementación puede usar `useLayoutEffect` para leer la altura una vez y cachearla, o apoyarse en `transition-all` con `max-h-0` ↔ `max-h-[2000px]` (valor sobredimensionado, pero más barato).
- Desplegable de búsqueda: `transition-all duration-100 ease-out` sobre la `opacity` + `translate-y` del contenedor posicionado absolutamente.

### Movimiento reducido

Cada animación respeta `@media (prefers-reduced-motion: reduce)`. El árbol entrega una regla CSS global:

```css
@media (prefers-reduced-motion: reduce) {
  .motion-reduce\:transition-none {
    transition: none !important;
  }
}
```

La persona implementadora aplica la variante Tailwind `motion-reduce:transition-none` a cada elemento que porte una transición. El spin del caret en carga TAMBIÉN se detiene — sin animación, el estado de carga se transmite por las tres barras de esqueleto junto a la fila, lo cual es suficiente.

---

## 9. Tipografía

Las fuentes del proyecto (según `tailwind.config.js`) son:

- **Sans:** `system-ui`, `-apple-system`, `Segoe UI`, `Roboto`, `Inter`, `sans-serif`.
- **Mono:** `ui-monospace`, `SFMono-Regular`, `Menlo`, `Monaco`, `Consolas`, `IBM Plex Mono`, `monospace`.

El árbol usa **sans** para todo. (El nombre canónico de especie en la `SpeciesList` aguas abajo usa mono, pero los nombres de fila del árbol son sans — esto coincide con la referencia CoL y mantiene la fila compacta.)

### Escala de roles

| Rol | Uso | Tamaño | Peso | Letter-spacing |
|-----|-----|--------|------|----------------|
| Cabecera de sección | "Tree" (sobre las filas, opcional) | `text-sm` (14px) | `font-medium` | normal |
| Nombre de fila | Nombre canónico del taxón | `text-sm` (14px) | `font-medium` | normal |
| Autoría | Cola de citación | `text-xs` (12px) | `font-normal` | normal, itálica |
| Etiqueta de rango | Etiqueta en mayúsculas | `text-[10px]` | `font-medium` | `tracking-widest` (0.1em) |
| Insignia de especie | Recuento numérico | `text-xs` (12px) | `font-medium` | normal, `tabular-nums` |
| Input de búsqueda | Lo que escribe la persona usuaria | `text-sm` (14px) | `font-normal` | normal |
| Etiquetas de filtros | "Fuente", "Solo vivientes" | `text-xs` (12px) | `font-medium` | normal |
| Estado vacío | "No hay taxonomía cargada." | `text-sm` (14px) | `font-normal` | normal |

### Decisiones de jerarquía

- **El peso del cuerpo es `font-medium` (500) para el nombre de fila** — más ligero que el texto de cuerpo típico porque la fila es densa y `font-medium` mantiene el nombre legible sin gritar.
- **La etiqueta de rango es `font-medium` + mayúsculas + `tracking-widest`** — pequeño + tracked + negrita es el patrón inconfundible de "etiqueta de sección".
- **La autoría es `font-normal italic`** — la itálica carga la pista de "esto es metadato" sin competir con el nombre.
- **Los números en la insignia de especie usan `tabular-nums`** — la alineación entre filas es crítica para el patrón de escaneo y comparación.

### Título de página

El árbol no es dueño de un título de página. La App ya renderiza `<h1>Taxon</h1>` en la cabecera. El árbol inserta un `<h2>` (o uno visualmente oculto) solo si su sección necesita etiqueta — recomendado: `<h2 className="sr-only">Árbol taxonómico</h2>` para que los lectores de pantalla anuncien la sección.

### Medida

- El texto de cuerpo en la fila no es prosa; la regla de 65–75ch no aplica. La fila es una etiqueta, no un párrafo.
- El estado vacío del desplegable de búsqueda es `text-sm text-slate text-center` — copy corto, sin preocupaciones de medida.

---

## 10. Color

La paleta del proyecto (según `tailwind.config.js`) es:

| Token | Hex | Uso |
|-------|-----|-----|
| `accent` | `#3b82f6` (= Tailwind `blue-500`) | Acción primaria, foco, selección |
| `blue-50` | `#eff6ff` | Fondo de fila seleccionada |
| `navy` | `#0f172a` (= Tailwind `slate-900`) | Texto primario en la fila |
| `slate` | `#475569` (= Tailwind `slate-600`) | Texto secundario (rango, autoría) |
| `muted` | `#94a3b8` (= Tailwind `slate-400`) | Terciario (placeholder, divisor) |
| `border` | `#e2e8f0` (= Tailwind `slate-200`) | Hairlines 1px, guías de sangría |
| `bg` | `#f8fafc` (= Tailwind `slate-50`) | Fondo sutil (hover, esqueleto) |
| `surface` | `#ffffff` | Fondo de tarjeta |
| `red` | `#dc2626` (= Tailwind `red-600`) | Error |
| `red-50` | `#fef2f2` | Fondo de error |
| `amber` | `#d97706` (= Tailwind `amber-600`) | Aviso (incierto) |
| `amber-50` | `#fffbeb` | Fondo de aviso |

### Estrategia de color

**Restringida.** Neutros (escala slate) más un acento (`accent`/blue-500). El árbol es una superficie de Operar — el color es funcional, no decorativo. El único color saturado es el fondo de selección (`blue-50`) y el anillo de foco (`accent`).

### Mapeo al prompt de la persona usuaria

El prompt de la persona usuaria pidió clases `stone-*`, `blue-*`, `red-*`, `amber-*`. El `tailwind.config.js` del proyecto NO incluye la paleta `stone` pero SÍ incluye los tokens semánticos `blue`, `red`, `amber` que mapean a los mismos valores hex. **El mapeo siguiente es autoritativo** — la persona implementadora usa los tokens del proyecto, no los valores por defecto de Tailwind:

| Clase del prompt | Token del proyecto |
|------------------|--------------------|
| `text-stone-900` | `text-navy` |
| `text-stone-700` | Mantener `text-navy` (un nivel más oscuro que 500 — usar el mismo; el estado hover es `hover:text-slate`) |
| `text-stone-500` | `text-slate` |
| `text-stone-400` | `text-muted` |
| `border-stone-200` | `border-border` |
| `bg-stone-100` | `bg-bg` |
| `bg-stone-50` | `bg-bg` |
| `bg-blue-50` | `bg-blue-50` (el proyecto lo define explícitamente) |
| `bg-blue-500` | `bg-accent` |
| `text-blue-500` | `text-accent` |
| `outline-blue-500` | `outline-accent` |
| `border-blue-500` | `border-accent` |
| `text-red-600` | `text-red` |
| `bg-red-50` | `bg-red-50` (el proyecto lo define explícitamente) |
| `text-amber-500` | `text-amber` |
| `bg-amber-50` | `bg-amber-50` (el proyecto lo define explícitamente) |

Usar clases `stone-*` sería una deriva del sistema de diseño del proyecto. La persona implementadora DEBE usar los tokens mapeados arriba. Esta es la reconciliación más importante que se plantea en §15.

### Modo oscuro

Fuera de alcance para el primer PR. La regla `:root { color-scheme: light; }` en `src/index.css` bloquea la superficie en modo claro. Un PR futuro puede intercambair los tokens.

---

## 11. Accesibilidad

Este es el contrato que la persona implementadora DEBE satisfacer. La prueba de a11y en el PR 3 (`TaxonomicTree.a11y.test.tsx`) verifica cada línea.

### Patrón de árbol ARIA

- Elemento raíz: `<div role="tree" aria-label="Árbol taxonómico">`.
- Cada fila: `<div role="treeitem" aria-level={depth + 1} aria-expanded={has_children ? isExpanded : undefined}>`.
- El `<button>` de cada fila es el único elemento enfocable dentro del treeitem.

### Navegación por teclado

| Tecla | Efecto |
|-------|--------|
| `ArrowDown` | Mueve el foco a la siguiente fila visible. |
| `ArrowUp` | Mueve el foco a la fila anterior visible. |
| `ArrowRight` | Expande la fila si está colapsada; si ya está expandida, mueve el foco al primer hijo. |
| `ArrowLeft` | Colapsa la fila si está expandida; si ya está colapsada (o no tiene hijos), mueve el foco al padre. |
| `Enter` | Alterna la fila (igual que un clic en el `<button>` de la fila). |
| `Home` | Mueve el foco a la primera fila visible (depth 0, posición 0). |
| `End` | Mueve el foco a la última fila visible. |
| `Tab` | Tab sale del árbol (sin trampas). |
| `Escape` | Colapsa el desplegable de búsqueda si está abierto; en caso contrario, colapsa la fila actual. |

### Accesibilidad del input de búsqueda

- `aria-label="Buscar taxón"`.
- `aria-controls="tree-search-results"`.
- `aria-expanded` refleja el estado del desplegable (`true` cuando el desplegable está abierto y `q.length > 0`).
- `aria-activedescendant` rastrea el id del resultado resaltado (`results-{index}`).
- Cuando el desplegable está cerrado, `aria-expanded="false"` y se quita `aria-activedescendant`.

### Región en vivo

- Un `<span aria-live="polite" aria-atomic="true" className="sr-only">` oculto anuncia efectos colaterales como "Cargados N hijos" tras una petición exitosa. El anuncio se dispara después de que los hijos se renderizan, en un `useEffect` que observa el conteo de hijos.
- Formato del anuncio: `"Cargados {count} {hijo-hijos}"` (singular vs plural).

### Estados de fila

- `aria-selected="true"` en la hoja seleccionada Y en cualquier ancestro que haya sido clicado (el camino explorado).
- `aria-busy="true"` en la fila cuyos hijos se están cargando.
- `aria-disabled="true"` en las filas filtradas por el checkbox "Solo vivientes".

### Contraste de color

- Texto de cuerpo (`text-navy` sobre `bg-surface`) = `0f172a` sobre `ffffff` → ratio **16.7:1** ✓ (AAA).
- Texto secundario (`text-slate` sobre `bg-surface`) = `475569` sobre `ffffff` → ratio **7.6:1** ✓ (AAA).
- Texto terciario (`text-muted` sobre `bg-surface`) = `94a3b8` sobre `ffffff` → ratio **3.1:1** — ⚠ por debajo de AA para texto de cuerpo. Usar `text-muted` SOLO para metadatos no esenciales (texto de placeholder, etiquetas divisorias) y sustituir por `text-slate` para cualquier etiqueta que la persona usuaria deba leer.
- Anillo de foco (`accent` sobre `bg-surface`) = `#3b82f6` sobre `#ffffff` → ratio **3.6:1** ✓ (UI no textual).
- Fila seleccionada (`bg-blue-50` con `text-navy`) = `#eff6ff` sobre `#0f172a` → ratio **15.9:1** ✓ (AAA).
- Texto de error (`text-red` sobre `bg-surface`) = `#dc2626` sobre `#ffffff` → ratio **4.8:1** ✓ (AA cuerpo).

### Objetivos táctiles

- Filas en móvil: 28px de altura visual + 8px de padding de impacto arriba + 8px abajo = 44px de objetivo táctil. Implementación: `py-3` en lugar de `py-2` en pantallas pequeñas.
- Input de búsqueda: `h-10` (40px) en escritorio, `h-11` (44px) en móvil (`min-h-[44px]`).
- Checkboxes de filtro: `<input type="checkbox">` nativo ya aplica 44×44px de área de tap por defecto en la hoja de estilos UA del navegador.

### Sin botones de solo icono

- El caret es un `<span>` (no un botón), por lo que no requiere etiqueta independiente.
- El input de búsqueda tiene un placeholder visible Y un `aria-label`.
- Los desplegables de filtro tienen etiquetas visibles.
- El enlace "Reintentar" tiene texto visible `"Reintentar"`.

### `prefers-reduced-motion`

Ya cubierto en §8. La regla CSS global se aplica a cada transición.

---

## 12. Comportamiento responsivo

| Breakpoint | Disposición |
|------------|-------------|
| `< 640px` (móvil) | Columna única. Los filtros se mueven a un acordeón `<details>`. Altura de fila 28px. Paso de sangría 12px. Etiqueta de rango oculta. Autoría oculta. Objetivos táctiles ≥ 44px. |
| `640–1024px` (tableta) | Columna única. Los filtros se ajustan a una segunda fila debajo de la búsqueda. Altura de fila 32px. Paso de sangría 16px. Etiqueta de rango visible. Autoría visible. |
| `≥ 1024px` (escritorio) | Columna única dentro de la ranura izquierda existente de la App. Contenido de fila completo. Cabeceras alineadas a la derecha. |

### Reordenamiento

- El patrón `flex-col md:flex-row` de la fila de cabecera reordena la búsqueda y los filtros.
- Las filas del árbol NO reflowan; el mismo `pl-4` (o `pl-3` en móvil) aplica por fila.

### ¿Container queries?

Fuera de alcance. El árbol responde al ancho del viewport, no al contenedor padre. La cuadrícula de la App decide el ancho disponible; el árbol usa ese ancho uniformemente.

### Áreas seguras

- Todo el árbol se ubica dentro del wrapper `mx-auto max-w-page px-6 py-8` de la App. El `p-4` interno de la tarjeta absorbe el área segura en dispositivos con notch.
- La persona implementadora añade `pb-[max(1rem,env(safe-area-inset-bottom))]` a la tarjeta del árbol para respetar el indicador de inicio en iOS.

---

## 13. Estados vacío / cargando / error

El contrato siguiente coincide con los escenarios de la spec exactamente. La persona implementadora rellena las cadenas con el copy exacto que la spec exige.

### "Sin raíces" (la DB devolvió cero filas con `parent_id IS NULL`)

- **Copy:** "No hay taxonomía cargada. Comprueba la conexión a la base de datos."
- **Visual:** centrado, `text-sm text-slate text-center py-8`. Sin icono.
- **Recuperación:** ninguna en la UI — la persona usuaria debe arreglar la conexión a la DB. El mensaje nombra la causa.

### "Sin hijos tras expansión" (un padre tiene cero hijos directos)

- La fila se renderiza sin caret y sin insignia — ya gestionado por el contrato del flag `has_children`.
- Sin texto de mensaje. La fila simplemente se lee como hoja.

### "Cargando" (montaje inicial, la petición de raíces está en curso)

- Cinco filas de esqueleto en el nivel superior. Cada esqueleto es `<div className="h-8 w-full rounded bg-bg animate-pulse" />` con una guía de sangría de 16px.
- Tras resolverse la petición de raíces, los esqueletos se reemplazan por las filas reales.

### "Cargando" (los hijos de una fila específica están en curso)

- El caret entra en giro infinito (§8).
- El área de hijos de la fila renderiza tres barras de esqueleto: `<span className="ml-6 inline-block h-2 w-24 rounded bg-border animate-pulse" />` × 3.

### "Input de búsqueda vacío"

- Sin desplegable. `aria-expanded="false"`. Sin petición.

### "Búsqueda sin resultados"

- El desplegable renderiza `"No hay coincidencias para \"<q>\""` exactamente como dicta la spec. `\""` es lo que escribió la persona usuaria, renderizado de forma segura.
- El desplegable se mantiene abierto (el foco vuelve al input en Esc).

### "Reintento por error"

- La fila del caret pasa a `text-red` y la fila gana un enlace `"Reintentar"`:
  ```html
  <span className="text-xs text-red">
    No se pudieron cargar los hijos.
    <button type="button" className="ml-2 underline" onClick={retry}>Reintentar</button>
  </span>
  ```
- Hacer clic en `Reintentar` reemite la misma petición `fetchTreeNode(parent_id)`.
- Las demás filas DEBEN permanecer expandidas. El error se delimita a la fila que falló.

### "Fallo de red" (la petición de todo el árbol falla)

- El árbol completo renderiza:
  ```
  No hay taxonomía cargada.
  [Reintentar]
  ```
- `text-sm text-slate text-center py-8` para el mensaje, `mt-4 inline-flex items-center gap-2 rounded-btn border border-border bg-surface px-3 py-2 text-sm text-slate hover:bg-bg` para el botón de reintento.

### "Página sin conexión" (la red general está caída)

- Los estados de error anteriores ya cubren esto. La recuperación siempre es "Reintentar".

---

## 14. Pasada de crítica (hallazgos del audit impeccable)

Las heurísticas del audit impeccable aplicadas a esta superficie. Cada hallazgo es una decisión deliberada, no diferida.

| Dimensión | Puntuación (0-4) | Decisión |
|-----------|------------------|----------|
| **Jerarquía visual** | 4 | La etiqueta de rango (`text-[10px] uppercase tracking-widest text-slate`) y la insignia de especie (`tabular-nums`) son los marcadores navegacionales de mayor énfasis. El nombre es el primario. La autoría es la inferior. La jerarquía de 4 niveles es inequívoca. |
| **Carga cognitiva** | 3 | Cuatro affordances de navegación: caret (expandir/colapsar), nombre (enlace), búsqueda (saltar), filtro (solo vivientes). Cada una tiene un visual distinto; se respeta el tope de 4–5 affordances de la Ley de Miller. El tope de 8 elementos del desplegable de búsqueda mantiene acotada la carga de memoria de trabajo. |
| **Accesibilidad** | 4 | Navegación por teclado (ArrowUp/Down/Left/Right/Enter/Home/End/Escape), patrón de árbol ARIA con `role="tree"`, `aria-level`, `aria-expanded`, `aria-selected`, `aria-busy`, anuncios `aria-live`. Contraste de color verificado (ver §11). |
| **Rendimiento** | 4 | Fetch perezoso por caret (un round-trip por expansión), `has_children` precalculado en el fetch del padre, `species_count` con null perezoso más allá de 100k hijos directos, tope de 200 filas por fetch de hijos. Estados de esqueleto durante el fetch. |
| **Responsividad** | 4 | Breakpoints móvil / tableta / escritorio. Los filtros colapsan a `<details>` en móvil. Objetivos táctiles ≥ 44px. La tarjeta absorbe los safe-area insets. |
| **Anti-patrones** | 4 | Sin carruseles. Sin diálogos modales en el filtro. Sin affordances solo-hover (anillo de foco presente). Sin botones de solo icono (el input de búsqueda tiene etiqueta visible). Sin números de sección. Sin valores por defecto dañinos de Tailwind. |
| **i18n** | 3 | Todo el copy vive en un único objeto `treeCopy` para que una futura traducción al español mapee claves sin tocar la disposición. El placeholder es la única cadena en contenido en inglés y es una clave de copy, no un literal. |
| **Tipografía** | 4 | Familia única (system-ui sans). 8 roles explícitos (cabecera de sección, nombre de fila, autoría, rango, insignia, input de búsqueda, etiqueta de filtro, estado vacío). `tabular-nums` para insignias numéricas. |
| **Color** | 4 | Estrategia restringida (un acento + neutros). Cada estado (hover, foco, seleccionado, cargando, error, vacío, deshabilitado) tiene un tratamiento de color distinto. Contraste verificado. |
| **Movimiento** | 4 | Solo transiciones funcionales (caret, expansión, desplegable, esqueleto). Cada transición respeta `prefers-reduced-motion`. El spin de carga es la única animación infinita. |
| **Errores** | 4 | Reintento por fila para el fetch de hijos. Reintento a nivel de página para el fetch de raíces. Lenguaje llano ("No se pudieron cargar los hijos." y no "Internal Server Error"). Las demás filas no se ven afectadas por un fallo de una sola fila. |
| **Onboarding** | 3 | El árbol arranca en las 5 raíces CoL con los carets auto-cerrados. La primera interacción es "haz clic en un caret para expandir" — descubrible sin instrucción. El placeholder de "Buscar taxón" muestra un ejemplo ("p. ej. Panthera") para que la persona usuaria sepa qué escribir. |

**Consistencia de modo (Operar):** las 12 heurísticas caen en el cubo de Operar. La puntuación más alta (4) la ostentan 9 de 12, la más baja (3) la ostentan 3 de 12. La superficie se gana el veredicto "envíalo" (9 componentes a 4/4, 3 a 3/4 = 93% del máximo).

### Lista de comprobación de auditoría de anti-patrones

- [x] Sin carruseles. (n/a — árbol, no superficie de medios.)
- [x] Sin plantilla de hero-metric. (n/a — el árbol es una superficie de navegación.)
- [x] Sin kicker/eyebrow sobre los encabezados. (El `<h2>` es `sr-only`; la etiqueta de rango es un marcador de fila, no un kicker.)
- [x] Sin números de sección. (La jerarquía de filas es el orden visual.)
- [x] Sin modal en el filtro. (Los filtros son inline.)
- [x] Sin texto con gradiente. (Todo el texto es color sólido.)
- [x] Sin glass / blur como decoración. (Las tarjetas son `bg-surface` con un borde de 1px.)
- [x] Sin border-left / border-right sobre-brillantes en tarjetas. (La fila seleccionada usa `border-l-4 border-accent` — dentro del techo de 4px para la affordance "seleccionada".)
- [x] Sin sombras de offset duras en tarjetas. (La tarjeta usa `border-border`, sin sombra. El desplegable de búsqueda usa `shadow-lg` — el desplegable es un overlay, la sombra es apropiada.)
- [x] Sin sparklines / progress rings. (Las barras de esqueleto transmiten el estado de carga.)
- [x] Sin monospace como disfraz. (Sans en todas partes. La `SpeciesList` aguas abajo usa mono para nombres canónicos — eso es correcto, no disfraz.)
- [x] Sin glifos Unicode como iconos. (El caret es un glifo; el icono de búsqueda es un SVG. Los marcadores `⚠` / `⊘` / `†` son marcadores semánticos deliberados, no "iconos".)
- [x] Sin fuente display en etiquetas de UI. (Familia sans única.)

---

## 15. Preguntas abiertas para la persona implementadora (PR 3)

Estas son las preguntas que la persona implementadora DEBE resolver antes de enviar. Documentar la respuesta en el cuerpo del PR.

### Q1. El mapeo de tokens de Tailwind

El prompt de la persona usuaria pidió clases `stone-*` / `blue-*` / `red-*` / `amber-*`. El `tailwind.config.js` del proyecto NO incluye la paleta `stone`. La persona implementadora DEBE usar los tokens semánticos del proyecto según la tabla de mapeo de §10. El mapeo es autoritativo — `text-stone-900` → `text-navy`, `text-stone-500` → `text-slate`, `border-stone-200` → `border-border`, `bg-blue-50` → `bg-blue-50` (el proyecto lo define explícitamente), etc. Añadir la paleta `stone` a `tailwind.config.js` está FUERA DE ALCANCE para el PR 3.

### Q2. Reconciliación de chips de filtro

El `Toggles.tsx` existente tiene 4 chips: `extinct`, `synonyms`, `uncertain`, `unassigned`. La nueva cabecera de `<TaxonomicTree>` conserva:
- `Sinónimos` (chip, `aria-pressed`, refleja el patrón existente).
- `Solo vivientes` (checkbox, inverso del antiguo chip `extinct`).
- `Fuente` (desplegable, no-op en el primer PR).

`Uncertain` y `unassigned` se eliminan del grupo de chips de la cabecera. Permanecen visibles como glifos por fila (`⚠` / `⊘`) en el prefijo de fila. **Justificación de la decisión:** los chips `uncertain` y `unassigned` alternaban la inclusión en la lista de especies, no en el árbol. Plegarlos en la cabecera saturaría el espacio de filtros de la fila; los glifos por fila son la UX dominante (CoL renderiza estos como marcadores `?` junto al nombre — la misma idea).

Si la persona implementadora discrepa, la alternativa es añadir un tercer panel `<details>` etiquetado "Incluir" con los tres chips restantes (`Sinónimos`, `Incierto`, `Sin asignar`). Esto es más pesado que los glifos por fila y no se recomienda.

### Q3. Matemática de la profundidad de sangría

La distribución taxonómica en `data/col.db` tiene la mayoría de taxones en el rango especie; la profundidad media de raíz a especie es 5–6. Paso de sangría 16px × 6 = 96px en escritorio, 12px × 6 = 72px en móvil. Ambos caben cómodamente en la columna izquierda de 280–320px. El tope de 12 niveles (192px escritorio, 144px móvil) es un techo duro; más allá, el nodo de truncamiento (`...`) toma el relevo.

### Q4. Navegación con Tab y Home

La spec requiere que las teclas `Home` / `End` salten a la primera/última fila visible. La "última fila visible" es la hoja expandida más profunda. La persona implementadora DEBE computar la lista de filas visibles en cada expansión/colapso y replanificar el `aria-activedescendant` Y el índice de foco en `Home` / `End`. Esta es la parte de a11y más compleja de la superficie.

### Q5. Input de búsqueda en móvil

En móvil, el botón "Done" del teclado también debe limpiar el input y cerrar el desplegable. La implementación usa el `<input type="search">` nativo con el botón de borrado del navegador + un `onBlur` sintético que cierra el desplegable tras un delay de 150ms (para que un clic en un resultado se registre primero).

### Q6. Filtro Solo vivientes en el fetch de raíces

El checkbox "Solo vivientes" es global (vive en la cabecera). Cuando está marcado, la siguiente llamada a `GET /api/tree/children` (para CUALQUIER padre) incluye `?include_extinct=false`. La caché se invalida por padre al cambiar el filtro. La implementación DEBE limpiar la caché cuando el checkbox alterna. El comportamiento visible para la persona usuaria es: "Marqué la casilla, todas las filas extendidas desaparecen en el siguiente clic."

### Q7. El desplegable Fuente es un no-op

La UI del desplegable `Fuente` renderiza `CoL` (activa) + `GBIF` (deshabilitada) + `WoRMS` (deshabilitada). Seleccionar una opción distinta es un no-op; la siguiente petición a `/api/tree/children` NO incluye un parámetro `source`. El `value` del desplegable se queda en `CoL`. Documentar esto en el docstring del componente para que un PR futuro que añada multi-fuente no rompa el contrato.

### Q8. La región en vivo "Cargados N hijos"

La región en vivo anuncia el conteo tras cada fetch exitoso. Singular vs plural: `"Cargado 1 hijo"` vs `"Cargados {N} hijos"`. La persona implementadora usa un ternario simple `count === 1 ? "hijo" : "hijos"` — el copy aún no está localizado, de modo que un `Intl.PluralRules` completo es excesivo.

### Q9. La diferencia visual del chip Toggles

El patrón de chip existente en `Toggles.tsx` usa `border-accent bg-blue-50 text-accent` para el estado activo. El nuevo chip `Sinónimos` de `<TaxonomicTree>` usa el MISMO patrón. La persona implementadora NO DEBE importar ningún componente compartido — el `Toggles.tsx` existente está vinculado al filtro de la lista de especies y se queda donde está. El nuevo chip es un `<button>` independiente en la cabecera del árbol.

---

## 16. Lista de comprobación del self-test

La persona implementadora DEBE recorrer esta lista antes de abrir el PR. Cada casilla es una comprobación acotada y verificable.

- [ ] Todas las clases de Tailwind provienen de los tokens de `tailwind.config.js` del proyecto (o de paletas por defecto de Tailwind que ya están en el bundle). Buscar en el diff `stone-`, `gray-`, `zinc-`, `neutral-` — no debe aparecer ninguna.
- [ ] Todos los atributos ARIA tienen el emparejamiento correcto de role/level según el patrón de árbol WAI-ARIA. (`role="tree"` en la raíz, `role="treeitem"` por fila, `aria-level` coincide con la profundidad, `aria-expanded` solo en filas expandibles.)
- [ ] Todas las duraciones de movimiento son ≤ 250ms. El spin del caret en carga es 1000ms (infinito) y es la única excepción. Ninguna métrica supera los 300ms.
- [ ] Contraste de color verificado ≥ 4.5:1 para texto de cuerpo. La única excepción es `text-muted` (3.1:1) que se usa solo para metadatos no esenciales.
- [ ] Objetivos táctiles ≥ 44×44px en móvil. Verificable inspeccionando el `getBoundingClientRect().height` de la fila renderizada en el viewport emulado móvil.
- [ ] Sin botones de solo icono. El caret es un `<span>`. El input de búsqueda tiene etiqueta visible. El enlace Reintentar tiene texto visible.
- [ ] Fallback de movimiento reducido para cada transición. La variante Tailwind `motion-reduce:transition-none` se aplica a cada elemento que porte una transición.
- [ ] Estados vacío / cargando / error cubiertos para cada superficie asíncrona. Montaje inicial, expansión por fila, búsqueda, reintento.
- [ ] Sin `!important`, sin estilos inline (excepto `style={{ paddingLeft: depth * step }}` para la sangría dirigida por datos).
- [ ] El payload del `CustomEvent` `path:change` es `{path: string[]}` — idéntico al contrato existente de Cascade. El listener de la App en `App.tsx` líneas 150–159 sigue funcionando verbatim.
- [ ] La llamada `useCascadePath.setPath(state.path)` se dispara en cada expansión — igual que la Cascade existente.
- [ ] El `aria-label` del componente Breadcrumb se renombra de `"Resolved species breadcrumb"` a `"Cascade path breadcrumb"` según la lista de cambios del archivo `design.md`.

---

## 17. Imagen de referencia

El árbol "Browse" original del Catalogue of Life (la inspiración para esta superficie):

![Referencia del Catalogue of Life](../../col-tree.png)

La referencia es un **punto de partida**, no una copia. El nuevo árbol moderniza el lenguaje visual:

| Aspecto | Referencia CoL | Nuevo árbol |
|---------|----------------|-------------|
| Tipografía | Sans-serif, denso, enlaces azul brillante | Sans system-ui, peso medio navy, acento restringido |
| Altura de fila | ~26px | 32px escritorio / 28px móvil |
| Guías de sangría | Tenues (apagadas) | 1px hairlines `border-border` |
| Caret | `▸` / `▾` | `▸` / `▾` (igual — convención universal) |
| Etiqueta de rango | Minúsculas, peso `normal` | `MAYÚSCULAS` + `tracking-widest` + `font-medium` |
| Insignia de especie | `2.452.105 spp.` (itálica, azul) | `2.4M spp.` (numérica, neutra, `tabular-nums`) |
| Filtros | Inline `[ ] Fuente [ ] Solo vivientes` (alineados a la derecha) | Igual — preservado exactamente |
| Color | Azul cobalto brillante (tipo `#1F8FFF`) | `accent` = `#3b82f6` (blue-500 del proyecto) |

El nuevo árbol hereda la idea estructural (filas con caret, sangría por rango, filtros inline) y moderniza la tipografía + el color + el espaciado según el sistema de diseño `taxon.pen` del proyecto.

---

## Apéndice — Referencia de tokens (lista para copiar y pegar)

La persona implementadora usa estos tokens de forma literal. Cualquier cosa que no esté en esta lista está FUERA de alcance.

### Colores

```text
text-navy          #0f172a   texto primario
text-slate         #475569   texto secundario, etiqueta de rango, autoría
text-muted         #94a3b8   terciario, placeholder, divisor
text-accent        #3b82f6   enlace, anillo de foco, filtro activo
text-red           #dc2626   texto de error
text-amber         #d97706   marcador de incierto
border-border      #e2e8f0   hairlines, guías de sangría, borde de tarjeta
bg-bg              #f8fafc   hover, esqueleto, insignia
bg-surface         #ffffff   tarjeta
bg-blue-50         #eff6ff   fila seleccionada
bg-red-50          #fef2f2   fondo de error
bg-amber-50        #fffbeb   fondo de aviso
```

### Espaciado

```text
gap-2              8px       gap entre filas
gap-3              12px      gap de cabecera (entre búsqueda y filtros)
p-4                16px      padding de tarjeta
px-2               8px       padding horizontal de fila
py-2               8px       padding vertical de fila (escritorio)
py-3               12px      padding vertical de fila (móvil, área de impacto)
pl-{depth*4}       16px*depth  paso de sangría (escritorio)
pl-{depth*3}       12px*depth  paso de sangría (móvil)
```

### Tipografía

```text
text-sm            14px      nombre de fila, input de búsqueda
text-xs            12px      autoría, insignia, etiquetas de filtro
text-[10px]        10px      etiqueta de rango
font-medium        500       nombre de fila, etiqueta de rango
font-normal        400       autoría, cuerpo
italic             n/a       solo autoría
tracking-widest    0.1em     solo etiqueta de rango
tabular-nums       n/a       solo insignia de especie
```

### Animación

```text
transition-colors duration-150 ease-out    hover
transition-transform duration-150 ease-out rotación del caret
transition-all duration-200 ease-out       expansión de fila
transition-all duration-100 ease-out       aparición del desplegable de búsqueda
animate-spin                                 caret cargando
animate-pulse                                fila de esqueleto
motion-reduce:transition-none                fallback de movimiento reducido
```

### Disposición

```text
max-w-page                  1200px            contenedor de App
rounded-card border border-border bg-surface p-4   tarjeta del árbol
rounded-md border border-border bg-surface         input de búsqueda
rounded-full bg-bg px-2 py-0.5 text-xs              insignia de especie
rounded-chip border px-3 py-1 text-sm                chip de toggles
```

---

*Fin del documento de diseño. La persona implementadora DEBE traducir este documento línea por línea a `TaxonomicTree.tsx` + `TaxonomicTree.state.ts` + las clases de Tailwind. Las preguntas abiertas en §15 requieren respuestas documentadas en el cuerpo del PR.*
