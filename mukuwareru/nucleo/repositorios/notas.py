"""Acceso a las tablas ``nota``, ``nota_etiqueta`` y ``nota_vinculo``.

Este repositorio es el unico sitio que escribe ``nota.cuerpo``, y por eso puede
mantener ``cuerpo_plano`` al dia en cada escritura sin riesgo de que se
desincronice: es el mismo patron que ``sesion.fecha_local``, no una tabla de
cache.

La mitad interesante son los metodos de **busqueda inversa** (``por_documento``,
``por_materia``, ``por_modulo``, ``por_anotacion``): son el interlinkado leido en
la otra direccion, que es lo que permite abrir un PDF y ver que notas hablan de
esa pagina.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from mukuwareru.nucleo.modelos.entidades import Nota, Vinculo
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha_hora, ahora_iso
from mukuwareru.utilidades.texto import a_texto_plano

_CAMPOS = """
    id, seccion_id, titulo, cuerpo, cuerpo_plano, orden, creado_en, actualizado_en
"""

_CAMPOS_N = """
    n.id, n.seccion_id, n.titulo, n.cuerpo, n.cuerpo_plano, n.orden,
    n.creado_en, n.actualizado_en
"""

_CAMPOS_VINCULO = """
    id, nota_id, materia_id, modulo_id, documento_id, anotacion_id, pagina, creado_en
"""


# Nombre presentable de cada destino de un vinculo, resuelto en una sola
# consulta con UNION. El orden del CASE fija en que orden salen en la ruta:
# primero la materia, luego el modulo, luego el PDF.
_DESTINOS = """
    SELECT v.nota_id AS nota_id, 1 AS orden, m.nombre AS nombre
      FROM nota_vinculo v JOIN materia m ON m.id = v.materia_id
     WHERE v.nota_id IN ({marcadores})
    UNION ALL
    SELECT v.nota_id, 2, mo.nombre
      FROM nota_vinculo v JOIN modulo mo ON mo.id = v.modulo_id
     WHERE v.nota_id IN ({marcadores})
    UNION ALL
    SELECT v.nota_id, 3,
           d.nombre || CASE WHEN v.pagina IS NULL THEN ''
                            ELSE ' p. ' || (v.pagina + 1) END
      FROM nota_vinculo v JOIN documento d ON d.id = v.documento_id
     WHERE v.nota_id IN ({marcadores})
    UNION ALL
    SELECT v.nota_id, 4, d.nombre || ' p. ' || (a.pagina + 1)
      FROM nota_vinculo v
      JOIN anotacion a ON a.id = v.anotacion_id
      JOIN documento d ON d.id = a.documento_id
     WHERE v.nota_id IN ({marcadores})
     ORDER BY nota_id, orden, nombre
