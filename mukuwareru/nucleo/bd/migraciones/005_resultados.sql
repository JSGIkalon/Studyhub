-- ---------------------------------------------------------------------------
-- 005 · Resultados de evaluaciones
--
-- Progreso responde a «cuanto temario llevo». Esto responde a «que tal lo hago»,
-- que es un eje distinto y no se mezcla con el anterior: ninguna columna de aqui
-- entra en ServicioProgreso. Se puede llevar el 30 % del temario y sacar un 70 %
-- en un simulacro, y las dos cosas son ciertas a la vez.
--
-- El vocabulario es deliberadamente generico. No hay ninguna tabla `mock`: un
-- simulacro del CFA, un parcial de un master, un quiz de un curso y el examen de
-- una certificacion son todos `evaluacion`. La escala tambien es generica:
-- puntos obtenidos sobre puntos posibles, con decimales. 38/50, 8,5/10, 4,2/5 y
-- 61/100 caben sin convertir nada; el porcentaje se CALCULA, como toda
-- estadistica de la aplicacion, y por eso no se guarda.
-- ---------------------------------------------------------------------------

CREATE TABLE evaluacion (
    id               INTEGER PRIMARY KEY,
    proyecto_id      INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,

    -- Opcional: el resultado de algo que ya estaba en el calendario. SET NULL y
    -- no CASCADE, que es la decision que importa aqui: borrar la fecha prevista
    -- no puede llevarse por delante la nota que sacaste.
    hito_id          INTEGER REFERENCES hito(id) ON DELETE SET NULL,

    titulo           TEXT    NOT NULL,
    fecha            TEXT    NOT NULL,          -- 'YYYY-MM-DD' local
    puntos_obtenidos REAL    NOT NULL CHECK (puntos_obtenidos >= 0),

    -- Estrictamente mayor que cero: un examen sobre cero puntos no es un examen,
    -- y seria una division por cero en cuanto se pintara el porcentaje.
    puntos_posibles  REAL    NOT NULL CHECK (puntos_posibles > 0),

    -- Peso RELATIVO, igual que `materia.peso` (ver 004): la nota de una
    -- asignatura es la media de sus evaluaciones ponderada por este peso,
    -- dividiendo entre la suma. Asi «30 % parcial + 70 % final» se escribe 30 y
    -- 70, o 3 y 7, y anadir un tercer examen no obliga a recalcular los otros.
    --
    -- El valor por defecto es 1 y NO 0, al contrario que en `materia.peso`. Alli
    -- el cero significaba «sin ponderar, vuelve al conteo de modulos», porque
    -- habia un modo anterior al que volver. Aqui no lo hay: la media natural de
    -- tres simulacros es la aritmetica, que es exactamente «todos con peso 1».
    --
    -- El peso vive en la evaluacion y no en cada linea del desglose. Un mismo
    -- examen que pesara distinto en cada asignatura (70 % en una, 40 % en otra)
    -- no cabe hoy; si alguna vez hace falta, la salida es aditiva: anadir
    -- `evaluacion_materia.peso REAL` y leer COALESCE(em.peso, e.peso). Mientras
    -- nadie lo pida, una columna menos y un dialogo que se entiende.
    peso             REAL    NOT NULL DEFAULT 1 CHECK (peso >= 0),

    nota             TEXT,
    creado_en        TEXT    NOT NULL
);

-- Como maximo un resultado por fecha del calendario: «el resultado del Mock 3»
-- es uno solo. El indice es parcial porque `hito_id` nulo es el caso corriente.
CREATE UNIQUE INDEX idx_evaluacion_hito ON evaluacion (hito_id)
    WHERE hito_id IS NOT NULL;
CREATE INDEX idx_evaluacion_fecha ON evaluacion (proyecto_id, fecha);

-- Desglose por asignatura. Es OPCIONAL: una evaluacion puede no tener ninguna
-- linea (el parcial del que solo sabes el total), tener una (el parcial de
-- Econometria) o tenerlas todas (un simulacro que reparte las diez materias).
--
-- Apunta a `materia` y no a `modulo` a proposito: ningun proveedor publica el
-- resultado modulo a modulo, y el grano de la nota es el mismo que el del peso.
--
-- La suma de las lineas NO tiene por que coincidir con la nota global, y no hay
-- ningun CHECK que lo exija: los simulacros redondean por tema, y ademas un
-- desglose parcial («de Ethics saque 14/18, del resto no me lo dieron») es
-- informacion util que un CHECK tiraria a la basura. La interfaz avisa de la
-- discrepancia en lugar de impedirla.
--
-- La clave primaria compuesta calca `bloque_materia` y hace imposible por
-- construccion que una misma materia aparezca dos veces en el mismo examen.
CREATE TABLE evaluacion_materia (
    evaluacion_id    INTEGER NOT NULL REFERENCES evaluacion(id) ON DELETE CASCADE,
    materia_id       INTEGER NOT NULL REFERENCES materia(id)    ON DELETE CASCADE,
    puntos_obtenidos REAL    NOT NULL CHECK (puntos_obtenidos >= 0),
    puntos_posibles  REAL    NOT NULL CHECK (puntos_posibles > 0),
    PRIMARY KEY (evaluacion_id, materia_id)
);

CREATE INDEX idx_evaluacion_materia ON evaluacion_materia (materia_id);
