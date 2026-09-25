-- 009 · Retira las tablas del grafo de dependencias.
--
-- La seccion Grafo se quito y ningun codigo lee ya `grafo_nodo` ni
-- `grafo_arista`. Solo guardaban posiciones en el lienzo y aristas entre
-- objetos que siguen existiendo en sus propias tablas: no se pierde temario,
-- progreso ni resultados. El migrador deja una copia de la base antes de
-- aplicar esto, por si acaso.

DROP TABLE IF EXISTS grafo_arista;
DROP TABLE IF EXISTS grafo_nodo;
