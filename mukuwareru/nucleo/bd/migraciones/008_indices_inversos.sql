-- 008 · Indices inversos de las tablas puente.
--
-- La clave primaria de una tabla puente (a_id, b_id) solo sirve para buscar
-- por la primera columna. Buscar por la segunda —agrupar el tiempo por materia,
-- filtrar notas por etiqueta, o el borrado en cascada al eliminar una materia o
-- una etiqueta— recorria la tabla entera.

CREATE INDEX IF NOT EXISTS idx_sesion_materia_materia ON sesion_materia (materia_id);
CREATE INDEX IF NOT EXISTS idx_bloque_materia_materia ON bloque_materia (materia_id);
CREATE INDEX IF NOT EXISTS idx_nota_etiqueta_etiqueta ON nota_etiqueta (etiqueta_id);
