"""Acceso a la tabla ``proyecto``."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date

from mukuwareru.nucleo.modelos.entidades import Proyecto
from mukuwareru.nucleo.repositorios.base import (
    Repositorio,
    a_fecha,
    a_fecha_hora,
    ahora_iso,
    transaccion,
)

_CAMPOS = """
    id, nombre, icono, color, fecha_objetivo, ruta_biblioteca,
    orden, archivado, creado_en
"""

# Lo que se pierde al borrar un proyecto. El orden es el del dialogo de
# confirmacion: primero el temario, luego el material, luego el tiempo.
_DEPENDENCIAS = """
    SELECT
        (SELECT COUNT(*) FROM materia   WHERE proyecto_id = ?)          AS materias,
        (SELECT COUNT(*) FROM modulo    WHERE materia_id IN
            (SELECT id FROM materia WHERE proyecto_id = ?))             AS modulos,
        (SELECT COUNT(*) FROM documento WHERE proyecto_id = ?)          AS documentos,
        (SELECT COUNT(*) FROM sesion    WHERE proyecto_id = ?)          AS sesiones,
        (SELECT COUNT(*) FROM anotacion WHERE documento_id IN
            (SELECT id FROM documento WHERE proyecto_id = ?))           AS anotaciones
"""


class RepositorioProyectos(Repositorio):
    """Consultas y escrituras sobre proyectos."""

    def listar(self, incluir_archivados: bool = False) -> list[Proyecto]:
        """Proyectos ordenados por ``orden`` y luego por nombre."""
        filtro = "" if incluir_archivados else "WHERE archivado = 0"
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM proyecto {filtro} ORDER BY orden, nombre"
        ).fetchall()
        return [_a_proyecto(f) for f in filas]

    def obtener(self, proyecto_id: int) -> Proyecto | None:
        """Un proyecto por id, o ``None`` si no existe."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM proyecto WHERE id = ?", (proyecto_id,)
        ).fetchone()
        return _a_proyecto(fila) if fila else None

    def crear(
        self,
        nombre: str,
        *,
        icono: str = "libro",
        color: str = "#E5484D",
        fecha_objetivo: date | None = None,
        ruta_biblioteca: str | None = None,
    ) -> Proyecto:
        """Inserta un proyecto y lo devuelve ya con su id."""
        siguiente = self._cx.execute(
            "SELECT COALESCE(MAX(orden), -1) + 1 FROM proyecto"
        ).fetchone()[0]
        cursor = self._cx.execute(
            """
            INSERT INTO proyecto
                (nombre, icono, color, fecha_objetivo, ruta_biblioteca, orden, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre,
                icono,
                color,
                fecha_objetivo.isoformat() if fecha_objetivo else None,
                ruta_biblioteca,
                siguiente,
                ahora_iso(),
            ),
        )
        creado = self.obtener(int(cursor.lastrowid or 0))
        assert creado is not None
        return creado

    def actualizar(self, proyecto: Proyecto) -> None:
        """Guarda los campos editables de un proyecto existente."""
        self._cx.execute(
            """
            UPDATE proyecto
               SET nombre = ?, icono = ?, color = ?, fecha_objetivo = ?,
                   ruta_biblioteca = ?, orden = ?, archivado = ?
             WHERE id = ?
            """,
            (
                proyecto.nombre,
                proyecto.icono,
                proyecto.color,
                proyecto.fecha_objetivo.isoformat() if proyecto.fecha_objetivo else None,
                proyecto.ruta_biblioteca,
                proyecto.orden,
                int(proyecto.archivado),
                proyecto.id,
            ),
        )

    def reordenar(self, ids: Sequence[int]) -> None:
        """Fija ``orden`` = 0..n-1 segun la secuencia recibida.

        Se reasignan todos los valores en lugar de intercambiar dos: asi el
        resultado no depende de como estuviera la columna antes, que en bases
        antiguas puede tener empates.
        """
        with transaccion(self._cx):
            self._cx.executemany(
                "UPDATE proyecto SET orden = ? WHERE id = ?",
                [(posicion, proyecto_id) for posicion, proyecto_id in enumerate(ids)],
            )

    def contar_dependencias(self, proyecto_id: int) -> dict[str, int]:
        """Cuantas filas se llevaria por delante ``eliminar``.

        La cascada es transitiva (proyecto -> documento -> anotacion), asi que
        el dialogo de confirmacion no puede deducirla contando una sola tabla.
        """
        fila = self._cx.execute(_DEPENDENCIAS, (proyecto_id,) * 5).fetchone()
        return {
            clave: int(fila[clave])
            for clave in ("materias", "modulos", "documentos", "sesiones", "anotaciones")
        }

    def eliminar(self, proyecto_id: int) -> None:
        """Borra el proyecto y, en cascada, todo lo que cuelga de el."""
        self._cx.execute("DELETE FROM proyecto WHERE id = ?", (proyecto_id,))


def _a_proyecto(fila: sqlite3.Row) -> Proyecto:
    return Proyecto(
        id=fila["id"],
        nombre=fila["nombre"],
        icono=fila["icono"],
        color=fila["color"],
        fecha_objetivo=a_fecha(fila["fecha_objetivo"]),
        ruta_biblioteca=fila["ruta_biblioteca"],
        orden=fila["orden"],
        archivado=bool(fila["archivado"]),
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
