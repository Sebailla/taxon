# Setup de Lighthouse CI para a11y (PR #21)

# Qué

Se añadió Lighthouse CI como tercer job de CI para `taxon`. El
job `lighthouse` instala Chrome stable, compila `frontend/dist`
y ejecuta `lhci autorun` con una aserción:
`categories:accessibility >= 0.95`. Combinado con los tests de
regresión de axe-core del PR #20, el proyecto cuenta ahora con
dos redes de seguridad de a11y independientes: axe-core corre
contra el árbol de React renderizado en jsdom, y Lighthouse corre
contra el bundle compilado real servido por Chrome headless.
Verificado en local y en el runner de CI: la puntuación de a11y
es 1.0.

# Cómo

### 1. Dependencia y scripts npm

`frontend/package.json`:

- `@lhci/cli@^0.14.0` añadida a `devDependencies`.
- `npm run lhci` envuelve el binario de `@lhci/cli` para uso
  directo.
- `npm run lhci:autorun` ejecuta `npm run build && lhci autorun`
  para garantizar que el bundle de producción exista antes de
  que LHCI empiece a recolectar.

`CHROME_PATH` se mantiene deliberadamente fuera de los scripts
npm. En CI se define explícitamente en el step del workflow; en
desarrollo local se define en el shell del desarrollador o en
`.env.local`. Hardcodearlo rompería la plataforma cuyo path no
coincida con el que el script espera.

### 2. Configuración de lhci (`frontend/.lighthouserc.json`)

- `staticDistDir: "./dist"` — LHCI arranca su propio servidor
  estático. Más simple que mantener un servidor custom y
  suficiente para la auditoría de a11y.
- `numberOfRuns: 1` — la puntuación de a11y es lo bastante
  determinista con una sola corrida.
- `settings.preset: "desktop"` — coincide con la auditoría de
  a11y que el equipo utiliza en local.
- `skipAudits` — se descartan auditorías SEO, crawlability,
  bf-cache y structured data que no aplican a una SPA sin
  superficie de marketing.
- `chromeFlags` — `--no-sandbox --headless=new --disable-gpu
  --disable-dev-shm-usage` para los runners Ubuntu de GitHub
  Actions.
- `assertions.categories:accessibility` — severidad `error`,
  puntuación mínima 0.95. Una sola aserción basta para este PR.
- `upload.target: temporary-public-storage` — la URL del reporte
  se imprime en el log de GitHub Actions sin necesitar un
  servidor LHCI propio.

### 3. Job de CI (`.github/workflows/ci.yml`)

Nuevo job `lighthouse` que corre en paralelo con backend y
frontend (sin `needs:` porque `lhci:autorun` recompila
internamente). Pasos:

1. Checkout.
2. Setup Node 20 con caché de npm (`frontend/package-lock.json`).
3. `npm ci` en `frontend/`.
4. `browser-actions/setup-chrome@v2` con
   `chrome-version: stable`.
5. `npm run build` en `frontend/`.
6. `npm run lhci:autorun` en `frontend/` con `CHROME_PATH:
   /usr/bin/google-chrome`.

### 4. Higiene de .gitignore

- `.gitignore` (raíz): `.lighthouseci/` — directorio de salida
  de reportes de LHCI.
- `frontend/.gitignore`: `*.tsbuildinfo` — ficheros de caché
  incremental emitidos por `tsc -b` que contaminaban `git
  status` desde que se mergeó el PR #20.

# Dónde

- `.github/workflows/ci.yml` — nuevo job `lighthouse`.
- `frontend/.lighthouserc.json` — configuración de LHCI.
- `frontend/package.json` — dep `@lhci/cli` + scripts `lhci` y
  `lhci:autorun`.
- `frontend/package-lock.json` — actualización del lockfile.
- `frontend/.gitignore` — ignorar `*.tsbuildinfo`.
- `.gitignore` — ignorar `.lighthouseci/`.

# Por qué

