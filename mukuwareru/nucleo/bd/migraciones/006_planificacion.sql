-- ---------------------------------------------------------------------------
-- 006 · Carga de estudio y evaluaciones pendientes
--
-- Dos cosas que el planificador necesitaba y no tenia.
--
-- 1. CARGA. Hasta ahora `ServicioPlan.diagnostico` estimaba el tiempo que queda
--    contando modulos pendientes y multiplicando por la media historica. Eso
--    funciona cuando todos los modulos se parecen, y deja de funcionar en cuanto
--    una asignatura de master pide cuarenta horas y otra doce. Con horas
--    declaradas el calculo deja de ser una extrapolacion.
--
--    Todas las columnas admiten NULL —«no lo he estimado»— salvo la prioridad,
--    que tiene un valor neutro. Un proyecto que no rellene nada se comporta
--    exactamente como antes: mismo criterio que el peso de la migracion 004.
--
-- 2. EVALUACIONES PENDIENTES. `puntos_obtenidos` era NOT NULL, de modo que solo
--    cabia un examen ya corregido. Para responder a «que nota necesito en el
--    final» hace falta poder declarar el final ANTES de hacerlo: su peso y su
--    fecha se conocen, su nota no. Una evaluacion sin nota es una evaluacion
--    pendiente; no entra en la nota acumulada y si en el peso que queda.
-- ---------------------------------------------------------------------------

-- --- 1. Carga por asignatura -----------------------------------------------

-- Horas que se calcula que cuesta la asignatura entera. NULL = sin estimar.
ALTER TABLE materia ADD COLUMN horas_estimadas REAL;

-- Sobrescritura manual de las horas que quedan. Normalmente las restantes son
-- estimadas menos dedicadas, pero esa resta se equivoca a menudo: se estudio
-- sin cronometro, o se entendio el tema en la mitad de tiempo. Esta columna deja
-- corregirlo sin falsear ni la estimacion ni el historial de sesiones, que son
-- dos datos que interesa conservar tal cual. NULL = usa el calculo.
ALTER TABLE materia ADD COLUMN horas_restantes_manual REAL;

-- 0 Baja · 1 Media · 2 Alta · 3 Critica. Entero y no texto porque lo unico que
-- se le pide es ordenar, y 1 es el valor neutro con el que arranca todo lo que
-- ya existe. Cuatro niveles fijos: un scoring configurable seria justo la
-- sobreingenieria que este sistema no necesita.
ALTER TABLE materia ADD COLUMN prioridad INTEGER NOT NULL DEFAULT 1
    CHECK (prioridad BETWEEN 0 AND 3);

-- «Cuando quiero tener esto acabado», en formato 'YYYY-MM-DD'.
--
-- NO sustituye a `hito`, y la diferencia importa: un hito es una fecha del
-- calendario que existe por si misma (el examen es el dia 10 lo mire quien lo
-- mire), mientras que esto es una meta propia de la asignatura. Meterlo como
-- hito llenaria el calendario de fechas inventadas.
ALTER TABLE materia ADD COLUMN fecha_limite TEXT;

-- Estimacion opcional por modulo. Si los modulos de una asignatura la tienen,
-- su suma manda sobre `materia.horas_estimadas`: es un dato mas fino y el
-- usuario que se ha molestado en desglosarlo no espera que se ignore.
--
-- Se admite aqui —y no en el peso, donde 004 lo descarto— porque estimar horas
-- de un modulo concreto es una pregunta que se sabe responder, mientras que
-- repartir el peso del examen modulo a modulo no lo es.
ALTER TABLE modulo ADD COLUMN horas_estimadas REAL;

-- --- 2. Evaluaciones pendientes ---------------------------------------------

-- SQLite no permite quitar un NOT NULL con ALTER TABLE, asi que la tabla se
-- recrea con el procedimiento estandar. Es seguro: el migrador ejecuta este
-- archivo dentro de una transaccion y con PRAGMA foreign_keys = OFF, y ha
-- dejado antes una copia de seguridad del archivo entero.
--
-- La definicion es la de 005 con un unico cambio —`puntos_obtenidos` pierde el
-- NOT NULL— y todos los comentarios de alli siguen vigentes.
CREATE TABLE evaluacion_nueva (
    id               INTEGER PRIMARY KEY,
    proyecto_id      INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
    hito_id          INTEGER REFERENCES hito(id) ON DELETE SET NULL,
    titulo           TEXT    NOT NULL,
    fecha            TEXT    NOT NULL,

    -- NULL = pendiente: declarada, todavia sin corregir.
    puntos_obtenidos REAL    CHECK (puntos_obtenidos IS NULL OR puntos_obtenidos >= 0),

    puntos_posibles  REAL    NOT NULL CHECK (puntos_posibles > 0),
    peso             REAL    NOT NULL DEFAULT 1 CHECK (peso >= 0),
    nota             TEXT,
    creado_en        TEXT    NOT NULL
);

INSERT INTO evaluacion_nueva
    (id, proyecto_id, hito_id, titulo, fecha, puntos_obtenidos,
     puntos_posibles, peso, nota, creado_en)
SELECT id, proyecto_id, hito_id, titulo, fecha, puntos_obtenidos,
       puntos_posibles, peso, nota, creado_en
  FROM evaluacion;

DROP TABLE evaluacion;
ALTER TABLE evaluacion_nueva RENAME TO evaluacion;

-- Los indices se van con la tabla vieja; se rehacen igual que en 005.
CREATE UNIQUE INDEX idx_evaluacion_hito ON evaluacion (hito_id)
    WHERE hito_id IS NOT NULL;
CREATE INDEX idx_evaluacion_fecha ON evaluacion (proyecto_id, fecha);
