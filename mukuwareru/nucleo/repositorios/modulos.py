"""Acceso a la tabla ``modulo`` y al recuento de progreso."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from mukuwareru.nucleo.modelos.entidades import Modulo
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha_hora, ahora_iso, transaccion

_CAMPOS = (
    "id, materia_id, nombre, orden, completado, completado_en, horas_estimadas"
)


@dataclass(frozen=True, slots=True)
class ConteoMateria:
    """Cuantos modulos tiene una materia, cuantos estan completados y su peso."""

    materia_id: int
    nombre: str
    total: int
    completados: int
    peso: float = 0.0
    color: str | None = None


class RepositorioModulos(Repositorio):
    """Consultas y escrituras sobre modulos."""

    def listar(self, materia_id: int) -> list[Modulo]:
        """Modulos de una materia, en su orden de presentacion."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM modulo WHERE materia_id = ? ORDER BY orden, nombre",
            (materia_id,),
        ).fetchall()
        return [_a_modulo(f) for f in filas]

    def obtener(self, modulo_id: int) -> Modulo | None:
        """Un modulo por id, o ``None`` si ya no existe."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM modulo WHERE id = ?", (modulo_id,)
        ).fetchone()
        return _a_modulo(fila) if fila else None

    def crear(
        self, materia_id: int, nombre: str, *, orden: int = 0, completado: bool = False
    ) -> Modulo:
        """Inserta un modulo y lo devuelve con su id."""
        marca = ahora_iso() if completado else None
        cursor = self._cx.execute(
            """
            INSERT INTO modulo (materia_id, nombre, orden, completado, completado_en)
            VALUES (?, ?, ?, ?, ?)
            """,
            (materia_id, nombre, orden, int(completado), marca),
        )
        return Modulo(
            id=int(cursor.lastrowid or 0),
            materia_id=materia_id,
            nombre=nombre,
            orden=orden,
            completado=completado,
        )

    def marcar(self, modulo_id: int, completado: bool) -> None:
        """Marca o desmarca un modulo, actualizando la fecha de finalizacion."""
        self._cx.execute(
            "UPDATE modulo SET completado = ?, completado_en = ? WHERE id = ?",
            (int(completado), ahora_iso() if completado else None, modulo_id),
        )

    def marcar_materia(self, materia_id: int, completado: bool) -> int:
        """Marca o desmarca todos los modulos de una materia. Devuelve cuantos cambio.

        El `AND completado <> ?` no es una optimizacion: sin el, volver a marcar
        una materia reescribiria `completado_en` de los modulos que ya estaban
        hechos, y las sugerencias de repaso de `ServicioPlan` —que miran esa
        fecha para proponer lo completado hace mas de tres semanas— se
        reiniciarian en silencio.
        """
        cursor = self._cx.execute(
            """
            UPDATE modulo SET completado = ?, completado_en = ?
             WHERE materia_id = ? AND completado <> ?
            """,
            (
                int(completado),
                ahora_iso() if completado else None,
                materia_id,
                int(completado),
            ),
        )
        return cursor.rowcount

    def renombrar(self, modulo_id: int, nombre: str) -> None:
        """Cambia el nombre de un modulo, conservando su estado y su orden.

        El curriculo del CFA se renumera cada ano y algun modulo cambia de
        nombre o se parte en varios. Renombrar en vez de borrar y recrear
        conserva el «completado» y la fecha en que se logro.
        """
        self._cx.execute("UPDATE modulo SET nombre = ? WHERE id = ?", (nombre, modulo_id))

    def fijar_horas(self, modulo_id: int, horas: float | None) -> None:
        """Estimacion de horas de un modulo. ``None`` la borra.

        Un valor negativo se guarda como ``None``: cero es una estimacion
        legitima, negativo solo puede ser un error al teclear.
        """
        self._cx.execute(
            "UPDATE modulo SET horas_estimadas = ? WHERE id = ?",
            (float(horas) if horas is not None and horas >= 0 else None, modulo_id),
        )

    def horas_por_materia(self, proyecto_id: int) -> dict[int, tuple[float, float]]:
        """Horas estimadas de cada materia segun sus modulos: ``(total, pendientes)``.

        Solo suma los modulos que tienen estimacion; los demas aportan cero. Las
        pendientes son las de los modulos sin completar, que es lo que el
        planificador necesita saber.

        Una materia sin ningun modulo estimado no aparece en el diccionario, de
        modo que el servicio puede distinguir «suma cero horas» de «no hay
        desglose, usa la estimacion de la materia».
        """
        filas = self._cx.execute(
            """
            SELECT mo.materia_id AS materia_id,
                   SUM(mo.horas_estimadas) AS total,
                   SUM(CASE WHEN mo.completado = 0 THEN mo.horas_estimadas ELSE 0 END)
                       AS pendientes
              FROM modulo mo
              JOIN materia m ON m.id = mo.materia_id
             WHERE m.proyecto_id = ? AND mo.horas_estimadas IS NOT NULL
             GROUP BY mo.materia_id
            """,
            (proyecto_id,),
        ).fetchall()
        return {
            int(f["materia_id"]): (float(f["total"]), float(f["pendientes"]))
            for f in filas
        }

    def eliminar(self, modulo_id: int) -> None:
        """Borra un modulo."""
        self._cx.execute("DELETE FROM modulo WHERE id = ?", (modulo_id,))

    def mover_a_materia(self, modulo_id: int, materia_id: int) -> bool:
        """Traslada un modulo a otra materia conservando su estado.

        Es lo que hace falta cuando el curriculo reubica un tema: hasta ahora el
        unico camino era borrar y recrear, que pierde `completado` y
        `completado_en` —justo lo que `renombrar` se preocupa de conservar—.

        Devuelve ``False``, sin tocar nada, si el modulo no existe, si ya esta en
        esa materia o si la materia destino tiene ya uno con ese nombre. Lo
        ultimo lo impide el `UNIQUE (materia_id, nombre)` del esquema, y se
        comprueba antes a proposito: reventar con `IntegrityError` obligaria a la
        interfaz a entender de SQLite, y renombrar por su cuenta seria peor.
        """
        actual = self.obtener(modulo_id)
        if actual is None or actual.materia_id == materia_id:
            return False
        if self._existe_nombre(materia_id, actual.nombre):
            return False

        with transaccion(self._cx):
            self._cx.execute(
                "UPDATE modulo SET materia_id = ?, orden = ? WHERE id = ?",
                (materia_id, len(self.listar(materia_id)), modulo_id),
            )
            # Compacta el destino: sus modulos pueden venir del Excel con el
            # orden empatado a cero, y entonces el recien llegado no quedaria al
            # final sino donde lo pusiera el desempate por nombre.
            self.reordenar(materia_id, [m.id for m in self.listar(materia_id)])
        return True

    def _existe_nombre(self, materia_id: int, nombre: str) -> bool:
        """Si esa materia ya tiene un modulo asi llamado."""
        fila = self._cx.execute(
            "SELECT 1 FROM modulo WHERE materia_id = ? AND nombre = ?",
            (materia_id, nombre),
        ).fetchone()
        return fila is not None

    # -- Orden -------------------------------------------------------------

    def reordenar(self, materia_id: int, ids: Sequence[int]) -> None:
        """Fija el orden de los modulos de una materia segun la lista de ids.

        Los ids que no se mencionen conservan su posicion relativa detras, y uno
        que no pertenezca a la materia se ignora: el `WHERE materia_id` evita que
        una lista equivocada reordene modulos de otro tema.
        """
        for posicion, modulo_id in enumerate(ids):
            self._cx.execute(
                "UPDATE modulo SET orden = ? WHERE id = ? AND materia_id = ?",
                (posicion, modulo_id, materia_id),
            )

    def mover(self, modulo_id: int, desplazamiento: int) -> bool:
        """Sube o baja un modulo dentro de su materia. Devuelve si se movio.

        Se reescribe el orden de toda la materia y no solo el del par que se
        intercambia: los modulos importados del Excel pueden compartir `orden`
        (todos a 0), y ahi un intercambio de dos valores no cambiaria nada.
        """
        actual = self.obtener(modulo_id)
        if actual is None:
            return False

        modulos = self.listar(actual.materia_id)
        posiciones = [m.id for m in modulos]
        origen = posiciones.index(modulo_id)
        destino = origen + desplazamiento
        if not 0 <= destino < len(posiciones):
            return False

        posiciones[origen], posiciones[destino] = posiciones[destino], posiciones[origen]
        self.reordenar(actual.materia_id, posiciones)
        return True

    def insertar_tras(
        self, modulo_id: int, nombre: str, *, completado: bool = False
    ) -> Modulo | None:
        """Crea un modulo justo detras de otro, corriendo los siguientes.

        Es lo que hace falta cuando un modulo del curriculo se parte en varios:
        los nuevos tienen que quedar en su sitio, no al final de la lista.
        """
        referencia = self.obtener(modulo_id)
        if referencia is None:
            return None

        modulos = self.listar(referencia.materia_id)
        nuevo = self.crear(
            referencia.materia_id, nombre, orden=referencia.orden, completado=completado
        )
        posiciones = [m.id for m in modulos]
        posiciones.insert(posiciones.index(modulo_id) + 1, nuevo.id)
        self.reordenar(referencia.materia_id, posiciones)
        nuevo.orden = posiciones.index(nuevo.id)
        return nuevo

    def completados_hasta(
        self, proyecto_id: int, fecha: str, limite: int
    ) -> list[tuple[Modulo, str]]:
        """Modulos completados en ``fecha`` (ISO) o antes, con el nombre de su materia.

        Del mas antiguo al mas reciente y, dentro del mismo dia, por nombre. Es
        la consulta del repaso activo: una sola, en lugar de listar los modulos
        materia por materia y filtrar en Python.
        """
        filas = self._cx.execute(
            f"""
            SELECT {", ".join("mo." + c.strip() for c in _CAMPOS.split(","))},
                   m.nombre AS materia
              FROM modulo mo
              JOIN materia m ON m.id = mo.materia_id
             WHERE m.proyecto_id = ? AND mo.completado = 1
               AND mo.completado_en IS NOT NULL
               AND substr(mo.completado_en, 1, 10) <= ?
             ORDER BY substr(mo.completado_en, 1, 10), mo.nombre
             LIMIT ?
            """,
            (proyecto_id, fecha, limite),
        ).fetchall()
        return [(_a_modulo(f), f["materia"]) for f in filas]

    def listar_del_proyecto(self, proyecto_id: int) -> dict[int, list[Modulo]]:
        """Todos los modulos del proyecto agrupados por materia, en una consulta.

        Las materias sin modulos no aparecen; quien recorra las materias debe
        usar ``.get(materia.id, [])``.
        """
        filas = self._cx.execute(
            f"""
            SELECT {", ".join("mo." + c.strip() for c in _CAMPOS.split(","))}
              FROM modulo mo
              JOIN materia m ON m.id = mo.materia_id
             WHERE m.proyecto_id = ?
             ORDER BY mo.materia_id, mo.orden, mo.nombre
            """,
            (proyecto_id,),
        ).fetchall()
        agrupados: dict[int, list[Modulo]] = {}
        for fila in filas:
            agrupados.setdefault(int(fila["materia_id"]), []).append(_a_modulo(fila))
        return agrupados

    # -- Recuentos ---------------------------------------------------------

    def conteo_por_materia(self, proyecto_id: int) -> list[ConteoMateria]:
        """Total y completados de cada materia del proyecto.

        Usa LEFT JOIN para que una materia sin modulos aparezca con total 0 en
        vez de desaparecer del progreso.

        **Invariante:** ordena por `orden, nombre`, igual que
        `RepositorioMaterias.listar`. El Panel recorre esto y la vista Progreso
        recorre aquello; cuando una materia no tiene color propio, ambas caen al
        color de la serie **por posicion**, asi que si los dos ordenes divergen
        la misma materia se pinta de dos colores distintos segun la pantalla.
        """
        filas = self._cx.execute(
            """
            SELECT m.id            AS materia_id,
                   m.nombre        AS nombre,
                   m.peso          AS peso,
                   m.color         AS color,
                   COUNT(mo.id)    AS total,
                   COALESCE(SUM(mo.completado), 0) AS completados
              FROM materia m
              LEFT JOIN modulo mo ON mo.materia_id = m.id
             WHERE m.proyecto_id = ?
             GROUP BY m.id
             ORDER BY m.orden, m.nombre
            """,
            (proyecto_id,),
        ).fetchall()
        return [
            ConteoMateria(
                materia_id=f["materia_id"],
                nombre=f["nombre"],
                total=f["total"],
                completados=f["completados"],
                peso=float(f["peso"]),
                color=f["color"],
            )
            for f in filas
        ]

    def conteo_total(self, proyecto_id: int) -> tuple[int, int]:
        """Devuelve ``(total, completados)`` de todo el proyecto."""
        fila = self._cx.execute(
            """
            SELECT COUNT(mo.id) AS total,
                   COALESCE(SUM(mo.completado), 0) AS completados
              FROM modulo mo
              JOIN materia m ON m.id = mo.materia_id
             WHERE m.proyecto_id = ?
            """,
            (proyecto_id,),
        ).fetchone()
        return int(fila["total"]), int(fila["completados"])


def _a_modulo(fila: sqlite3.Row) -> Modulo:
    horas = fila["horas_estimadas"]
    return Modulo(
        id=fila["id"],
        materia_id=fila["materia_id"],
        nombre=fila["nombre"],
        orden=fila["orden"],
        completado=bool(fila["completado"]),
        completado_en=a_fecha_hora(fila["completado_en"]),
        horas_estimadas=float(horas) if horas is not None else None,
    )
