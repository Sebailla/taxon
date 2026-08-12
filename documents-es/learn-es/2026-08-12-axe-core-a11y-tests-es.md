# Qué

Cobertura automatizada con axe-core sobre la UI de React. Cuatro
tests RED-first fijan el contrato de accesibilidad para App,
Toggles (estado por defecto + activo) y AmbiguityPicker (abierto),
de modo que las más de 70 reglas WCAG 2.1 A/AA + best-practice se
ejecutan en cada PR. Embarcado como PR #20, que cerró
parcialmente el issue #19 (la mitad de axe-core — la mitad de
Lighthouse CI queda diferida para un PR posterior).

Además se corrigió una flake de CI en `tests/Cascade.test.tsx`
donde `user.selectOptions` se disparaba antes de que el fetch de
kingdoms hubiera poblado la lista de `<option>`.

# Cómo

### 1. Tests de axe-core

Archivo nuevo `frontend/tests/a11y.test.tsx` con 4 tests RED-first:

- App no presenta violaciones de axe en el render vacío.
- Toggles no presenta violaciones de axe en el estado por defecto.
- Toggles no presenta violaciones de axe con los toggles activos.
- AmbiguityPicker no presenta violaciones de axe cuando está abierto.

Se usa el valor crudo devuelto por `axe()` en lugar de
`toHaveNoViolations` porque la ampliación `vitest-axe/extend-expect`
de la aserción de Vitest solo toma efecto en algunos contextos. La
comprobación cruda produce un mensaje de fallo claro con id de la
violación, impacto y URL de ayuda cuando una aserción se dispara.

Conjunto de reglas: `wcag2a, wcag2aa, wcag21a, wcag21aa,
best-practice` — coincide con lo que audita Lighthouse en CI, de
modo que el veredicto se mantiene consistente entre ambas
comprobaciones cuando llegue LHCI.

`tests/setup.ts` stubbea `HTMLCanvasElement.prototype.getContext`
para que jsdom no imprima un warning cada vez que axe-core evalúa
el contraste de color.

### 2. Corrección de flake de CI en el test de Cascade

El `<select>` de kingdom se renderiza con solo "Loading children…"
mientras el fetch inicial de kingdoms está en curso.
`findByRole("combobox", { name: /kingdom/i })` retorna tan pronto
como existe el `<select>`, pero `user.selectOptions` requiere que
el `<option>` objetivo esté presente. En el runner de CI el fetch
de kingdoms resolvió microsegundos después de `findByRole`, por lo
que `selectOptions` se disparó contra un select cuya lista de
opciones aún no contenía "Animalia" y falló con "Value 'Animalia'
not found in options". Las ejecuciones locales enmascararon la
flake porque el fetch resolvió microsegundos antes que
`findByRole`.

Corrección: `await screen.findByRole("option", { name: "Animalia" })`
antes de `selectOptions`. Mismo patrón que el resto del archivo ya
usa para los cambios de phylum.

# Dónde

- `frontend/tests/a11y.test.tsx` — nuevo, 4 tests de axe-core.
- `frontend/tests/setup.ts` — stub de `getContext` del canvas.
- `frontend/package.json` — dependencias `axe-core` + `vitest-axe`.
- `frontend/package-lock.json` — actualización del lockfile.
- `frontend/tests/Cascade.test.tsx` — espera de la opción Animalia
  antes de `selectOptions`.

# Por qué

La auditoría manual (`docs/audits/lighthouse-a11y.md`) recorre las
10 dimensiones de la skill impeccable y produjo las correcciones
P2/P3 de #18, pero solo se ejecuta de forma manual. axe-core añade
cobertura automatizada para un conjunto de reglas más amplio
(etiquetas de formularios, contraste de color, texto alternativo,
jerarquía de encabezados, nombres accesibles de botones y más de
70 adicionales) en cada PR. Detectar regresiones automáticamente
es más barato que descubrirlas en el siguiente ciclo de auditoría
manual.

El issue #19 agrupaba este trabajo con Lighthouse CI como un único
seguimiento. Partirlos fue una decisión de juicio:

- axe-core es autocontenido (una dependencia de Vitest + 4 tests,
  cero cambios de infraestructura de CI).
- Lighthouse CI necesita cuatro piezas de pegamento (scripts npm,
  configuración de lhci, script de Puppeteer + servidor stub, job
  nuevo en `.github/workflows/ci.yml`).
- Meterlos en un único PR habría inflado el diff a ~300 líneas y
  mezclado solo-tests con infra.

La rebanada más pequeña embarca primero la cobertura de mayor
valor; LHCI viene en un PR aparte con su propia revisión focalizada.

# Cómo funciona

`npm test` en `frontend/` ejecuta 51 tests en 7 archivos. En el
runner de CI (Ubuntu + Node 20), Vitest arranca jsdom y ejecuta
los 4 tests de axe-core en serie. Cada test renderiza el componente
bajo prueba, ejecuta `axe()` con el conjunto estándar de reglas y
verifica `violations.length === 0`. Cualquier violación falla el
test con el id de la regla, el nivel de impacto, los nodos
afectados y una URL de ayuda apuntando a la documentación de la
regla de axe-core.

La corrección en el test de Cascade vuelve el timing explícito: el
test ahora espera a que el `<option>` de kingdoms exista antes de
emitir el evento de usuario `selectOptions`, que es el patrón
correcto de RTL cuando un fetch asíncrono puebla un `<select>`.

# Workflows

- **CI** — el job de frontend ejecuta `vitest run` tras
  `tsc --noEmit` + `eslint`. Los fallos de axe-core aparecen como
  errores de aserción de Vitest con el contexto de la regla en
  línea.
- **Revisiones** — PR pequeño (4 archivos, +246 / -163 líneas).
  Cabe en el presupuesto de revisión. Foco del revisor: la lista
  de tests (4 de axe-core + la corrección de timing) y la subida
  de deps (`axe-core`, `vitest-axe`).
- **PR futuro (LHCI)** — necesita scripts npm, la referencia
  `puppeteerScript` en `.lighthouserc.json`, añadir
  `*.tsbuildinfo` a `frontend/.gitignore` y un job nuevo
  `lighthouse` en `.github/workflows/ci.yml` que descargue el
  artefacto `frontend-dist` y ejecute `npx lhci autorun`. La
  configuración y los scripts están en stash en
  `feat/a11y-ci-axe` como `stash@{0}` para ese PR.
