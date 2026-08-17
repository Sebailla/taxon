# Especificación: species-folder

## Propósito

La capacidad `species-folder` crea y persiste una carpeta bajo una raíz controlada por el operador (`AQUALIFE_ROOT`) que refleja la ruta de miga de pan resuelta de una especie `(genus, epithet)`. La carpeta se crea bajo demanda, se persiste en `species_folders` y sobrevive a re-importaciones de `taxa` mediante columnas de re-vinculación `(genus, epithet)`. Cierra la subcaracterística B del issue #68.

## Requisitos

### Requisito: Crear Carpeta Resuelve la Miga de Pan y Persiste la Ruta Anidada

El sistema DEBE resolver un par `(genus, epithet)` mediante `taxon.api.hierarchy.resolve_path_by_display_level`, unir los segmentos canónicos `name` con `os.sep`, anexar a la `AQUALIFE_ROOT` resuelta, crear el directorio anidado con `Path.mkdir(parents=True, exist_ok=True)` y hacer upsert de una fila en `species_folders` keyed por el par `(genus, epithet)` (`PRIMARY KEY (genus, epithet)`, SIN foreign key a `taxa.id`). El endpoint DEBE devolver HTTP 201 con `{"path": "<ruta absoluta>"}`.

#### Escenario: La primera creación es exitosa y devuelve la ruta absoluta

- DADO que `Panthera tigris` existe en `taxa` encadenado a `Animalia`
- CUANDO el cliente publica `POST /api/species-folder/Panthera/tigris`
- ENTONCES la respuesta es HTTP 201 con `{"path": "<AQUALIFE_ROOT>/Animalia/Chordata/.../Panthera/Panthera tigris"}`
- Y la carpeta existe en disco después de la respuesta
- Y existe una fila en `species_folders` con `genus="Panthera"`, `epithet="tigris"`, `path` igual a la respuesta

#### Escenario: La creación repetida devuelve 409

- DADO que existe una fila en `species_folders` para `Panthera tigris`
- CUANDO el cliente publica `POST /api/species-folder/Panthera/tigris` de nuevo
- ENTONCES la respuesta es HTTP 409 con `{detail: str}`

### Requisito: `AQUALIFE_ROOT` se Resuelve Contra la Raíz del Proyecto

El sistema DEBE leer `AQUALIFE_ROOT` del entorno con valor por defecto `./Proyecto-Aqualife/` y DEBE resolver las rutas relativas contra la **raíz del proyecto**, no contra el directorio de trabajo actual. Cuando la raíz no está establecida Y la ruta resuelta no es escribible, el endpoint DEBE fallar con HTTP 500 y un cuerpo `ErrorResponse` que nombre la ruta que falla y el cwd.

#### Escenario: La raíz por defecto se resuelve contra la raíz del proyecto, no contra cwd

- DADO que el proceso se inicia desde un subdirectorio de la raíz del proyecto (checkout de worktree)
- Y `AQUALIFE_ROOT` no está establecida
- CUANDO el cliente resuelve la carpeta de una especie
- ENTONCES la carpeta creada vive en `<project_root>/Proyecto-Aqualife/...`, NO en `<cwd>/Proyecto-Aqualife/...`

#### Escenario: La raíz no escribible falla ruidosamente

- DADO que `AQUALIFE_ROOT` está establecida en una ruta de solo lectura
- CUANDO el cliente publica `POST /api/species-folder/{g}/{e}`
- ENTONCES la respuesta es HTTP 500 con `{detail: "...AQUALIFE_ROOT... not writable..."}`

### Requisito: La Verificación de Existencia Devuelve Ruta o 404

El sistema DEBE exponer `GET /api/species-folder/{genus}/{epithet}` que devuelve HTTP 200 con `{"path": str, "exists": true}` cuando existe una fila, y HTTP 404 con `ErrorResponse` cuando no existe. La `path` DEBE ser la ruta absoluta almacenada en la fila.

#### Escenario: Fila existente devuelve 200 con ruta

- DADO que existe una fila en `species_folders` para `Panthera tigris`
- CUANDO el cliente solicita `GET /api/species-folder/Panthera/tigris`
- ENTONCES la respuesta es HTTP 200 con `{"path": "<ruta absoluta>", "exists": true}`

#### Escenario: Fila ausente devuelve 404

- DADO que no existe una fila en `species_folders` para `Panthera tigris`
- CUANDO el cliente solicita `GET /api/species-folder/Panthera/tigris`
- ENTONCES la respuesta es HTTP 404 con `{detail: str}`

### Requisito: El Esquema Caminado por `(genus, epithet)` Sobrevive a Re-Importaciones

