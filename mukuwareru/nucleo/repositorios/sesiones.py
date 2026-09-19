"""Acceso a la tabla ``sesion``.

Aqui viven tambien las agregaciones de tiempo. El servicio de estadisticas
compone estos resultados, pero el SQL no sale de este archivo.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from mukuwareru.nucleo.modelos.entidades import OrigenSesion, Sesion, TipoSesion
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha_hora

_CAMPOS = """
    id, proyecto_id, tipo, origen, inicio, fin,
    duracion_seg, fecha_local, completada
"""

# La misma lista cualificada, para las consultas que hacen JOIN.
_CAMPOS_S = """
    s.id, s.proyecto_id, s.tipo, s.origen, s.inicio, s.fin,
    s.duracion_seg, s.fecha_local, s.completada
"""


class RepositorioSesiones(Repositorio):
    """Consultas y escrituras sobre sesiones de estudio."""

    # -- Escritura ---------------------------------------------------------

    def crear(
        self,
        proyecto_id: int,
        *,
        tipo: TipoSesion,
        origen: OrigenSesion,
        inicio: datetime,
        duracion_seg: int,
        fin: datetime | None = None,
        completada: bool = True,
        materias: list[int] | None = None,
    ) -> Sesion:
        """Registra una sesion y la asocia opcionalmente a varias materias."""
        cursor = self._cx.execute(
            """
            INSERT INTO sesion
                (proyecto_id, tipo, origen, inicio, fin, duracion_seg, fecha_local, completada)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proyecto_id,
                str(tipo),
                str(origen),
                inicio.isoformat(timespec="seconds"),
                fin.isoformat(timespec="seconds") if fin else None,
                duracion_seg,
                inicio.date().isoformat(),
                int(completada),
            ),
        )
        sesion_id = int(cursor.lastrowid or 0)
        etiquetas = materias or []
        if etiquetas:
            self.etiquetar(sesion_id, etiquetas)

        return Sesion(
            id=sesion_id,
            proyecto_id=proyecto_id,
            tipo=tipo,
            origen=origen,
            inicio=inicio,
            fin=fin,
            duracion_seg=duracion_seg,
            fecha_local=inicio.date().isoformat(),
            completada=completada,
            materias=list(etiquetas),
        )

    def etiquetar(self, sesion_id: int, materias: list[int]) -> None:
        """Reemplaza las materias asociadas a una sesion."""
        self._cx.execute("DELETE FROM sesion_materia WHERE sesion_id = ?", (sesion_id,))
        self._cx.executemany(
            "INSERT INTO sesion_materia (sesion_id, materia_id) VALUES (?, ?)",
            [(sesion_id, m) for m in materias],
        )

    def eliminar(self, sesion_id: int) -> None:
        """Borra una sesion."""
        self._cx.execute("DELETE FROM sesion WHERE id = ?", (sesion_id,))

    # -- Lectura -----------------------------------------------------------

    def recientes(self, proyecto_id: int, limite: int = 5) -> list[Sesion]:
        """Ultimas sesiones de trabajo, de la mas reciente a la mas antigua.

        Se desempata por ``id`` porque ``inicio`` tiene resolucion de segundo:
        dos sesiones del mismo segundo salian en orden arbitrario.
        """
        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS} FROM sesion
             WHERE proyecto_id = ? AND tipo = 'trabajo'
             ORDER BY inicio DESC, id DESC
             LIMIT ?
            """,
            (proyecto_id, limite),
        ).fetchall()
        return [_a_sesion(f) for f in filas]

    def listar_rango(
        self, proyecto_id: int, desde: str, hasta: str, *, solo_trabajo: bool = True
    ) -> list[Sesion]:
        """Sesiones del rango de fechas locales, en orden cronologico.

        ``segundos_por_dia`` basta para los graficos, pero el cumplimiento de un
        bloque planeado necesita el solape de horas, y para eso hacen falta las
        filas y sus materias, no la suma.
        """
        condiciones = ["s.proyecto_id = ?", "s.fecha_local BETWEEN ? AND ?"]
        parametros: list[object] = [proyecto_id, desde, hasta]
        if solo_trabajo:
            condiciones.append("s.tipo = 'trabajo'")

        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS_S} FROM sesion s
             WHERE {' AND '.join(condiciones)}
             ORDER BY s.inicio, s.id
            """,
            parametros,
        ).fetchall()
        sesiones = [_a_sesion(f) for f in filas]
        if not sesiones:
            return []

        marcadores = ",".join("?" * len(sesiones))
        vinculos = self._cx.execute(
            f"SELECT sesion_id, materia_id FROM sesion_materia "
            f"WHERE sesion_id IN ({marcadores})",
            [s.id for s in sesiones],
        ).fetchall()
        por_sesion: dict[int, list[int]] = {}
        for fila in vinculos:
            por_sesion.setdefault(int(fila["sesion_id"]), []).append(
                int(fila["materia_id"])
            )
        for sesion in sesiones:
            sesion.materias = por_sesion.get(sesion.id, [])
        return sesiones

    def segundos_trabajo(
        self, proyecto_id: int, *, desde: str | None = None, hasta: str | None = None
    ) -> int:
        """Segundos de trabajo acumulados en el rango de fechas locales dado.

        Ambos extremos son inclusivos; ``None`` significa sin limite.
        """
        condiciones = ["proyecto_id = ?", "tipo = 'trabajo'"]
        parametros: list[object] = [proyecto_id]
        if desde is not None:
            condiciones.append("fecha_local >= ?")
            parametros.append(desde)
        if hasta is not None:
            condiciones.append("fecha_local <= ?")
            parametros.append(hasta)

        fila = self._cx.execute(
            f"SELECT COALESCE(SUM(duracion_seg), 0) FROM sesion WHERE {' AND '.join(condiciones)}",
            parametros,
        ).fetchone()
        return int(fila[0])

    def contar_pomodoros(self, proyecto_id: int, *, fecha: str | None = None) -> int:
        """Sesiones de trabajo completadas, opcionalmente de un solo dia."""
        condiciones = ["proyecto_id = ?", "tipo = 'trabajo'", "completada = 1"]
        parametros: list[object] = [proyecto_id]
        if fecha is not None:
            condiciones.append("fecha_local = ?")
            parametros.append(fecha)

        fila = self._cx.execute(
            f"SELECT COUNT(*) FROM sesion WHERE {' AND '.join(condiciones)}", parametros
        ).fetchone()
        return int(fila[0])

    def dias_con_trabajo(self, proyecto_id: int) -> list[str]:
        """Fechas locales con trabajo registrado, de la mas reciente hacia atras."""
        filas = self._cx.execute(
            """
            SELECT DISTINCT fecha_local FROM sesion
             WHERE proyecto_id = ? AND tipo = 'trabajo' AND duracion_seg > 0
             ORDER BY fecha_local DESC
            """,
            (proyecto_id,),
        ).fetchall()
        return [f["fecha_local"] for f in filas]

    def fechas_importadas(self, proyecto_id: int) -> set[str]:
        """Fechas locales que ya tienen una sesion procedente de una importacion.

        Es la clave que hace idempotente la importacion del Excel: el registro
        diario trae una fila por dia, asi que la fecha identifica la sesion.
        """
        filas = self._cx.execute(
            """
            SELECT DISTINCT fecha_local FROM sesion
             WHERE proyecto_id = ? AND origen = 'importada'
            """,
            (proyecto_id,),
        ).fetchall()
        return {f["fecha_local"] for f in filas}

    def segundos_por_dia(self, proyecto_id: int, desde: str, hasta: str) -> dict[str, int]:
        """Segundos de trabajo por fecha local dentro del rango, ambos inclusive."""
        filas = self._cx.execute(
            """
            SELECT fecha_local, SUM(duracion_seg) AS total FROM sesion
             WHERE proyecto_id = ? AND tipo = 'trabajo'
               AND fecha_local BETWEEN ? AND ?
             GROUP BY fecha_local
            """,
            (proyecto_id, desde, hasta),
        ).fetchall()
        return {f["fecha_local"]: int(f["total"]) for f in filas}

    def segundos_por_materia(self, proyecto_id: int) -> dict[int, int]:
        """Segundos de trabajo atribuidos a cada materia etiquetada.

        Una sesion etiquetada con varias materias **reparte** su duracion a
        partes iguales entre ellas. No se sabe cuanto tiempo fue a cada tema,
        pero repartir es la unica opcion que conserva el total: sumar la sesion
        completa a cada etiqueta hacia que las partes sumaran mas que el todo e
        inflaba justo las materias que solo aparecian de refilon.
        """
        filas = self._cx.execute(
            """
            SELECT sm.materia_id AS materia_id,
                   SUM(s.duracion_seg * 1.0 / etiquetas.cuantas) AS total
              FROM sesion s
              JOIN sesion_materia sm ON sm.sesion_id = s.id
              JOIN (
                    SELECT sesion_id, COUNT(*) AS cuantas
                      FROM sesion_materia GROUP BY sesion_id
                   ) etiquetas ON etiquetas.sesion_id = s.id
             WHERE s.proyecto_id = ? AND s.tipo = 'trabajo'
             GROUP BY sm.materia_id
            """,
            (proyecto_id,),
        ).fetchall()
        return {f["materia_id"]: round(f["total"]) for f in filas}

    def segundos_sin_clasificar(self, proyecto_id: int) -> int:
        """Segundos de trabajo que no tienen ninguna materia asociada."""
        fila = self._cx.execute(
            """
            SELECT COALESCE(SUM(s.duracion_seg), 0) FROM sesion s
             WHERE s.proyecto_id = ? AND s.tipo = 'trabajo'
               AND NOT EXISTS (SELECT 1 FROM sesion_materia sm WHERE sm.sesion_id = s.id)
            """,
            (proyecto_id,),
        ).fetchone()
        return int(fila[0])


def _a_sesion(fila: sqlite3.Row) -> Sesion:
    inicio = a_fecha_hora(fila["inicio"])
    assert inicio is not None
    return Sesion(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        tipo=TipoSesion(fila["tipo"]),
        origen=OrigenSesion(fila["origen"]),
        inicio=inicio,
        fin=a_fecha_hora(fila["fin"]),
        duracion_seg=fila["duracion_seg"],
        fecha_local=fila["fecha_local"],
        completada=bool(fila["completada"]),
    )
