"""Acceso a las tablas ``cuaderno`` y ``seccion``.

Las dos van en el mismo repositorio porque son un solo arbol de dos niveles y no
se consultan por separado: pintar el panel de Notas necesita las dos a la vez.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from mukuwareru.nucleo.modelos.entidades import Cuaderno, Seccion
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha_hora, ahora_iso, transaccion

_CAMPOS_CUADERNO = "id, proyecto_id, nombre, color, orden, creado_en"
_CAMPOS_SECCION = "id, cuaderno_id, nombre, color, orden, creado_en"
# La misma lista cualificada, para las consultas con JOIN sobre `cuaderno`.
_CAMPOS_SECCION_S = "s.id, s.cuaderno_id, s.nombre, s.color, s.orden, s.creado_en"

NOMBRE_POR_DEFECTO = "General"


class RepositorioCuadernos(Repositorio):
    """Cuadernos y secciones: el arbol donde viven las notas."""

    # -- Cuadernos ----------------------------------------------------------

    def listar(self, proyecto_id: int) -> list[Cuaderno]:
        """Cuadernos del proyecto, en su orden."""
        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS_CUADERNO} FROM cuaderno
             WHERE proyecto_id = ? ORDER BY orden, nombre
            """,
            (proyecto_id,),
        ).fetchall()
        return [_a_cuaderno(f) for f in filas]

    def obtener(self, cuaderno_id: int) -> Cuaderno | None:
        """Un cuaderno por id, o ``None``."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS_CUADERNO} FROM cuaderno WHERE id = ?", (cuaderno_id,)
        ).fetchone()
        return _a_cuaderno(fila) if fila else None

    def crear(
        self, proyecto_id: int, nombre: str, *, color: str | None = None
    ) -> Cuaderno:
        """Inserta un cuaderno al final de la lista del proyecto."""
        siguiente = self._cx.execute(
            "SELECT COALESCE(MAX(orden), -1) + 1 FROM cuaderno WHERE proyecto_id = ?",
            (proyecto_id,),
        ).fetchone()[0]
        cursor = self._cx.execute(
            """
            INSERT INTO cuaderno (proyecto_id, nombre, color, orden, creado_en)
            VALUES (?, ?, ?, ?, ?)
            """,
            (proyecto_id, nombre, color, siguiente, ahora_iso()),
        )
        creado = self.obtener(int(cursor.lastrowid or 0))
        assert creado is not None
        return creado

    def renombrar(self, cuaderno_id: int, nombre: str) -> None:
        """Cambia el nombre de un cuaderno."""
        self._cx.execute(
            "UPDATE cuaderno SET nombre = ? WHERE id = ?", (nombre, cuaderno_id)
        )

    def reordenar(self, ids: Sequence[int]) -> None:
        """Fija ``orden`` = 0..n-1 segun la secuencia recibida."""
        with transaccion(self._cx):
            self._cx.executemany(
                "UPDATE cuaderno SET orden = ? WHERE id = ?",
                [(posicion, id_) for posicion, id_ in enumerate(ids)],
            )

    def eliminar(self, cuaderno_id: int) -> None:
        """Borra el cuaderno y, en cascada, sus secciones y sus notas."""
        self._cx.execute("DELETE FROM cuaderno WHERE id = ?", (cuaderno_id,))

    # -- Secciones ----------------------------------------------------------

    def listar_secciones(self, cuaderno_id: int) -> list[Seccion]:
        """Secciones de un cuaderno, en su orden."""
        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS_SECCION} FROM seccion
             WHERE cuaderno_id = ? ORDER BY orden, nombre
            """,
            (cuaderno_id,),
        ).fetchall()
        return [_a_seccion(f) for f in filas]

    def obtener_seccion(self, seccion_id: int) -> Seccion | None:
        """Una seccion por id, o ``None``."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS_SECCION} FROM seccion WHERE id = ?", (seccion_id,)
        ).fetchone()
        return _a_seccion(fila) if fila else None

    def crear_seccion(
        self, cuaderno_id: int, nombre: str, *, color: str | None = None
    ) -> Seccion:
        """Inserta una seccion al final de su cuaderno."""
        siguiente = self._cx.execute(
            "SELECT COALESCE(MAX(orden), -1) + 1 FROM seccion WHERE cuaderno_id = ?",
            (cuaderno_id,),
        ).fetchone()[0]
        cursor = self._cx.execute(
            """
            INSERT INTO seccion (cuaderno_id, nombre, color, orden, creado_en)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cuaderno_id, nombre, color, siguiente, ahora_iso()),
        )
        creada = self.obtener_seccion(int(cursor.lastrowid or 0))
        assert creada is not None
        return creada

    def renombrar_seccion(self, seccion_id: int, nombre: str) -> None:
        """Cambia el nombre de una seccion."""
        self._cx.execute(
            "UPDATE seccion SET nombre = ? WHERE id = ?", (nombre, seccion_id)
        )

    def eliminar_seccion(self, seccion_id: int) -> None:
        """Borra la seccion y, en cascada, sus notas."""
        self._cx.execute("DELETE FROM seccion WHERE id = ?", (seccion_id,))

    def contar_secciones(self, cuaderno_id: int) -> int:
        """Cuantas secciones tiene el cuaderno."""
        fila = self._cx.execute(
            "SELECT COUNT(*) FROM seccion WHERE cuaderno_id = ?", (cuaderno_id,)
        ).fetchone()
        return int(fila[0])

    # -- Siembra y conteos --------------------------------------------------

    def asegurar_por_defecto(self, proyecto_id: int) -> Seccion:
        """Primera seccion del proyecto, creandola si no hay ninguna.

        Es el unico camino de siembra, y por eso la migracion 002 no inserta
        nada: sirve igual para los proyectos que ya existian antes de que las
        notas existieran y para los que se creen manana.
        """
        fila = self._cx.execute(
            f"""
            SELECT {_CAMPOS_SECCION_S} FROM seccion s
              JOIN cuaderno c ON c.id = s.cuaderno_id
             WHERE c.proyecto_id = ?
             ORDER BY c.orden, c.id, s.orden, s.id
             LIMIT 1
            """,
            (proyecto_id,),
        ).fetchone()
        if fila is not None:
            return _a_seccion(fila)

        cuadernos = self.listar(proyecto_id)
        cuaderno = cuadernos[0] if cuadernos else self.crear(
            proyecto_id, NOMBRE_POR_DEFECTO
        )
        return self.crear_seccion(cuaderno.id, NOMBRE_POR_DEFECTO)

    def contar_notas(self, proyecto_id: int) -> dict[int, int]:
        """Notas por seccion, para los contadores del arbol.

        Una consulta y no una por seccion: el arbol se repinta a menudo.
        """
        filas = self._cx.execute(
            """
            SELECT s.id AS seccion_id, COUNT(n.id) AS total
              FROM seccion s
              JOIN cuaderno c ON c.id = s.cuaderno_id
              LEFT JOIN nota n ON n.seccion_id = s.id
             WHERE c.proyecto_id = ?
             GROUP BY s.id
            """,
            (proyecto_id,),
        ).fetchall()
        return {int(f["seccion_id"]): int(f["total"]) for f in filas}


def _a_cuaderno(fila: sqlite3.Row) -> Cuaderno:
    return Cuaderno(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        nombre=fila["nombre"],
        color=fila["color"],
        orden=fila["orden"],
        creado_en=a_fecha_hora(fila["creado_en"]),
    )


def _a_seccion(fila: sqlite3.Row) -> Seccion:
    return Seccion(
        id=fila["id"],
        cuaderno_id=fila["cuaderno_id"],
        nombre=fila["nombre"],
        color=fila["color"],
        orden=fila["orden"],
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
