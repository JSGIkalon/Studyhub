-- 010 · Materia de cada PDF y titulos de nota que no escribio nadie.
--
-- Un PDF pertenece a lo sumo a una materia: `2026-L1-Equity.pdf` es de Equity y
-- de nada mas. Por eso es una columna y no una tabla de vinculos. ON DELETE SET
-- NULL y no CASCADE: borrar la materia no puede llevarse el PDF por delante.
ALTER TABLE documento
    ADD COLUMN materia_id INTEGER REFERENCES materia(id) ON DELETE SET NULL;

CREATE INDEX idx_documento_materia ON documento (materia_id)
    WHERE materia_id IS NOT NULL;

-- Hasta ahora, guardar una nota sin titulo grababa como titulo el principio del
-- cuerpo aplanado en una linea, y desde fuera no se distinguia de uno escrito a
-- mano. Esos titulos son un prefijo exacto de `cuerpo_plano` (quitando el «…»
-- del recorte): se vacian, y el titulo pasa a deducirse al mostrar la nota, de
-- su primera linea real.
UPDATE nota
   SET titulo = ''
 WHERE titulo <> ''
   AND instr(cuerpo_plano, rtrim(titulo, '…')) = 1;
