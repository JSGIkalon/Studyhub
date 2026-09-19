-- ---------------------------------------------------------------------------
-- 002 · Notas sueltas: cuadernos, secciones, etiquetas y vinculos
--
-- Convenciones de 001: marcas ISO-8601 con desfase local, fechas 'YYYY-MM-DD'
-- locales precalculadas, booleanos 0 / 1, toda clave foranea ON DELETE CASCADE.
--
-- `anotacion` NO se toca, y esa es la decision. Una anotacion es un ancla dentro
-- de un PDF: tiene pagina obligatoria y se borra con su documento, porque sin el
-- PDF un resaltado no significa nada. Una nota suelta es lo contrario: no tiene
-- pagina, pertenece a un cuaderno y debe SOBREVIVIR al borrado del PDF que
-- menciona. Son dos ciclos de vida opuestos sobre la misma columna, y ademas
-- quitar un NOT NULL en SQLite obliga a reconstruir la tabla sobre datos reales
-- del usuario. Con tabla nueva la migracion es solo CREATE.
-- ---------------------------------------------------------------------------

CREATE TABLE cuaderno (
    id          INTEGER PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    nombre      TEXT    NOT NULL,
    color       TEXT,
    orden       INTEGER NOT NULL DEFAULT 0,
    creado_en   TEXT    NOT NULL,
    UNIQUE (proyecto_id, nombre)
);

CREATE TABLE seccion (
    id          INTEGER PRIMARY KEY,
    cuaderno_id INTEGER NOT NULL REFERENCES cuaderno(id) ON DELETE CASCADE,
    nombre      TEXT    NOT NULL,
    color       TEXT,
    orden       INTEGER NOT NULL DEFAULT 0,
    creado_en   TEXT    NOT NULL,
    UNIQUE (cuaderno_id, nombre)
);

-- `seccion_id` es NOT NULL y todo cuaderno nace con una seccion «General», de
-- modo que una nota rapida nunca obliga a decidir donde va y el SQL no tiene que
-- recorrer un arbol con padre nullable.
--
-- `cuerpo` es el mismo HTML autocontenido que produce ui/dialogos/nota.py, con
-- las imagenes pegadas como data: URI en base64.
-- `cuerpo_plano` es derivado, no cacheado: se recalcula en el repositorio en cada
-- escritura, en la misma fila, igual que `sesion.fecha_local`. Sin el, un LIKE
-- sobre `cuerpo` encontraria coincidencias dentro del base64 de una imagen.
CREATE TABLE nota (
    id             INTEGER PRIMARY KEY,
    seccion_id     INTEGER NOT NULL REFERENCES seccion(id) ON DELETE CASCADE,
    titulo         TEXT    NOT NULL DEFAULT '',
    cuerpo         TEXT    NOT NULL DEFAULT '',
    cuerpo_plano   TEXT    NOT NULL DEFAULT '',
    orden          INTEGER NOT NULL DEFAULT 0,
    creado_en      TEXT    NOT NULL,
    actualizado_en TEXT    NOT NULL
);

CREATE TABLE etiqueta (
    id          INTEGER PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    nombre      TEXT    NOT NULL,
    color       TEXT,
    UNIQUE (proyecto_id, nombre)
);

CREATE TABLE nota_etiqueta (
    nota_id     INTEGER NOT NULL REFERENCES nota(id)     ON DELETE CASCADE,
    etiqueta_id INTEGER NOT NULL REFERENCES etiqueta(id) ON DELETE CASCADE,
    PRIMARY KEY (nota_id, etiqueta_id)
);

-- Un vinculo apunta a exactamente un objeto. Se usan claves foraneas reales y
-- excluyentes en lugar del par generico (tipo TEXT, objeto_id INTEGER): el par
-- generico tira por la borda la integridad referencial y dejaria vinculos
-- apuntando a PDFs ya borrados. `pagina` solo tiene sentido con `documento_id`;
-- NULL significa «el documento entero».
CREATE TABLE nota_vinculo (
    id           INTEGER PRIMARY KEY,
    nota_id      INTEGER NOT NULL REFERENCES nota(id)      ON DELETE CASCADE,
    materia_id   INTEGER          REFERENCES materia(id)   ON DELETE CASCADE,
    modulo_id    INTEGER          REFERENCES modulo(id)    ON DELETE CASCADE,
    documento_id INTEGER          REFERENCES documento(id) ON DELETE CASCADE,
    anotacion_id INTEGER          REFERENCES anotacion(id) ON DELETE CASCADE,
    pagina       INTEGER,
    creado_en    TEXT    NOT NULL,
    CHECK (
        (materia_id   IS NOT NULL) + (modulo_id    IS NOT NULL)
      + (documento_id IS NOT NULL) + (anotacion_id IS NOT NULL) = 1
    ),
    CHECK (pagina IS NULL OR documento_id IS NOT NULL)
);

-- SQLite trata cada NULL como distinto en un UNIQUE, asi que cada destino
-- necesita su indice parcial para no duplicarse. Es la misma solucion que ya
-- usan idx_ajuste_proyecto e idx_ajuste_global en 001.
CREATE UNIQUE INDEX idx_vinculo_materia   ON nota_vinculo (nota_id, materia_id)
    WHERE materia_id   IS NOT NULL;
CREATE UNIQUE INDEX idx_vinculo_modulo    ON nota_vinculo (nota_id, modulo_id)
    WHERE modulo_id    IS NOT NULL;
CREATE UNIQUE INDEX idx_vinculo_anotacion ON nota_vinculo (nota_id, anotacion_id)
    WHERE anotacion_id IS NOT NULL;
-- COALESCE porque «el documento entero» (pagina NULL) tambien debe ser unico.
CREATE UNIQUE INDEX idx_vinculo_documento
    ON nota_vinculo (nota_id, documento_id, COALESCE(pagina, -1))
    WHERE documento_id IS NOT NULL;

-- Busqueda inversa: «que notas apuntan a este PDF, a esta pagina, a esta materia».
CREATE INDEX idx_vinculo_por_documento ON nota_vinculo (documento_id, pagina)
    WHERE documento_id IS NOT NULL;
CREATE INDEX idx_vinculo_por_materia   ON nota_vinculo (materia_id)
    WHERE materia_id   IS NOT NULL;
CREATE INDEX idx_vinculo_por_modulo    ON nota_vinculo (modulo_id)
    WHERE modulo_id    IS NOT NULL;
CREATE INDEX idx_vinculo_por_anotacion ON nota_vinculo (anotacion_id)
    WHERE anotacion_id IS NOT NULL;

CREATE INDEX idx_cuaderno_proyecto ON cuaderno (proyecto_id, orden);
CREATE INDEX idx_seccion_cuaderno  ON seccion  (cuaderno_id, orden);
CREATE INDEX idx_nota_seccion      ON nota     (seccion_id, orden, id);
CREATE INDEX idx_nota_actualizada  ON nota     (actualizado_en DESC);

-- El cuaderno por defecto NO se siembra aqui a proposito: datetime('now') no
-- lleva desfase local y romperia la convencion de `creado_en`. Lo crea
-- RepositorioCuadernos.asegurar_por_defecto(), un solo camino que sirve igual
-- para los proyectos que ya existen y para los que se creen manana.