"""


@dataclass(frozen=True, slots=True)
class NotaListada:
    """Una nota con su ubicacion y sus destinos ya resueltos a nombres.

    Toda lista de notas tiene que decir de donde sale cada una y con que esta
    relacionada; hacerlo con una consulta por nota seria absurdo, y obligar al
    usuario a abrirla para saberlo es justo lo que se quiere evitar.
    """

    nota: Nota
    cuaderno: str
    seccion: str
    destinos: tuple[str, ...] = ()

    def ruta(self, titulo: str) -> str:
        """``Cuaderno -> Seccion -> Nota -> destinos``, en una linea.

        Es la firma de la nota: dice donde vive y con que esta ligada sin tener
        que abrirla ni cambiar de pestana.
        """
        partes = [self.cuaderno, self.seccion, titulo]
        if self.destinos:
            partes.append(" · ".join(self.destinos))
        return "  ->  ".join(partes)


class RepositorioNotas(Repositorio):
    """Notas sueltas, sus etiquetas y sus vinculos."""

    # -- Lectura ------------------------------------------------------------

    def obtener(self, nota_id: int) -> Nota | None:
        """La nota con sus etiquetas y vinculos ya resueltos."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM nota WHERE id = ?", (nota_id,)
        ).fetchone()
        if fila is None:
            return None
        nota = _a_nota(fila)
        nota.etiquetas = self.etiquetas_de(nota_id)
        nota.vinculos = self.vinculos_de(nota_id)
        return nota

    def listar(self, seccion_id: int) -> list[Nota]:
        """Notas de una seccion, sin etiquetas ni vinculos (lista ligera)."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM nota WHERE seccion_id = ? ORDER BY orden, id",
            (seccion_id,),
        ).fetchall()
        return [_a_nota(f) for f in filas]

    def listar_del_proyecto(
        self,
        proyecto_id: int,
        *,
        texto: str | None = None,
        cuaderno_id: int | None = None,
        seccion_id: int | None = None,
        etiqueta_id: int | None = None,
        limite: int | None = None,
    ) -> list[NotaListada]:
        """Notas del proyecto, filtrables por texto, ubicacion y etiqueta.

        El filtro de texto va contra ``titulo`` y ``cuerpo_plano``: sobre
        ``cuerpo`` encontraria coincidencias dentro del base64 de las imagenes.
        """
        condiciones = ["c.proyecto_id = ?"]
        parametros: list[object] = [proyecto_id]

        if texto:
            condiciones.append("(n.titulo LIKE ? OR n.cuerpo_plano LIKE ?)")
            patron = f"%{texto}%"
            parametros.extend((patron, patron))
        if cuaderno_id is not None:
            condiciones.append("c.id = ?")
            parametros.append(cuaderno_id)
        if seccion_id is not None:
            condiciones.append("s.id = ?")
            parametros.append(seccion_id)
        if etiqueta_id is not None:
            condiciones.append(
                "EXISTS (SELECT 1 FROM nota_etiqueta ne"
                "         WHERE ne.nota_id = n.id AND ne.etiqueta_id = ?)"
            )
            parametros.append(etiqueta_id)

        limitacion = ""
        if limite is not None:
            limitacion = "LIMIT ?"
            parametros.append(limite)

        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS_N}, c.nombre AS cuaderno, s.nombre AS seccion
              FROM nota n
              JOIN seccion s  ON s.id = n.seccion_id
              JOIN cuaderno c ON c.id = s.cuaderno_id
             WHERE {' AND '.join(condiciones)}
             ORDER BY n.actualizado_en DESC, n.id DESC
             {limitacion}
            """,
            parametros,
        ).fetchall()
        return self._con_destinos([_a_listada(f) for f in filas])

    def _con_destinos(self, listadas: list[NotaListada]) -> list[NotaListada]:
        """Rellena ``destinos`` de todas las notas con una sola consulta."""
        if not listadas:
            return []
        ids = [listada.nota.id for listada in listadas]
        marcadores = ",".join("?" * len(ids))
        filas = self._cx.execute(
            _DESTINOS.format(marcadores=marcadores), ids * 4
        ).fetchall()

        por_nota: dict[int, list[str]] = {}
        for fila in filas:
            por_nota.setdefault(int(fila["nota_id"]), []).append(str(fila["nombre"]))
        return [
            NotaListada(
                nota=listada.nota,
                cuaderno=listada.cuaderno,
                seccion=listada.seccion,
                destinos=tuple(por_nota.get(listada.nota.id, ())),
            )
            for listada in listadas
        ]

    def recientes(self, proyecto_id: int, limite: int = 5) -> list[NotaListada]:
        """Ultimas notas modificadas, para el Panel."""
        return self.listar_del_proyecto(proyecto_id, limite=limite)

    def contar(self, proyecto_id: int) -> int:
        """Numero de notas sueltas del proyecto."""
        fila = self._cx.execute(
            """
            SELECT COUNT(*) FROM nota n
              JOIN seccion s  ON s.id = n.seccion_id
              JOIN cuaderno c ON c.id = s.cuaderno_id
             WHERE c.proyecto_id = ?
            """,
            (proyecto_id,),
        ).fetchone()
        return int(fila[0])

    # -- Escritura ----------------------------------------------------------

    def crear(
        self, seccion_id: int, *, titulo: str = "", cuerpo: str = ""
    ) -> Nota:
        """Inserta una nota al final de su seccion."""
        siguiente = self._cx.execute(
            "SELECT COALESCE(MAX(orden), -1) + 1 FROM nota WHERE seccion_id = ?",
            (seccion_id,),
        ).fetchone()[0]
        marca = ahora_iso()
        cursor = self._cx.execute(
            """
            INSERT INTO nota
                (seccion_id, titulo, cuerpo, cuerpo_plano, orden, creado_en, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (seccion_id, titulo, cuerpo, a_texto_plano(cuerpo), siguiente, marca, marca),
        )
        creada = self.obtener(int(cursor.lastrowid or 0))
        assert creada is not None
        return creada

    def actualizar(self, nota_id: int, *, titulo: str, cuerpo: str) -> None:
        """Guarda titulo y cuerpo, y recalcula lo derivado."""
        self._cx.execute(
            """
            UPDATE nota
               SET titulo = ?, cuerpo = ?, cuerpo_plano = ?, actualizado_en = ?
             WHERE id = ?
            """,
            (titulo, cuerpo, a_texto_plano(cuerpo), ahora_iso(), nota_id),
        )

    def mover(self, nota_id: int, seccion_id: int) -> None:
        """Lleva la nota a otra seccion, al final."""
        siguiente = self._cx.execute(
            "SELECT COALESCE(MAX(orden), -1) + 1 FROM nota WHERE seccion_id = ?",
            (seccion_id,),
        ).fetchone()[0]
        self._cx.execute(
            "UPDATE nota SET seccion_id = ?, orden = ? WHERE id = ?",
            (seccion_id, siguiente, nota_id),
        )

    def reordenar(self, ids: Sequence[int]) -> None:
        """Fija ``orden`` = 0..n-1 segun la secuencia recibida."""
        with self._cx:
            self._cx.executemany(
                "UPDATE nota SET orden = ? WHERE id = ?",
                [(posicion, id_) for posicion, id_ in enumerate(ids)],
            )

    def eliminar(self, nota_id: int) -> None:
        """Borra la nota y, en cascada, sus etiquetas y vinculos."""
        self._cx.execute("DELETE FROM nota WHERE id = ?", (nota_id,))

    # -- Etiquetas ----------------------------------------------------------

    def etiquetas_de(self, nota_id: int) -> list[int]:
        """Identificadores de las etiquetas de la nota."""
        filas = self._cx.execute(
            """
            SELECT ne.etiqueta_id FROM nota_etiqueta ne
              JOIN etiqueta e ON e.id = ne.etiqueta_id
             WHERE ne.nota_id = ? ORDER BY e.nombre
            """,
            (nota_id,),
        ).fetchall()
        return [int(f[0]) for f in filas]

    def etiquetar(self, nota_id: int, etiquetas: Sequence[int]) -> None:
        """Reemplaza las etiquetas de la nota. Calca ``sesiones.etiquetar``."""
        with self._cx:
            self._cx.execute("DELETE FROM nota_etiqueta WHERE nota_id = ?", (nota_id,))
            self._cx.executemany(
                "INSERT INTO nota_etiqueta (nota_id, etiqueta_id) VALUES (?, ?)",
                [(nota_id, etiqueta_id) for etiqueta_id in etiquetas],
            )

    # -- Vinculos -----------------------------------------------------------

    def vinculos_de(self, nota_id: int) -> list[Vinculo]:
        """Vinculos de la nota, en el orden en que se crearon."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS_VINCULO} FROM nota_vinculo WHERE nota_id = ? ORDER BY id",
            (nota_id,),
        ).fetchall()
        return [_a_vinculo(f) for f in filas]

    def vincular_materia(self, nota_id: int, materia_id: int) -> None:
        """Liga la nota a una materia. Repetirlo es inocuo."""
        self._vincular(nota_id, materia_id=materia_id)

    def vincular_modulo(self, nota_id: int, modulo_id: int) -> None:
        """Liga la nota a un modulo. Repetirlo es inocuo."""
        self._vincular(nota_id, modulo_id=modulo_id)

    def vincular_documento(
        self, nota_id: int, documento_id: int, *, pagina: int | None = None
    ) -> None:
        """Liga la nota a un PDF, opcionalmente a una pagina concreta."""
        self._vincular(nota_id, documento_id=documento_id, pagina=pagina)

    def vincular_anotacion(self, nota_id: int, anotacion_id: int) -> None:
        """Liga la nota a un resaltado o marcador del PDF."""
        self._vincular(nota_id, anotacion_id=anotacion_id)

    def _vincular(
        self,
        nota_id: int,
        *,
        materia_id: int | None = None,
        modulo_id: int | None = None,
        documento_id: int | None = None,
        anotacion_id: int | None = None,
        pagina: int | None = None,
    ) -> None:
        """Inserta un vinculo, apoyandose en los indices unicos parciales.

        ``ON CONFLICT DO NOTHING`` hace que vincular dos veces lo mismo no falle
        ni duplique, que es lo que se espera de arrastrar un PDF sobre una nota
        que ya lo tenia.
        """
        self._cx.execute(
            """
            INSERT INTO nota_vinculo
                (nota_id, materia_id, modulo_id, documento_id, anotacion_id,
                 pagina, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                nota_id, materia_id, modulo_id, documento_id, anotacion_id,
                pagina, ahora_iso(),
            ),
        )

    def desvincular(self, vinculo_id: int) -> None:
        """Quita un vinculo. La nota y el objeto siguen intactos."""
        self._cx.execute("DELETE FROM nota_vinculo WHERE id = ?", (vinculo_id,))

    # -- Busqueda inversa ---------------------------------------------------

    def por_documento(
        self, documento_id: int, pagina: int | None = None
    ) -> list[NotaListada]:
        """Notas vinculadas a un PDF.

        Con ``pagina``, las de esa pagina **mas** las del documento entero: una
        nota sobre todo el libro es relevante en cualquiera de sus paginas.
        """
        condicion = "v.documento_id = ?"
        parametros: list[object] = [documento_id]
        if pagina is not None:
            condicion += " AND (v.pagina IS NULL OR v.pagina = ?)"
            parametros.append(pagina)
        return self._por_vinculo(condicion, parametros)

    def por_materia(self, materia_id: int) -> list[NotaListada]:
        """Notas vinculadas a una materia."""
        return self._por_vinculo("v.materia_id = ?", [materia_id])

    def por_modulo(self, modulo_id: int) -> list[NotaListada]:
        """Notas vinculadas a un modulo."""
        return self._por_vinculo("v.modulo_id = ?", [modulo_id])

    def por_anotacion(self, anotacion_id: int) -> list[NotaListada]:
        """Notas vinculadas a una anotacion concreta."""
        return self._por_vinculo("v.anotacion_id = ?", [anotacion_id])

    def _por_vinculo(self, condicion: str, parametros: list[object]) -> list[NotaListada]:
        """Notas que tienen algun vinculo que cumpla la condicion.

        ``DISTINCT`` porque una nota puede tener varios vinculos al mismo
        documento (el entero y una pagina) y no debe salir dos veces.
        """
        filas = self._cx.execute(
            f"""
            SELECT DISTINCT {_CAMPOS_N}, c.nombre AS cuaderno, s.nombre AS seccion
              FROM nota_vinculo v
              JOIN nota n     ON n.id = v.nota_id
              JOIN seccion s  ON s.id = n.seccion_id
              JOIN cuaderno c ON c.id = s.cuaderno_id
             WHERE {condicion}
             ORDER BY n.actualizado_en DESC, n.id DESC
            """,
            parametros,
        ).fetchall()
        return self._con_destinos([_a_listada(f) for f in filas])

    def conteo_por_documento(self, proyecto_id: int) -> dict[int, int]:
        """Notas vinculadas a cada PDF del proyecto, para la insignia de la Biblioteca."""
        filas = self._cx.execute(
            """
            SELECT v.documento_id AS documento_id, COUNT(DISTINCT v.nota_id) AS total
              FROM nota_vinculo v
              JOIN documento d ON d.id = v.documento_id
             WHERE d.proyecto_id = ?
             GROUP BY v.documento_id
            """,
            (proyecto_id,),
        ).fetchall()
        return {int(f["documento_id"]): int(f["total"]) for f in filas}

    def conteo_por_materia(self, proyecto_id: int) -> dict[int, int]:
        """Notas vinculadas a cada materia, para los contadores de Progreso."""
        filas = self._cx.execute(
            """
            SELECT v.materia_id AS materia_id, COUNT(DISTINCT v.nota_id) AS total
              FROM nota_vinculo v
              JOIN materia m ON m.id = v.materia_id
             WHERE m.proyecto_id = ?
             GROUP BY v.materia_id
            """,
            (proyecto_id,),
        ).fetchall()
        return {int(f["materia_id"]): int(f["total"]) for f in filas}


def _a_nota(fila: sqlite3.Row) -> Nota:
    return Nota(
        id=fila["id"],
        seccion_id=fila["seccion_id"],
        titulo=fila["titulo"],
        cuerpo=fila["cuerpo"],
        cuerpo_plano=fila["cuerpo_plano"],
        orden=fila["orden"],
        creado_en=a_fecha_hora(fila["creado_en"]),
        actualizado_en=a_fecha_hora(fila["actualizado_en"]),
    )


def _a_listada(fila: sqlite3.Row) -> NotaListada:
    return NotaListada(
        nota=_a_nota(fila), cuaderno=fila["cuaderno"], seccion=fila["seccion"]
    )


def _a_vinculo(fila: sqlite3.Row) -> Vinculo:
    return Vinculo(
        id=fila["id"],
        nota_id=fila["nota_id"],
        materia_id=fila["materia_id"],
        modulo_id=fila["modulo_id"],
        documento_id=fila["documento_id"],
        anotacion_id=fila["anotacion_id"],
        pagina=fila["pagina"],
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
