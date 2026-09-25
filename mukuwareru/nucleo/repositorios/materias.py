"""Acceso a la tabla ``materia``."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import date

from mukuwareru.nucleo.modelos.entidades import Materia, Prioridad
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha, transaccion

_CAMPOS = (
    "id, proyecto_id, nombre, orden, color, peso, "
    "horas_estimadas, horas_restantes_manual, prioridad, fecha_limite"
)


class RepositorioMaterias(Repositorio):
    """Consultas y escrituras sobre materias."""

    def listar(self, proyecto_id: int) -> list[Materia]:
        """Materias del proyecto, en su orden de presentacion."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM materia WHERE proyecto_id = ? ORDER BY orden, nombre",
            (proyecto_id,),
        ).fetchall()
        return [_a_materia(f) for f in filas]

    def obtener(self, materia_id: int) -> Materia | None:
        """Una materia por id, o ``None`` si ya no existe."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM materia WHERE id = ?", (materia_id,)
        ).fetchone()
        return _a_materia(fila) if fila else None

    def obtener_por_nombre(self, proyecto_id: int, nombre: str) -> Materia | None:
        """Busca una materia por su nombre exacto dentro del proyecto."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM materia WHERE proyecto_id = ? AND nombre = ?",
            (proyecto_id, nombre),
        ).fetchone()
        return _a_materia(fila) if fila else None

    def crear(
        self,
        proyecto_id: int,
        nombre: str,
        *,
        orden: int = 0,
        color: str | None = None,
        peso: float = 0.0,
    ) -> Materia:
        """Inserta una materia y la devuelve con su id."""
        cursor = self._cx.execute(
            "INSERT INTO materia (proyecto_id, nombre, orden, color, peso) "
            "VALUES (?, ?, ?, ?, ?)",
            (proyecto_id, nombre, orden, color, max(0.0, peso)),
        )
        return Materia(
            id=int(cursor.lastrowid or 0),
            proyecto_id=proyecto_id,
            nombre=nombre,
            orden=orden,
            color=color,
            peso=max(0.0, peso),
        )

    def obtener_o_crear(
        self,
        proyecto_id: int,
        nombre: str,
        *,
        orden: int = 0,
        color: str | None = None,
        peso: float = 0.0,
    ) -> Materia:
        """Devuelve la materia existente o la crea. Base de la importacion idempotente."""
        existente = self.obtener_por_nombre(proyecto_id, nombre)
        return existente or self.crear(
            proyecto_id, nombre, orden=orden, color=color, peso=peso
        )

    def renombrar(self, materia_id: int, nombre: str) -> None:
        """Cambia el nombre de una materia."""
        self._cx.execute("UPDATE materia SET nombre = ? WHERE id = ?", (nombre, materia_id))

    def fijar_color(self, materia_id: int, color: str | None) -> None:
        """Fija el color de una materia. ``None`` la devuelve al color de la serie.

        La columna existe desde el esquema inicial pero nadie la escribia, asi
        que el color de una materia cambiaba solo al renombrarla: sin valor
        propio, las vistas pintan por posicion en la lista.
        """
        self._cx.execute("UPDATE materia SET color = ? WHERE id = ?", (color, materia_id))

    # -- Carga de estudio ------------------------------------------------------

    def fijar_carga(
        self,
        materia_id: int,
        *,
        horas_estimadas: float | None,
        horas_restantes_manual: float | None,
        prioridad: Prioridad,
        fecha_limite: date | None,
    ) -> None:
        """Guarda de una vez las horas, la prioridad y la fecha limite.

        Los cuatro campos viajan juntos porque se editan juntos, en un unico
        dialogo. Partirlo en cuatro metodos obligaria a la vista a escribir
        cuatro veces para guardar un formulario.

        Las horas negativas se guardan como ``None`` y no como cero: cero es una
        estimacion legitima («esto no me cuesta nada»), y un valor negativo solo
        puede ser un error de escritura.
        """
        self._cx.execute(
            """
            UPDATE materia
               SET horas_estimadas = ?, horas_restantes_manual = ?,
                   prioridad = ?, fecha_limite = ?
             WHERE id = ?
            """,
            (
                _horas(horas_estimadas),
                _horas(horas_restantes_manual),
                int(prioridad),
                fecha_limite.isoformat() if fecha_limite else None,
                materia_id,
            ),
        )

    # -- Orden -----------------------------------------------------------------

    def reordenar(self, proyecto_id: int, ids: Sequence[int]) -> None:
        """Fija el orden de las materias del proyecto segun la lista de ids.

        Los ids que no se mencionen conservan su posicion relativa detras, y uno
        que no pertenezca al proyecto se ignora: el `WHERE proyecto_id` evita que
        una lista equivocada reordene el temario de otro proyecto.
        """
        for posicion, materia_id in enumerate(ids):
            self._cx.execute(
                "UPDATE materia SET orden = ? WHERE id = ? AND proyecto_id = ?",
                (posicion, materia_id, proyecto_id),
            )

    def mover(self, materia_id: int, desplazamiento: int) -> bool:
        """Sube o baja una materia dentro de su proyecto. Devuelve si se movio.

        Igual que en los modulos, se reescribe el orden del proyecto entero y no
        solo el del par que se intercambia: las materias importadas del Excel
        comparten `orden` (todas a 0), y ahi un intercambio de dos valores no
        cambiaria nada.
        """
        actual = self.obtener(materia_id)
        if actual is None:
            return False

        posiciones = [m.id for m in self.listar(actual.proyecto_id)]
        origen = posiciones.index(materia_id)
        destino = origen + desplazamiento
        if not 0 <= destino < len(posiciones):
            return False

        posiciones[origen], posiciones[destino] = posiciones[destino], posiciones[origen]
        self.reordenar(actual.proyecto_id, posiciones)
        return True

    # -- Pesos -----------------------------------------------------------------

    def fijar_pesos(self, proyecto_id: int, pesos: Mapping[int, float]) -> None:
        """Escribe varios pesos de golpe, dentro de una unica transaccion.

        El `WHERE proyecto_id` es la misma defensa que en `reordenar`: un id que
        no sea del proyecto se ignora en vez de alterar otro temario.
        """
        with transaccion(self._cx):
            for materia_id, peso in pesos.items():
                self._cx.execute(
                    "UPDATE materia SET peso = ? WHERE id = ? AND proyecto_id = ?",
                    (max(0.0, peso), materia_id, proyecto_id),
                )

    def limpiar_pesos(self, proyecto_id: int) -> None:
        """Devuelve todo el proyecto al progreso por conteo de modulos."""
        self._cx.execute("UPDATE materia SET peso = 0 WHERE proyecto_id = ?", (proyecto_id,))

    def eliminar(self, materia_id: int) -> None:
        """Borra la materia y, en cascada, sus modulos."""
        self._cx.execute("DELETE FROM materia WHERE id = ?", (materia_id,))


def _horas(valor: float | None) -> float | None:
    """Normaliza unas horas: negativas o ausentes son «sin dato»."""
    if valor is None or valor < 0:
        return None
    return float(valor)


def _a_materia(fila: sqlite3.Row) -> Materia:
    estimadas = fila["horas_estimadas"]
    manual = fila["horas_restantes_manual"]
    return Materia(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        nombre=fila["nombre"],
        orden=fila["orden"],
        color=fila["color"],
        peso=float(fila["peso"]),
        horas_estimadas=float(estimadas) if estimadas is not None else None,
        horas_restantes_manual=float(manual) if manual is not None else None,
        prioridad=Prioridad(int(fila["prioridad"])),
        fecha_limite=a_fecha(fila["fecha_limite"]),
    )
