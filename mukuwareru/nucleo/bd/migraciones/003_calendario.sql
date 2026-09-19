-- ---------------------------------------------------------------------------
-- 003 · Calendario y planificacion
--
-- Abre la valvula de escape que §12 dejaba prevista: varias fechas por proyecto
-- sin bifurcar el tipo de proyecto (examen frente a carrera).
--
-- `proyecto.fecha_objetivo` NO desaparece: la leen la barra lateral,
-- `Proyecto.dias_restantes` y el dialogo de proyecto. Se espeja en el unico hito
-- con `principal = 1`, en una sola direccion, desde `ServicioProyectos`.
--
-- Dos tablas y no un `evento` generico: un hito es un instante sin duracion que
-- se cumple o no; un bloque tiene hora, duracion, materias previstas y se
-- compara contra el tiempo realmente estudiado. Unificarlos daria una tabla con
-- la mitad de las columnas siempre en NULL y dos CHECK divergentes.
-- ---------------------------------------------------------------------------

CREATE TABLE hito (
    id            INTEGER PRIMARY KEY,
    proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    titulo        TEXT    NOT NULL,
    tipo          TEXT    NOT NULL DEFAULT 'hito'
                          CHECK (tipo IN ('examen', 'entrega', 'hito')),
    fecha         TEXT    NOT NULL,          -- 'YYYY-MM-DD' local
    hora          TEXT,                      -- 'HH:MM' local, opcional
    nota          TEXT,
    color         TEXT,
    principal     INTEGER NOT NULL DEFAULT 0,
    completado    INTEGER NOT NULL DEFAULT 0,
    completado_en TEXT,
    creado_en     TEXT    NOT NULL
);

-- Como maximo un hito principal por proyecto: es el que espeja fecha_objetivo.
CREATE UNIQUE INDEX idx_hito_principal ON hito (proyecto_id) WHERE principal = 1;
CREATE INDEX idx_hito_fecha ON hito (proyecto_id, fecha);

-- La fecha objetivo que ya tuviera cada proyecto pasa a ser su hito principal.
-- Se reutiliza `proyecto.creado_en` como marca en lugar de generarla con
-- datetime('now'), que saldria sin desfase local y romperia la convencion.
INSERT INTO hito (proyecto_id, titulo, tipo, fecha, principal, creado_en)
    SELECT id, 'Fecha objetivo', 'examen', fecha_objetivo, 1, creado_en
      FROM proyecto
     WHERE fecha_objetivo IS NOT NULL;

CREATE TABLE bloque_plan (
    id           INTEGER PRIMARY KEY,
    proyecto_id  INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    fecha        TEXT    NOT NULL,           -- 'YYYY-MM-DD' local
    hora_inicio  TEXT,                       -- 'HH:MM' local; NULL = sin hora
    duracion_min INTEGER NOT NULL DEFAULT 25 CHECK (duracion_min > 0),
    titulo       TEXT    NOT NULL DEFAULT '',
    nota         TEXT,
    creado_en    TEXT    NOT NULL
);

-- Calca `sesion_materia`: un bloque puede prever varias materias.
CREATE TABLE bloque_materia (
    bloque_id  INTEGER NOT NULL REFERENCES bloque_plan(id) ON DELETE CASCADE,
    materia_id INTEGER NOT NULL REFERENCES materia(id)     ON DELETE CASCADE,
    PRIMARY KEY (bloque_id, materia_id)
);

CREATE INDEX idx_bloque_fecha ON bloque_plan (proyecto_id, fecha, hora_inicio);

-- Lo planeado frente a lo real NO se guarda: no hay `bloque_plan.sesion_id`.
-- Obligaria a reclamar la sesion a mano, y una CASCADE desde `sesion` borraria
-- el bloque al borrar la sesion, que es lo contrario de lo que se quiere. El
-- cumplimiento se CALCULA, como toda estadistica de la aplicacion.
