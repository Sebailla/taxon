# Default de base de datos a `data/col.db` con fallback a `data/taxon.db`

## What

Se cambia `DEFAULT_DATABASE_URL` para que apunte a `sqlite:///./data/col.db`
(el dataset CoL producido por `python -m taxon.import_data`) y, cuando
ese archivo no exista en disco, se haga fallback automático a
`sqlite:///./data/taxon.db`. Antes había que setear
`TAXON_DATABASE_URL=.../data/col.db` en cada arranque.

## How

- La lógica de resolución de URL vivía duplicada en `taxon/api/__init__.py`
  y `taxon/migrate.py`. Se extrae a un módulo nuevo
  `taxon/api/database_url.py` como única fuente de verdad.
- El helper (`resolve_database_url`) mantiene la cadena de precedencia
  existente (`argument > env > DEFAULT_DATABASE_URL`), añade la
  verificación `_sqlite_file_exists` y solo dispara el fallback cuando
  la resolución llegó al default **y** el archivo primario no existe.
  Argumentos explícitos y `TAXON_DATABASE_URL` con archivo ausente se
  honran tal cual (no hay fallback implícito para overrides del usuario).
- El helper emite un `logging.WARNING` la primera vez que se hace
  fallback, así el operador nota el drift entre el default declarado
  y el dataset que la app realmente abrió.
- Se crea `taxon/tests/test_api_database_url.py` con 12 tests red-first
  que cubren: la cadena de precedencia completa, el camino
  "default presente → no fallback", el camino "default ausente +
  fallback presente → fallback + WARNING", el camino "ambos ausentes
  → se mantiene el primary", pass-through de `:memory:` y de URLs no
  SQLite, y la creación del directorio padre.

## Where

- `taxon/api/database_url.py` — nuevo módulo con `DEFAULT_DATABASE_URL`
  y `resolve_database_url`.
- `taxon/api/__init__.py` — reexporta `DEFAULT_DATABASE_URL` desde el
  helper; `create_app` delega la resolución.
- `taxon/migrate.py` — sustituye su copia local por una delegación
  al helper compartido.
- `taxon/tests/test_api_database_url.py` — contrato red-first del
  resolver (12 tests).

## Why

CoL es el dataset canónico desde que se retiró GBIF. El default apuntaba
todavía al legacy `taxon.db`, así que cualquier operador que arrancaba
la API sin variables de entorno aterrizaba en un dataset vacío o en
el dataset equivocado. La consecuencia práctica era: cada vez que
alguien clonaba el repo tenía que leer el README para descubrir que
necesitaba exportar `TAXON_DATABASE_URL`. El fallback cubre el caso
de checkouts antiguos y caches de CI que todavía traen `taxon.db`
solo.

## How it works en producción

1. `python -m taxon.main` arranca.
2. `create_app(None)` delega en `resolve_database_url(None)`.
3. Si `TAXON_DATABASE_URL` está seteada → esa URL gana.
4. Si no, el default `sqlite:///./data/col.db` se evalúa: ¿el archivo
   existe? Sí → se usa sin warning. No → busca
   `sqlite:///./data/taxon.db`; si existe, emite un WARNING y lo usa;
   si tampoco, se queda con el primary (SQLAlchemy creará uno vacío).
5. El directorio padre del archivo final se crea con `mkdir -p` para
   que el primer arranque en una máquina limpia no falle.

## Workflows

- CI: `pytest taxon/tests/` corre el nuevo archivo de tests con todas
  las variantes de URL y los mocks de filesystem. `ruff`, `ruff
  format --check`, `mypy` verdes.
- Operador: ya no necesita `TAXON_DATABASE_URL` salvo que quiera
  apuntar a una base distinta. Si la app arranca con un dataset
  distinto al del default, ve un WARNING en logs — la primera pista
  de que algo se desincronizó.
- Migraciones: `python -m taxon.migrate apply` honra el mismo default
  y fallback, así que un reset de DB ya no requiere tocar la env.

## Aprendido

- El patrón de fallback "primary ausente → secondary" NO debe disparar
  cuando el caller pasó la URL explícitamente. El test
  `test_explicit_argument_with_missing_file_is_honoured` y el
  `test_env_var_with_missing_file_is_honoured` cubren esa distinción;
  es el error más fácil de cometer cuando se mete el chequeo de
  existencia en el resolver.
- La regla "si el primary y el fallback faltan, quédate con el primary"
  es importante: si swapearas automáticamente, SQLAlchemy crearía un
  SQLite vacío en la ruta del fallback y el operador perdería la
  pista de qué pasó.