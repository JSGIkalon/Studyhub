-- ---------------------------------------------------------------------------
-- 001 · Esquema inicial de StudyHub
--
-- Convenciones:
--   · Marcas de tiempo: TEXT ISO-8601 con desfase local ('2026-08-16T14:03:22-05:00').
--   · Fechas de agrupacion: TEXT 'YYYY-MM-DD' en hora local, precalculadas.
--   · Booleanos: INTEGER 0 / 1.
--   · Toda clave foranea con ON DELETE CASCADE.
-- ---------------------------------------------------------------------------

CREATE TABLE proyecto (
    id              INTEGER PRIMARY KEY,
    nombre          TEXT    NOT NULL,
    icono           TEXT    NOT NULL DEFAULT 'libro',
    color           TEXT    NOT NULL DEFAULT '#E5484D',
    fecha_objetivo  TEXT,                          -- 'YYYY-MM-DD', opcional
    ruta_biblioteca TEXT,                          -- NULL = Library/<nombre>
    orden           INTEGER NOT NULL DEFAULT 0,
    archivado       INTEGER NOT NULL DEFAULT 0,
    creado_en       TEXT    NOT NULL
);

CREATE TABLE materia (
    id          INTEGER PRIMARY KEY,
    proyecto_id INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    nombre      TEXT    NOT NULL,
    orden       INTEGER NOT NULL DEFAULT 0,
    color       TEXT,
    UNIQUE (proyecto_id, nombre)
);

CREATE TABLE modulo (
    id            INTEGER PRIMARY KEY,
    materia_id    INTEGER NOT NULL REFERENCES materia(id) ON DELETE CASCADE,
    nombre        TEXT    NOT NULL,
    orden         INTEGER NOT NULL DEFAULT 0,
    completado    INTEGER NOT NULL DEFAULT 0,
    completado_en TEXT,
    UNIQUE (materia_id, nombre)
);

CREATE TABLE documento (
    id             INTEGER PRIMARY KEY,
    proyecto_id    INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    ruta_relativa  TEXT    NOT NULL,
    nombre         TEXT    NOT NULL,
    huella         TEXT    NOT NULL,               -- tamano + md5 parcial
    paginas        INTEGER,                        -- NULL hasta la primera apertura
    bytes          INTEGER NOT NULL DEFAULT 0,
    pagina_actual  INTEGER NOT NULL DEFAULT 0,
    zoom           REAL    NOT NULL DEFAULT 1.0,
    scroll_x       REAL    NOT NULL DEFAULT 0.0,
    scroll_y       REAL    NOT NULL DEFAULT 0.0,
    abierto_en     TEXT,
    agregado_en    TEXT    NOT NULL,
    UNIQUE (proyecto_id, ruta_relativa)
);

CREATE TABLE sesion (
    id           INTEGER PRIMARY KEY,
    proyecto_id  INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    tipo         TEXT    NOT NULL CHECK (tipo IN ('trabajo', 'descanso_corto', 'descanso_largo')),
    origen       TEXT    NOT NULL CHECK (origen IN ('pomodoro', 'manual', 'importada')),
    inicio       TEXT    NOT NULL,
    fin          TEXT,
    duracion_seg INTEGER NOT NULL DEFAULT 0,
    fecha_local  TEXT    NOT NULL,                 -- 'YYYY-MM-DD', para agrupar
    completada   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sesion_materia (
    sesion_id  INTEGER NOT NULL REFERENCES sesion(id)  ON DELETE CASCADE,
    materia_id INTEGER NOT NULL REFERENCES materia(id) ON DELETE CASCADE,
    PRIMARY KEY (sesion_id, materia_id)
);

CREATE TABLE anotacion (
    id                 INTEGER PRIMARY KEY,
    documento_id       INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    tipo               TEXT    NOT NULL CHECK (tipo IN ('marcador', 'nota', 'resaltado')),
    pagina             INTEGER NOT NULL,
    rects_json         TEXT    NOT NULL DEFAULT '[]',  -- coordenadas en PUNTOS PDF
    texto_seleccionado TEXT,
    comentario         TEXT,
    color              TEXT    NOT NULL DEFAULT '#F5A524',
    creado_en          TEXT    NOT NULL
);

CREATE TABLE ajuste (
    proyecto_id INTEGER REFERENCES proyecto(id) ON DELETE CASCADE,  -- NULL = global
    clave       TEXT    NOT NULL,
    valor       TEXT    NOT NULL
);

-- SQLite trata cada NULL como distinto en un UNIQUE, asi que los ajustes
-- globales necesitan su propio indice parcial para no duplicarse.
CREATE UNIQUE INDEX idx_ajuste_proyecto ON ajuste (proyecto_id, clave)
    WHERE proyecto_id IS NOT NULL;
CREATE UNIQUE INDEX idx_ajuste_global   ON ajuste (clave)
    WHERE proyecto_id IS NULL;

CREATE INDEX idx_materia_proyecto   ON materia   (proyecto_id, orden);
CREATE INDEX idx_modulo_materia     ON modulo    (materia_id, orden);
CREATE INDEX idx_documento_proyecto ON documento (proyecto_id);
CREATE INDEX idx_documento_huella   ON documento (proyecto_id, huella);
CREATE INDEX idx_sesion_fecha       ON sesion    (proyecto_id, fecha_local);
CREATE INDEX idx_anotacion_doc      ON anotacion (documento_id, pagina);
