# Especificación: workspace-explorer

## Propósito

La capacidad `workspace-explorer` renderiza un iframe embebido para la fuente de búsqueda actualmente activa para que el usuario pueda leer cada resultado sin salir del contexto de la SPA. El iframe se vincula a un registro `activeLink` mantenido por el store Zustand `workspaceStore`; el `activeLink` se establece cuando el usuario hace clic en una celda de `SpeciesLinks` (manteniendo la conducta existente `target="_blank"` de abrir en nueva pestaña). El iframe lleva un conjunto de atributos sandbox deliberado y una tarjeta de degradación elegante para fuentes que rechazan la incrustación (los rechazos de X-Frame-Options / CSP son comunes para Wikipedia, Scholar, BHL). Cierra la subcaracterística D del issue #68.

## Requisitos

### Requisito: Los Atributos Sandbox del Iframe Coinciden con el Conjunto Operativo

El sistema DEBE renderizar un `<iframe>` cuyo atributo `sandbox` sea exactamente `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads`. El atributo NO DEBE incluir `allow-top-navigation` (el iframe no debe poder navegar la SPA) y NO DEBE incluir `allow-modals`. El `src` DEBE ser igual a la URL del enlace activo cuando hay un enlace activo, y DEBE estar vacío (o no renderizarse) cuando no hay enlace activo.

#### Escenario: El sandbox del iframe coincide con el conjunto exacto de atributos

- DADO que el `activeLink` está establecido en `{species: "Panthera tigris", source: "Wikipedia", url: "..."}`
- CUANDO el `<ExplorerPanel>` se monta
- ENTONCES el `<iframe>` renderizado tiene `sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"`
- Y el `src` del iframe es igual a la URL del enlace activo
- Y el iframe no tiene la bandera `allow-top-navigation`

#### Escenario: Sin enlace activo se muestra estado vacío

- DADO que no hay un `activeLink` establecido en el store
- CUANDO el `<ExplorerPanel>` se monta
- ENTONCES el panel renderiza un marcador de posición ("Pick a source to embed")
- Y no se renderiza ningún iframe (o el iframe tiene `src` vacío con una superposición de marcador)

### Requisito: El Estado del Enlace Activo se Resuelve al Hacer Clic en un Enlace de Especie

El sistema DEBE actualizar `workspaceStore.activeLink` cuando el usuario hace clic en una celda de `SpeciesLinks` cuyo enlace pertenece a una especie. El enlace activo DEBE ser `{speciesId, source, url}` donde `url` es la URL sustituida. El manejador de clic DEBE mantener la conducta existente del ancla `target="_blank"` — hacer clic abre una nueva pestaña Y popula el iframe.

#### Escenario: El clic en un enlace de especie popula el enlace activo

- DADO que el panel de enlaces de especie renderiza una celda `Wikipedia` para `Panthera tigris`
- CUANDO el usuario hace clic en la celda
- ENTONCES `useWorkspace.getState().activeLink` es igual a `{speciesId: <id>, source: "Wikipedia", url: "<URL sustituida>"}`
- Y el navegador abre una nueva pestaña mediante `target="_blank"`
- Y el src del iframe se actualiza a la misma URL

### Requisito: El Panel de Enlaces de Migas de Pan por Taxón NO Activa el Iframe

El sistema NO DEBE establecer `activeLink` desde el panel de enlaces de migas de pan por taxón (el endpoint `taxon-links` para segmentos de miga, sin epíteto). El panel de enlaces de migas de pan mantiene su conducta existente `target="_blank"` pero no popula el panel del explorer; el iframe se mantiene en su estado anterior o en el estado vacío.

#### Escenario: El clic en un enlace de miga no popula el enlace activo

- DADO que el panel de enlaces de migas de pan renderiza una celda `Wikipedia` para `Animalia`
- CUANDO el usuario hace clic en la celda
- ENTONCES `useWorkspace.getState().activeLink` no cambia (o permanece null)
- Y el navegador abre una nueva pestaña mediante `target="_blank"`
- Y el estado del iframe no cambia

### Requisito: El Rechazo por X-Frame-Options / CSP Muestra Tarjeta de Respaldo

