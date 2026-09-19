"""Acceso a las tablas ``evaluacion`` y ``evaluacion_materia``.

El desglose por asignatura se lee siempre junto a su evaluacion: no significa
nada por separado y son pocas filas. El porcentaje nunca se guarda, se calcula
(ver ``Evaluacion.porcentaje``).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from mukuwareru.nucleo.modelos.entidades import Evaluacion, LineaEvaluacion
from mukuwareru.nucleo.repositorios.base import (
    Repositorio,
    a_fecha,
    a_fecha_hora,
    ahora_iso,
)

_CAMPOS = """
    id, proyecto_id, hito_id, titulo, fecha, puntos_obtenidos,
    puntos_posibles, peso, nota, creado_en
"""


@dataclass(frozen=True, slots=True)
class LineaPesada:
    """Una linea de desglose con el contexto que el servicio necesita.

    Vive aqui y no en ``entidades`` porque es la forma de una consulta, no una
    cosa del dominio: exactamente el mismo criterio que ``ConteoMateria``.
    """

    materia_id: int
    nombre: str
    peso_materia: float
    peso_evaluacion: float
    puntos_obtenidos: float
    puntos_posibles: float

    @property
    def fraccion(self) -> float:
        """Acierto de esta linea entre 0 y 1."""
        return self.puntos_obtenidos / self.puntos_posibles


class RepositorioEvaluaciones(Repositorio):
    """Resultados de examenes y su desglose por asignatura."""

    def listar(self, proyecto_id: int) -> list[Evaluacion]:
        """Evaluaciones de mas reciente a mas antigua, con su desglose.

        Las lineas se leen en una sola consulta y se reparten en memoria, igual
        que en ``RepositorioBloques.listar``: una consulta por evaluacion
        convertiria pintar el historial en decenas de viajes.
        """
        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS} FROM evaluacion
             WHERE proyecto_id = ?
             ORDER BY fecha DESC, id DESC
            """,
            (proyecto_id,),
        ).fetchall()
        evaluaciones = [_a_evaluacion(f) for f in filas]
        if not evaluaciones:
            return []

        marcadores = ",".join("?" * len(evaluaciones))
        lineas = self._cx.execute(
            f"""
            SELECT evaluacion_id, materia_id, puntos_obtenidos, puntos_posibles
              FROM evaluacion_materia
             WHERE evaluacion_id IN ({marcadores})
            """,
            [e.id for e in evaluaciones],
        ).fetchall()
        por_evaluacion: dict[int, list[LineaEvaluacion]] = {}
        for fila in lineas:
            por_evaluacion.setdefault(int(fila["evaluacion_id"]), []).append(
                _a_linea(fila)
            )
        for evaluacion in evaluaciones:
            evaluacion.materias = por_evaluacion.get(evaluacion.id, [])
        return evaluaciones

    def obtener(self, evaluacion_id: int) -> Evaluacion | None:
        """Una evaluacion por id, con su desglose. ``None`` si ya no existe."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM evaluacion WHERE id = ?", (evaluacion_id,)
        ).fetchone()
        if fila is None:
            return None
        evaluacion = _a_evaluacion(fila)
        evaluacion.materias = self.desglose_de(evaluacion_id)
        return evaluacion

    def por_hito(self, hito_id: int) -> Evaluacion | None:
        """El resultado anotado sobre una fecha del calendario, si lo hay."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM evaluacion WHERE hito_id = ?", (hito_id,)
        ).fetchone()
        return self.obtener(int(fila["id"])) if fila else None

    def crear(
        self,
        proyecto_id: int,
        titulo: str,
        fecha: date,
        puntos_obtenidos: float | None,
        puntos_posibles: float,
        *,
        peso: float = 1.0,
        hito_id: int | None = None,
        nota: str | None = None,
        materias: Sequence[LineaEvaluacion] | None = None,
    ) -> Evaluacion:
        """Inserta una evaluacion con su desglose y la devuelve ya con su id.

        ``puntos_obtenidos`` en ``None`` da de alta una evaluacion **pendiente**:
        declarada con su peso y su fecha, sin nota todavia.
        """
        cursor = self._cx.execute(
            """
            INSERT INTO evaluacion
                (proyecto_id, hito_id, titulo, fecha, puntos_obtenidos,
                 puntos_posibles, peso, nota, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proyecto_id, hito_id, titulo, fecha.isoformat(),
                puntos_obtenidos, puntos_posibles, max(0.0, peso), nota, ahora_iso(),
            ),
        )
        evaluacion_id = int(cursor.lastrowid or 0)
        if materias:
            self.desglosar(evaluacion_id, materias)
        creada = self.obtener(evaluacion_id)
        assert creada is not None
        return creada

    def actualizar(self, evaluacion: Evaluacion) -> None:
        """Guarda los campos editables. NO toca el desglose: usa ``desglosar``."""
        self._cx.execute(
            """
            UPDATE evaluacion
               SET titulo = ?, fecha = ?, puntos_obtenidos = ?, puntos_posibles = ?,
                   peso = ?, hito_id = ?, nota = ?
             WHERE id = ?
            """,
            (
                evaluacion.titulo, evaluacion.fecha.isoformat(),
                evaluacion.puntos_obtenidos, evaluacion.puntos_posibles,
                max(0.0, evaluacion.peso), evaluacion.hito_id, evaluacion.nota,
                evaluacion.id,
            ),
        )

    def desglose_de(self, evaluacion_id: int) -> list[LineaEvaluacion]:
        """Lineas de una evaluacion, por materia."""
        filas = self._cx.execute(
            """
            SELECT materia_id, puntos_obtenidos, puntos_posibles
              FROM evaluacion_materia WHERE evaluacion_id = ?
            """,
            (evaluacion_id,),
        ).fetchall()
        return [_a_linea(f) for f in filas]

    def desglosar(
        self, evaluacion_id: int, materias: Sequence[LineaEvaluacion]
    ) -> None:
        """Reemplaza el desglose entero. Calca ``RepositorioBloques.etiquetar``.

        Pasar una secuencia vacia deja la evaluacion solo con su nota global.
        """
        self._cx.execute(
            "DELETE FROM evaluacion_materia WHERE evaluacion_id = ?", (evaluacion_id,)
        )
        self._cx.executemany(
            """
            INSERT INTO evaluacion_materia
                (evaluacion_id, materia_id, puntos_obtenidos, puntos_posibles)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    evaluacion_id, linea.materia_id,
                    linea.puntos_obtenidos, linea.puntos_posibles,
                )
                for linea in materias
            ],
        )

    def eliminar(self, evaluacion_id: int) -> None:
        """Borra la evaluacion y, en cascada, su desglose."""
        self._cx.execute("DELETE FROM evaluacion WHERE id = ?", (evaluacion_id,))

    def lineas_por_materia(self, proyecto_id: int) -> list[LineaPesada]:
        """Todas las lineas del proyecto con el peso de su evaluacion y su materia.

        Es la consulta que alimenta ``ServicioResultados``: un unico JOIN en
        lugar de recorrer las evaluaciones una por una desde el servicio.

        Las pendientes quedan fuera: sin nota global no hay desglose que valga, y
        colar sus lineas hundiria la nota de la asignatura con ceros de examenes
        que aun no se han hecho.
        """
        filas = self._cx.execute(
            """
            SELECT em.materia_id       AS materia_id,
                   m.nombre            AS nombre,
                   m.peso              AS peso_materia,
                   e.peso              AS peso_evaluacion,
                   em.puntos_obtenidos AS puntos_obtenidos,
                   em.puntos_posibles  AS puntos_posibles
              FROM evaluacion_materia em
              JOIN evaluacion e ON e.id = em.evaluacion_id
              JOIN materia m    ON m.id = em.materia_id
             WHERE e.proyecto_id = ?
            """,
            (proyecto_id,),
        ).fetchall()
        return [
            LineaPesada(
                materia_id=f["materia_id"],
                nombre=f["nombre"],
                peso_materia=float(f["peso_materia"]),
                peso_evaluacion=float(f["peso_evaluacion"]),
                puntos_obtenidos=float(f["puntos_obtenidos"]),
                puntos_posibles=float(f["puntos_posibles"]),
            )
            for f in filas
        ]

    def conteo(self, proyecto_id: int) -> int:
        """Cuantas evaluaciones tiene el proyecto. Para el estado vacio."""
        fila = self._cx.execute(
            "SELECT COUNT(*) FROM evaluacion WHERE proyecto_id = ?", (proyecto_id,)
        ).fetchone()
        return int(fila[0])


def _a_linea(fila: sqlite3.Row) -> LineaEvaluacion:
    return LineaEvaluacion(
        materia_id=fila["materia_id"],
        puntos_obtenidos=float(fila["puntos_obtenidos"]),
        puntos_posibles=float(fila["puntos_posibles"]),
    )


def _a_evaluacion(fila: sqlite3.Row) -> Evaluacion:
    fecha = a_fecha(fila["fecha"])
    assert fecha is not None
    obtenidos = fila["puntos_obtenidos"]
    return Evaluacion(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        titulo=fila["titulo"],
        fecha=fecha,
        puntos_obtenidos=float(obtenidos) if obtenidos is not None else None,
        puntos_posibles=float(fila["puntos_posibles"]),
        peso=float(fila["peso"]),
        hito_id=fila["hito_id"],
        nota=fila["nota"],
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