El sistema DEBE caminar por `(genus, epithet)` en cada lectura y escritura para que las re-importaciones que incrementan `taxa.id` no dejen huérfana la fila de carpeta. La tabla `species_folders` DEBE tener `PRIMARY KEY (genus, epithet)` SIN foreign key a `taxa.id`; el par `(genus, epithet)` es la identidad durable de la fila de carpeta. El endpoint resuelve el nombre de la especie vía `resolve_path_by_display_level` y matchea la fila directamente por el par `(genus, epithet)`.

#### Escenario: La fila de carpeta sobrevive a incremento manual de `taxa.id`

- DADO que existe una fila en `species_folders` para `(Panthera, tigris)`
- CUANDO el fixture de test muta `taxa.id` para `Panthera tigris` (simulando re-importación)
- Y el cliente solicita `GET /api/species-folder/Panthera/tigris`
- ENTONCES el sistema devuelve la `path` de la fila sin cambios
- Y no se requiere operación de re-vinculación (la fila está keyed en `(genus, epithet)`, no en `taxa.id`)

### Requisito: La Ruta de Carpeta Redonda Limpia para Especies Solo ASCII

El sistema DEBE producir rutas de carpeta cuyos segmentos sean los valores canónicos `name` textualmente para especies ASCII, unidos por `os.sep`. La ruta NO DEBE introducir segmentos URL-codificados ni caracteres de comillas.

#### Escenario: Los segmentos ASCII se unen textualmente

- DADO que `Panthera tigris` se resuelve a `Animalia → Chordata → ... → Panthera tigris`
- CUANDO se crea la carpeta
- ENTONCES la ruta en disco es `<AQUALIFE_ROOT>/Animalia/Chordata/.../Panthera/Panthera tigris`
- Y ningún segmento se minúsculiza, se URL-codifica ni se reemplaza con guiones bajos

### Requisito: El Script de Migración Autocontenido Aplica el Esquema Sin Arrancar la API

El sistema DEBE exponer `python -m taxon.migrate {dry-run|apply}` que invoca `Base.metadata.create_all(engine)` contra `TAXON_DATABASE_URL` para las tres tablas nuevas (`species_explored`, `species_folders`, `link_visited`). El script DEBE imprimir un resumen de una línea; `apply` NO DEBE eliminar ni alterar tablas preexistentes.

#### Escenario: dry-run informa sin mutar

- DADO que la base de datos SQLite carece de las tres tablas nuevas
- CUANDO el operador ejecuta `python -m taxon.migrate dry-run`
- ENTONCES el script imprime un resumen que nombra las tres tablas faltantes
- Y el archivo de base de datos queda sin cambios en disco

#### Escenario: apply crea las tres tablas nuevas

- DADO que la base de datos SQLite carece de las tres tablas nuevas
- CUANDO el operador ejecuta `python -m taxon.migrate apply`
- ENTONCES el script crea `species_explored`, `species_folders`, `link_visited`
- Y las tablas preexistentes `taxa` y `species_paths` quedan intactas

### Requisito: El Lifespan de FastAPI Inicializa el Esquema al Arrancar

El sistema DEBE invocar `Base.metadata.create_all(engine)` para las tres tablas nuevas dentro del contexto `lifespan` de FastAPI para que una base de datos fresca adopte el esquema en el primer arranque. El lifespan NO DEBE intentar crear las tablas preexistentes (`taxa`, `species_paths`).

#### Escenario: Una base de datos fresca sirve los nuevos endpoints tras arrancar

- DADO que una base de datos SQLite no tiene las tablas `species_explored` / `species_folders` / `link_visited`
- CUANDO la aplicación FastAPI arranca
- ENTONCES `Base.metadata.create_all(engine)` crea las tres tablas nuevas
- Y la primera solicitud `POST /api/explored/{g}/{e}` es exitosa

## Fuera de Alcance

- Sincronización en la nube, multidispositivo, autenticación — SQLite local monousuario según el issue #68.
- Anidamiento de carpeta para subespecies — la carpeta se detiene en el bucket de la especie.
- Una columna desnormalizada `taxa.is_explored` — la marca de explorado tiene su propia tabla (ver la especificación `species-explored`).
- Dependencia de Alembic — `create_all` en runtime + script autocontenido es el mecanismo de migración.
- Colisiones de ruta dentro de `AQUALIFE_ROOT` (segmentos con diferente capitalización) — las especies ASCII hacen round-trip textualmente; la normalización no-ASCII es una rebanada separada.
- Limpieza de carpetas cuya fila de especie se elimina — la verificación de existencia es la única sonda "está viva".