El sistema DEBE renderizar una tarjeta de respaldo en lugar del iframe cuando la fuente activa rechaza la incrustación. El respaldo DEBE ser disparado por el evento `onError` del iframe y DEBE renderizar: el nombre de la fuente, un mensaje de una línea explicando que la fuente rechaza la incrustación, y un botón obvio `<a href={url} target="_blank" rel="noopener noreferrer">Open in new tab</a>`. El `<a>` de respaldo DEBE ser un ancla regular renderizada fuera del iframe para que el estado del bloqueador de popups no afecte la accesibilidad.

#### Escenario: La fuente que rechaza la incrustación muestra respaldo

- DADO que el `activeLink` es `Wikipedia` para `Panthera tigris`
- CUANDO el iframe dispara `onError` (porque `en.wikipedia.org` envía `X-Frame-Options: SAMEORIGIN`)
- ENTONCES la tarjeta de marcador reemplaza al iframe
- Y la tarjeta muestra "Wikipedia — this source refuses embedding"
- Y la tarjeta contiene un botón `<a target="_blank" rel="noopener noreferrer" href={url}>Open in new tab</a>`
- Y el botón es alcanzable con foco de teclado (axe-core: 0 violaciones)

#### Escenario: El respaldo nunca está oculto

- DADO que la tarjeta de respaldo está renderizada
- CUANDO el usuario inspecciona el panel
- ENTONCES el botón "Open in new tab" es visible (opacity ≥ 1, sin `display: none`, sin `visibility: hidden`)
- Y el botón es el primer foco de tabulación dentro de la tarjeta

### Requisito: Aria Label Nombra la Fuente Emebebida

El sistema DEBE establecer `aria-label="Embedded search result for {genus} {epithet} ({source})"` en el iframe para que los lectores de pantalla anuncien el contexto embebido. La etiqueta DEBE actualizarse cuando cambia el enlace activo.

#### Escenario: El aria label se actualiza al cambiar el enlace activo

- DADO que el `activeLink` es `Wikipedia` para `Panthera tigris`
- CUANDO el `<ExplorerPanel>` se renderiza
- ENTONCES el iframe tiene `aria-label="Embedded search result for Panthera tigris (Wikipedia)"`

#### Escenario: El aria label cambia al cambiar de fuente

- DADO que el `activeLink` es `Wikipedia` para `Panthera tigris`
- CUANDO el usuario hace clic en un enlace `Google` para la misma especie
- ENTONCES el `aria-label` del iframe se actualiza a `"Embedded search result for Panthera tigris (Google)"`
- Y el `src` del iframe se actualiza a la URL de `Google`

### Requisito: Se Monta en la Columna Derecha Debajo de Migas de Pan / Enlaces de Especie

El sistema DEBE montar `<ExplorerPanel>` dentro de la columna derecha de `App.tsx`, debajo de los bloques `<SpeciesLinks>` y `<Breadcrumb>`. El panel DEBE ser `sticky top-0` para que permanezca visible mientras el usuario desplaza la cuadrícula de despacho. El montaje NO DEBE mover la renderización existente de `<Breadcrumb>` / `<SpeciesLinks>`.

#### Escenario: El panel se renderiza debajo de los enlaces de especie

- DADO que el usuario resuelve una especie
- CUANDO la SPA se monta
- ENTONCES la columna derecha muestra `<Breadcrumb>` arriba, `<SpeciesLinks>` debajo y `<ExplorerPanel>` debajo de los enlaces
- Y el panel tiene `class="sticky top-0"`

## Fuera de Alcance

- Estado de iframe persistente entre recargas de la SPA — el enlace activo tiene alcance de sesión; recargar la SPA inicia el estado vacío hasta que el usuario hace clic en un enlace.
- Interceptación de drag-and-drop cross-origin — el flujo de descarga por defecto del navegador del iframe maneja `Content-Disposition: attachment`; la SPA no intercepta descargas.
- Marcar automáticamente una fuente como visitada cuando el usuario hace clic en el enlace dentro del iframe — el manejador de clic hace toggle explícitamente vía `link-visited`; la detección automática es una rebanada separada.
- Preajustes de tamaño de iframe por fuente — el iframe usa una única altura responsiva; los preajustes por fuente se difieren a una iteración posterior.
- Registrar la posición de scroll o el estado del formulario de la página embebida — el iframe es sin estado desde la perspectiva de la SPA.
- UX de iframe específica para móvil (Safari ITP, requestDesktopWebsite) — cae bajo el alcance de escritorio del navegador de la SPA existente.
