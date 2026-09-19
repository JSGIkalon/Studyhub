"""Acceso a la tabla ``hito``.

Un hito es una fecha con nombre: el examen, una entrega, un mock. Sustituye con
ventaja a la unica ``proyecto.fecha_objetivo``, que se conserva y se espeja en el
hito marcado como ``principal``.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from mukuwareru.nucleo.modelos.entidades import Hito, TipoHito
from mukuwareru.nucleo.repositorios.base import (
    Repositorio,
    a_fecha,
    a_fecha_hora,
    ahora_iso,
)

_CAMPOS = """
    id, proyecto_id, titulo, tipo, fecha, hora, nota, color,
    principal, completado, completado_en, creado_en
"""


class RepositorioHitos(Repositorio):
    """Consultas y escrituras sobre las fechas clave de un proyecto."""

    def listar(
        self, proyecto_id: int, *, desde: str | None = None, hasta: str | None = None
    ) -> list[Hito]:
        """Hitos ordenados por fecha. Extremos inclusivos; ``None`` sin limite."""
        condiciones = ["proyecto_id = ?"]
        parametros: list[object] = [proyecto_id]
        if desde is not None:
            condiciones.append("fecha >= ?")
            parametros.append(desde)
        if hasta is not None:
            condiciones.append("fecha <= ?")
            parametros.append(hasta)

        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS} FROM hito
             WHERE {' AND '.join(condiciones)}
             ORDER BY fecha, hora, id
            """,
            parametros,
        ).fetchall()
        return [_a_hito(f) for f in filas]

    def obtener(self, hito_id: int) -> Hito | None:
        """Un hito por id, o ``None``."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM hito WHERE id = ?", (hito_id,)
        ).fetchone()
        return _a_hito(fila) if fila else None

    def proximos(self, proyecto_id: int, desde: str, limite: int = 3) -> list[Hito]:
        """Hitos sin completar cuya fecha es hoy o posterior."""
        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS} FROM hito
             WHERE proyecto_id = ? AND completado = 0 AND fecha >= ?
             ORDER BY fecha, hora, id
             LIMIT ?
            """,
            (proyecto_id, desde, limite),
        ).fetchall()
        return [_a_hito(f) for f in filas]

    def principal(self, proyecto_id: int) -> Hito | None:
        """El hito que espeja ``proyecto.fecha_objetivo``, si existe."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM hito WHERE proyecto_id = ? AND principal = 1",
            (proyecto_id,),
        ).fetchone()
        return _a_hito(fila) if fila else None

    def crear(
        self,
        proyecto_id: int,
        titulo: str,
        fecha: date,
        *,
        tipo: TipoHito = TipoHito.HITO,
        hora: str | None = None,
        nota: str | None = None,
        color: str | None = None,
        principal: bool = False,
    ) -> Hito:
        """Inserta un hito y lo devuelve ya con su id."""
        cursor = self._cx.execute(
            """
            INSERT INTO hito
                (proyecto_id, titulo, tipo, fecha, hora, nota, color, principal, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proyecto_id, titulo, str(tipo), fecha.isoformat(), hora, nota, color,
                int(principal), ahora_iso(),
            ),
        )
        creado = self.obtener(int(cursor.lastrowid or 0))
        assert creado is not None
        return creado

    def actualizar(self, hito: Hito) -> None:
        """Guarda los campos editables de un hito existente."""
        self._cx.execute(
            """
            UPDATE hito
               SET titulo = ?, tipo = ?, fecha = ?, hora = ?, nota = ?, color = ?
             WHERE id = ?
            """,
            (
                hito.titulo, str(hito.tipo), hito.fecha.isoformat(),
                hito.hora, hito.nota, hito.color, hito.id,
            ),
        )

    def marcar_completado(self, hito_id: int, completado: bool) -> None:
        """Da un hito por cumplido, o lo devuelve a pendiente."""
        self._cx.execute(
            "UPDATE hito SET completado = ?, completado_en = ? WHERE id = ?",
            (int(completado), ahora_iso() if completado else None, hito_id),
        )

    def eliminar(self, hito_id: int) -> None:
        """Borra un hito."""
        self._cx.execute("DELETE FROM hito WHERE id = ?", (hito_id,))

    def fijar_objetivo(self, proyecto_id: int, fecha: date | None) -> None:
        """Crea, mueve o borra el hito ``principal`` del proyecto.

        Lo llama ``ServicioProyectos`` al guardar, para que la columna
        ``proyecto.fecha_objetivo`` y el calendario no puedan discrepar. El
        indice unico parcial ``idx_hito_principal`` garantiza que no haya dos.
        """
        actual = self.principal(proyecto_id)
        if fecha is None:
            if actual is not None:
                self.eliminar(actual.id)
            return

        if actual is None:
            self.crear(
                proyecto_id,
                "Fecha objetivo",
                fecha,
                tipo=TipoHito.EXAMEN,
                principal=True,
            )
            return

        # Solo la fecha: el titulo y el tipo pueden haberse editado a mano desde
        # el calendario, y pisarlos en cada guardado del proyecto seria molesto.
        self._cx.execute(
            "UPDATE hito SET fecha = ? WHERE id = ?", (fecha.isoformat(), actual.id)
        )


def _a_hito(fila: sqlite3.Row) -> Hito:
    fecha = a_fecha(fila["fecha"])
    assert fecha is not None
    return Hito(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        titulo=fila["titulo"],
        fecha=fecha,
        tipo=TipoHito(fila["tipo"]),
        hora=fila["hora"],
        nota=fila["nota"],
        color=fila["color"],
        principal=bool(fila["principal"]),
        completado=bool(fila["completado"]),
        completado_en=a_fecha_hora(fila["completado_en"]),
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
