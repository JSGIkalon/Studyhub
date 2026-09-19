"""Acceso a la tabla ``anotacion``.

Marcador, nota y resaltado comparten tabla porque son la misma cosa: un ancla en
una pagina con texto y comentario opcionales.
"""

from __future__ import annotations

import json
import sqlite3

from mukuwareru.nucleo.modelos.entidades import Anotacion, TipoAnotacion
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha_hora, ahora_iso

_CAMPOS = """
    id, documento_id, tipo, pagina, rects_json,
    texto_seleccionado, comentario, color, creado_en
"""

_CAMPOS_A = """
    a.id, a.documento_id, a.tipo, a.pagina, a.rects_json,
    a.texto_seleccionado, a.comentario, a.color, a.creado_en
"""


class RepositorioAnotaciones(Repositorio):
    """Consultas y escrituras sobre marcadores, notas y resaltados."""

    def listar(self, documento_id: int) -> list[Anotacion]:
        """Anotaciones de un documento, en orden de lectura."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM anotacion WHERE documento_id = ? ORDER BY pagina, id",
            (documento_id,),
        ).fetchall()
        return [_a_anotacion(f) for f in filas]

    def obtener(self, anotacion_id: int) -> Anotacion | None:
        """Una anotacion por id, o ``None`` si ya no existe."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM anotacion WHERE id = ?", (anotacion_id,)
        ).fetchone()
        return _a_anotacion(fila) if fila else None

    def obtener_con_documento(self, anotacion_id: int) -> tuple[Anotacion, str] | None:
        """Una anotacion junto al nombre de su PDF.

        Lo necesita el panel «Relacionado con» de una nota: un vinculo a una
        anotacion no se puede presentar sin decir de que documento es.
        """
        fila = self._cx.execute(
            f"""
            SELECT {_CAMPOS_A}, d.nombre AS documento
              FROM anotacion a
              JOIN documento d ON d.id = a.documento_id
             WHERE a.id = ?
            """,
            (anotacion_id,),
        ).fetchone()
        return (_a_anotacion(fila), fila["documento"]) if fila else None

    def listar_del_proyecto(
        self, proyecto_id: int, tipo: TipoAnotacion | None = None
    ) -> list[tuple[Anotacion, str]]:
        """Anotaciones de todo el proyecto junto al nombre de su documento."""
        condiciones = ["d.proyecto_id = ?"]
        parametros: list[object] = [proyecto_id]
        if tipo is not None:
            condiciones.append("a.tipo = ?")
            parametros.append(str(tipo))

        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS_A}, d.nombre AS documento
              FROM anotacion a
              JOIN documento d ON d.id = a.documento_id
             WHERE {' AND '.join(condiciones)}
             ORDER BY a.creado_en DESC
            """,
            parametros,
        ).fetchall()
        return [(_a_anotacion(f), f["documento"]) for f in filas]

    def crear(
        self,
        documento_id: int,
        *,
        tipo: TipoAnotacion,
        pagina: int,
        rects: list[tuple[float, float, float, float]] | None = None,
        texto_seleccionado: str | None = None,
        comentario: str | None = None,
        color: str = "#F5A524",
    ) -> Anotacion:
        """Crea una anotacion anclada a una pagina."""
        cursor = self._cx.execute(
            """
            INSERT INTO anotacion
                (documento_id, tipo, pagina, rects_json,
                 texto_seleccionado, comentario, color, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                documento_id,
                str(tipo),
                pagina,
                json.dumps(rects or []),
                texto_seleccionado,
                comentario,
                color,
                ahora_iso(),
            ),
        )
        return Anotacion(
            id=int(cursor.lastrowid or 0),
            documento_id=documento_id,
            tipo=tipo,
            pagina=pagina,
            rects=list(rects or []),
            texto_seleccionado=texto_seleccionado,
            comentario=comentario,
            color=color,
        )

    def actualizar_comentario(self, anotacion_id: int, comentario: str | None) -> None:
        """Cambia el comentario de una anotacion."""
        self._cx.execute(
            "UPDATE anotacion SET comentario = ? WHERE id = ?", (comentario, anotacion_id)
        )

    def eliminar(self, anotacion_id: int) -> None:
        """Borra una anotacion."""
        self._cx.execute("DELETE FROM anotacion WHERE id = ?", (anotacion_id,))

    def contar(self, proyecto_id: int) -> int:
        """Numero de anotaciones del proyecto."""
        fila = self._cx.execute(
            """
            SELECT COUNT(*) FROM anotacion a
              JOIN documento d ON d.id = a.documento_id
             WHERE d.proyecto_id = ?
            """,
            (proyecto_id,),
        ).fetchone()
        return int(fila[0])


def _a_anotacion(fila: sqlite3.Row) -> Anotacion:
    return Anotacion(
        id=fila["id"],
        documento_id=fila["documento_id"],
        tipo=TipoAnotacion(fila["tipo"]),
        pagina=fila["pagina"],
        rects=[tuple(r) for r in json.loads(fila["rects_json"] or "[]")],
        texto_seleccionado=fila["texto_seleccionado"],
        comentario=fila["comentario"],
        color=fila["color"],
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
