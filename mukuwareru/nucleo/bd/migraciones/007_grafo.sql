-- ---------------------------------------------------------------------------
-- 007 · Grafo de dependencias
--
-- Una segunda lectura de lo que ya hay. Un nodo NO es un objeto de estudio: es
-- un puntero a uno que ya existe —una materia, un modulo, un hito, un
-- resultado— mas su posicion en el lienzo. Por eso aqui no hay ni nombre, ni
-- color, ni horas: se leen siempre por la clave foranea, como hace
-- `nota_vinculo`. Una copia local seria una copia que se desincroniza.
--
-- Tampoco hay estado. «Bloqueado / Disponible / En curso / Completado» se
-- CALCULA en ServicioGrafo cruzando las aristas con ServicioProgreso. Guardarlo
-- seria el sistema de progreso paralelo que esta aplicacion no tiene: marcar un
-- modulo en la vista Progreso dejaria el grafo mintiendo hasta que alguien se
-- acordara de sincronizarlo.
--
-- No hay tabla `grafo`. Cada proyecto tiene exactamente uno, asi que una tabla
-- cuya unica columna util seria `proyecto_id` solo anadiria un JOIN a cada
-- consulta. `grafo_nodo.proyecto_id` ES el grafo.
-- ---------------------------------------------------------------------------

CREATE TABLE grafo_nodo (
    id            INTEGER PRIMARY KEY,
    proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,

    -- Exactamente una rellena. Cuatro claves foraneas y no `(tipo, objeto_id)`:
    -- el par generico tira la integridad referencial y deja nodos apuntando a
    -- materias borradas. Es la misma decision que en `nota_vinculo` y por la
    -- misma razon. Con FK reales, borrar una materia se lleva su nodo y —en
    -- cascada— sus aristas, sin una sola linea de codigo de limpieza.
    materia_id    INTEGER REFERENCES materia(id)    ON DELETE CASCADE,
    modulo_id     INTEGER REFERENCES modulo(id)     ON DELETE CASCADE,
    hito_id       INTEGER REFERENCES hito(id)       ON DELETE CASCADE,
    evaluacion_id INTEGER REFERENCES evaluacion(id) ON DELETE CASCADE,

    -- Coordenadas del centro del nodo en el sistema de la ESCENA, no en pixeles
    -- de pantalla. Misma decision que los rectangulos de las anotaciones en
    -- puntos del PDF: un nodo colocado al 150 % de zoom tiene que aparecer en el
    -- mismo sitio al 80 % y en otro monitor.
    x             REAL    NOT NULL DEFAULT 0,
    y             REAL    NOT NULL DEFAULT 0,

    -- Etiqueta propia OPCIONAL. Nula —lo normal— significa «usa el nombre de la
    -- entidad». Existe solo para el caso de una materia que en el grafo conviene
    -- llamar de otra manera; no es una copia del nombre ni se sincroniza con el.
    etiqueta      TEXT,
    nota          TEXT,
    creado_en     TEXT    NOT NULL,

    CHECK ((materia_id    IS NOT NULL)
         + (modulo_id     IS NOT NULL)
         + (hito_id       IS NOT NULL)
         + (evaluacion_id IS NOT NULL) = 1)
);

-- «Arrastrar una entidad al lienzo no la duplica» es un invariante de la base de
-- datos, no una comprobacion de la interfaz. Indices unicos parciales, uno por
-- destino, igual que en `nota_vinculo`.
CREATE UNIQUE INDEX idx_grafo_nodo_materia
    ON grafo_nodo (materia_id)    WHERE materia_id    IS NOT NULL;
CREATE UNIQUE INDEX idx_grafo_nodo_modulo
    ON grafo_nodo (modulo_id)     WHERE modulo_id     IS NOT NULL;
CREATE UNIQUE INDEX idx_grafo_nodo_hito
    ON grafo_nodo (hito_id)       WHERE hito_id       IS NOT NULL;
CREATE UNIQUE INDEX idx_grafo_nodo_evaluacion
    ON grafo_nodo (evaluacion_id) WHERE evaluacion_id IS NOT NULL;
CREATE INDEX idx_grafo_nodo_proyecto ON grafo_nodo (proyecto_id);

-- Un prerrequisito. La conjuncion y la disyuncion caben en una sola columna
-- entera:
--
--     dentro del mismo `grupo` las aristas son O · entre grupos son Y
--
-- «Calculo Y (Probabilidad O Estadistica)» son tres filas hacia el mismo
-- destino: Calculo en el grupo 1, las otras dos en el grupo 2. Es forma normal
-- conjuntiva, y cubre ramificacion y convergencia sin nada mas.
--
-- Lo que se evito con esto: nodos operador —un segundo tipo de nodo sin entidad
-- detras, que habria que dibujar, mover y derivarle un estado, o sea el clon de
-- n8n que este diseno no quiere— y una tabla `grafo_grupo` cuya unica columna
-- util seria su propio id.
--
-- El grupo se numera por destino, empezando en 1. Una arista nueva entra en
-- MAX(grupo) + 1, o sea Y, que es lo que espera quien acaba de dibujar la
-- flecha; pasarla a O es fundir su grupo con el de otra.
CREATE TABLE grafo_arista (
    destino   INTEGER NOT NULL REFERENCES grafo_nodo(id) ON DELETE CASCADE,
    origen    INTEGER NOT NULL REFERENCES grafo_nodo(id) ON DELETE CASCADE,
    grupo     INTEGER NOT NULL DEFAULT 1 CHECK (grupo >= 1),
    creado_en TEXT    NOT NULL,

    -- (destino, origen) y no al reves: la consulta caliente es «prerrequisitos
    -- de este nodo», que es la que decide su estado.
    PRIMARY KEY (destino, origen),

    -- El ciclo de longitud uno. Los demas los impide ServicioGrafo.conectar,
    -- que comprueba alcanzabilidad sobre el grafo ya cargado: un CHECK no puede
    -- recorrer una tabla, y un trigger con CTE recursiva meteria reglas de
    -- negocio dentro del esquema, que es peor que SQL fuera de un repositorio.
    CHECK (origen <> destino)
);

CREATE INDEX idx_grafo_arista_origen ON grafo_arista (origen);