La auditoría manual de a11y (`docs/audits/lighthouse-a11y.md`,
puntuación 36/40) y los tests de regresión de axe-core (PR #20)
son contratos sólidos, pero ninguno corre contra el bundle de
producción. Lighthouse CI cierra esa brecha auditando el output
real de `vite build` a través de Chrome headless, lo que detecta
problemas que solo se manifiestan en el artefacto compilado
(atributos SVG eliminados por el bundler, fallos de carga de
fuentes, mismatches de hidratación). La aserción de 0.95 da al
equipo un suelo firme: cualquier PR que baje la puntuación de
a11y del bundle de producción por debajo de 0.95 falla CI.

Combinado con el PR #20, el proyecto tiene cobertura
superpuesta que detecta distintos modos de fallo — axe-core en
jsdom detecta problemas a nivel de contrato a velocidad de test
unitario; LHCI detecta problemas del entorno de build a
velocidad de CI. Se espera que los dos veredictos coincidan
dentro de ±2 puntos en cualquier PR sano, según los criterios
de aceptación del issue #19.

# Cómo funciona

En cada push a un PR contra `develop`, GitHub Actions ejecuta
cuatro jobs en paralelo:

- `backend (python 3.11)` — pytest + ruff + mypy.
- `backend (python 3.12)` — la misma pareja de la matriz.
- `frontend (node 20)` — typecheck + Vitest + ESLint + build
  de Vite + upload del artefacto `frontend/dist/`.
- `lighthouse (a11y)` — instala Chrome stable, recompila el
  bundle (idempotente), ejecuta `lhci autorun`. Si tiene éxito,
  el paso de upload de LHCI imprime una URL de
  `storage.googleapis.com/lighthouse-infrastructure.appspot.com`
  con el reporte completo (las reglas de axe-core integradas en
  Lighthouse, todas las puntuaciones de categoría y los
  resultados de las aserciones).

Si la puntuación de a11y cae por debajo de 0.95, el paso de
`lhci autorun` sale con código no-cero y el job falla,
bloqueando el merge. La URL del reporte queda disponible en los
logs del run fallido para triaje.

# Workflows

- **CI** — tres jobs paralelos (matriz backend 3.11/3.12,
  frontend, lighthouse). El job lighthouse es el único que
  toca Chrome; los jobs existentes mantienen su matriz Node 20
  + Python sin cambios.
- **Revisiones** — PR pequeño (~6 archivos, +3584 / -34 líneas;
  la mayor parte del diff es `package-lock.json`). Cuatro
  rebanadas de `work-unit-commits` (gitignore, dep + scripts,
  config de lhci, job de CI) mantienen la superficie de revisión
  compacta.
- **Flujo de desarrollo local** — `cd frontend && npm ci &&
  CHROME_PATH=/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome
  npm run lhci:autorun` reproduce la auditoría de CI en macOS.
  El HTML del reporte se abre al final del run.

# Aprendizajes

- **`staticDistDir` y `startServerCommand` son mutuamente
  excluyentes en la config de LHCI.** Cuando se define
  `staticDistDir`, LHCI ignora `startServerCommand` y corre su
  propio servidor. El borrador inicial de este PR tenía ambos,
  más un servidor stub y un script de hidratación de Puppeteer.
  Sacarlos recortó ~120 líneas de código sin pérdida de
  cobertura de a11y.
- **`@lhci/cli@0.14` no autodetecta Chrome en macOS.** El
  healthcheck reporta "Chrome installation not found" incluso
  cuando Chrome está en la ruta estándar
  `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
  Definir `CHROME_PATH` explícitamente lo arregla. En el runner
  de CI, `browser-actions/setup-chrome` instala Chrome en
  `/usr/bin/google-chrome`, que es lo que usa el workflow.
- **`numberOfRuns: 1` basta para a11y.** La categoría a11y de
  Lighthouse usa reglas deterministas de axe-core; la
  puntuación no varía entre corridas. Subirlo a 3 corridas
  triplicaría la duración del job (~3 min) sin señal adicional.
- **`errors-in-console` no es una aserción útil de a11y en este
  setup.** El servidor estático devuelve 404 para
  `/api/kingdoms`, lo que registra un error en consola en cada
  corrida. Añadir esa aserción haría fallar el job por motivos
  de entorno. Se reconsidera cuando el stub server esté
  cableado.

# Fuera del alcance (deliberado)

- **Servidor stub / script de hidratación de Puppeteer.**
  Borrados antes del commit. Ver el cuerpo del PR #21 para el
  razonamiento completo. Preservados en el historial de la
  rama por si un PR futuro quiere añadir aserciones de
  `errors-in-console` o `categories:best-practices`.
- **Aserción `categories:best-practices`.** Por el mismo motivo.
- **Aserciones `categories:performance` y `categories:seo`.** El
  equipo todavía no ha auditado el presupuesto de performance ni
  la superficie SEO de la SPA. Fuera del alcance de este PR;
  se reconsideran cuando se vuelvan requisitos de producto.
- **Modo `LHCI server`** (dashboard de reportes por proyecto).
  `temporary-public-storage` basta por ahora.
