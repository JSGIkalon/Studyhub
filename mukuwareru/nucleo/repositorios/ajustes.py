"""Acceso a la tabla ``ajuste``: almacen clave/valor.

``proyecto_id`` a ``NULL`` significa ajuste global. Los indices parciales del
esquema garantizan que no haya claves duplicadas en ninguno de los dos ambitos.
"""

from __future__ import annotations

from mukuwareru.nucleo.repositorios.base import Repositorio


class RepositorioAjustes(Repositorio):
    """Lectura y escritura de ajustes globales y por proyecto."""

    def obtener(self, clave: str, proyecto_id: int | None = None) -> str | None:
        """Valor de una clave, o ``None`` si no esta guardada."""
        if proyecto_id is None:
            fila = self._cx.execute(
                "SELECT valor FROM ajuste WHERE proyecto_id IS NULL AND clave = ?", (clave,)
            ).fetchone()
        else:
            fila = self._cx.execute(
                "SELECT valor FROM ajuste WHERE proyecto_id = ? AND clave = ?",
                (proyecto_id, clave),
            ).fetchone()
        return fila["valor"] if fila else None

    def establecer(self, clave: str, valor: str, proyecto_id: int | None = None) -> None:
        """Guarda o reemplaza el valor de una clave."""
        if proyecto_id is None:
            self._cx.execute("DELETE FROM ajuste WHERE proyecto_id IS NULL AND clave = ?", (clave,))
        else:
            self._cx.execute(
                "DELETE FROM ajuste WHERE proyecto_id = ? AND clave = ?", (proyecto_id, clave)
            )
        self._cx.execute(
            "INSERT INTO ajuste (proyecto_id, clave, valor) VALUES (?, ?, ?)",
            (proyecto_id, clave, valor),
        )

    def todos(self, proyecto_id: int | None = None) -> dict[str, str]:
        """Todos los ajustes del ambito indicado."""
        if proyecto_id is None:
            filas = self._cx.execute(
                "SELECT clave, valor FROM ajuste WHERE proyecto_id IS NULL"
            ).fetchall()
        else:
            filas = self._cx.execute(
                "SELECT clave, valor FROM ajuste WHERE proyecto_id = ?", (proyecto_id,)
            ).fetchall()
        return {f["clave"]: f["valor"] for f in filas}
