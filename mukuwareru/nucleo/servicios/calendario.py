"""Calendario: lo estudiado, lo planeado y la distancia entre las dos cosas.

Las sesiones son una **proyeccion de solo lectura** de la tabla ``sesion``: el
calendario no guarda nada de lo ya estudiado y por eso no puede desincronizarse.
Lo unico que se guarda es lo que aun no ha pasado —hitos y bloques planeados—.

``repartir_cumplimiento`` es una funcion pura, sin conexion ni Qt, igual que
``calcular_racha`` y ``RelojPomodoro``: la regla de «¿estudie lo que dije?» es lo
bastante delicada como para probarse entera en microsegundos.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from mukuwareru.nucleo.modelos.entidades import BloquePlan, Hito, Sesion
from mukuwareru.nucleo.repositorios import (
    RepositorioBloques,
    RepositorioHitos,
    RepositorioSesiones,
)

# A partir de que porcentaje del bloque se considera hecho. Exigir el 100 % de
# un bloque de 90 minutos castigaria por levantarse cinco minutos antes.
UMBRAL_CUMPLIDO = 0.8


@dataclass(frozen=True, slots=True)
class Cumplimiento:
    """Lo planeado frente a lo realmente estudiado en un bloque."""

    bloque_id: int
    planeado_seg: int
    real_seg: int

    @property
    def ratio(self) -> float:
        """Fraccion del bloque cubierta, recortada a 1.0."""
        if self.planeado_seg <= 0:
            return 0.0
        return min(1.0, self.real_seg / self.planeado_seg)

    @property
    def porcentaje(self) -> int:
        """El ratio en enteros, que es como se ensena."""
        return round(self.ratio * 100)

    @property
    def cumplido(self) -> bool:
        """Si cuenta como hecho."""
        return self.ratio >= UMBRAL_CUMPLIDO


@dataclass(frozen=True, slots=True)
class DiaCalendario:
    """Todo lo que la celda de un dia necesita para pintarse."""

    fecha: date
    segundos_estudiados: int = 0
    pomodoros: int = 0
    hitos: list[Hito] = field(default_factory=list)
    bloques: list[BloquePlan] = field(default_factory=list)
    cumplimientos: dict[int, Cumplimiento] = field(default_factory=dict)
    sesiones: list[Sesion] = field(default_factory=list)

    @property
    def minutos_planeados(self) -> int:
        """Minutos que se habian previsto para este dia."""
        return sum(bloque.duracion_min for bloque in self.bloques)

    @property
    def bloques_cumplidos(self) -> int:
        """Cuantos de los bloques previstos se dieron por hechos."""
        return sum(1 for c in self.cumplimientos.values() if c.cumplido)

    @property
    def vacio(self) -> bool:
        """Si no hay nada que pintar en este dia."""
        return not (
            self.segundos_estudiados or self.hitos or self.bloques
        )

    @property
    def incumplido(self) -> bool:
        """Si tenia algo planeado y no se cumplio del todo."""
        return bool(self.bloques) and self.bloques_cumplidos < len(self.bloques)


@dataclass(frozen=True, slots=True)
class ResumenCumplimiento:
    """Cuanto se ha cumplido lo planeado en un rango de dias.

    Es la cifra que responde «¿cuantos dias, y cuantas horas, me he quedado
    corto?». Se calcula sobre ``rango()``, nunca se guarda.
    """

    dias_con_plan: int
    dias_cumplidos: int
    segundos_planeados: int
    segundos_reales: int

    @property
    def dias_incumplidos(self) -> int:
        return self.dias_con_plan - self.dias_cumplidos

    @property
    def pct_dias_incumplidos(self) -> float:
        if not self.dias_con_plan:
            return 0.0
        return 100 * self.dias_incumplidos / self.dias_con_plan

    @property
    def segundos_faltantes(self) -> int:
        return max(0, self.segundos_planeados - self.segundos_reales)

    @property
    def pct_horas_incumplidas(self) -> float:
        if not self.segundos_planeados:
            return 0.0
        return 100 * self.segundos_faltantes / self.segundos_planeados


def _fin_de(sesion: Sesion) -> datetime:
    """Momento en que acabo la sesion.

    ``fin`` puede ser NULL cuando la aplicacion se cerro a media fase, asi que se
    deduce de ``inicio + duracion``.
    """
    if sesion.fin is not None:
        return sesion.fin
    return sesion.inicio + timedelta(seconds=sesion.duracion_seg)


def _ventana(bloque: BloquePlan) -> tuple[time, time] | None:
    """Franja ``[inicio, fin)`` del bloque, o ``None`` si no tiene hora."""
    if bloque.hora_inicio is None:
        return None
    try:
        horas, minutos = (int(parte) for parte in bloque.hora_inicio.split(":"))
    except ValueError:
        return None
    inicio = time(hour=horas % 24, minute=minutos % 60)
    total = horas * 60 + minutos + bloque.duracion_min
    # Un bloque que se pasa de medianoche se recorta al final del dia: partirlo
    # en dos dias complicaria el reparto para un caso que casi no ocurre.
    total = min(total, 24 * 60 - 1)
    return inicio, time(hour=total // 60, minute=total % 60)


def _solape_seg(sesion: Sesion, desde: time, hasta: time) -> int:
    """Segundos de la sesion que caen dentro de la franja, el mismo dia."""
    dia = sesion.inicio.date()
    ventana_inicio = datetime.combine(dia, desde, tzinfo=sesion.inicio.tzinfo)
    ventana_fin = datetime.combine(dia, hasta, tzinfo=sesion.inicio.tzinfo)
    inicio = max(sesion.inicio, ventana_inicio)
    fin = min(_fin_de(sesion), ventana_fin)
    return max(0, int((fin - inicio).total_seconds()))


def _cuenta_para(bloque: BloquePlan, sesion: Sesion) -> bool:
    """Si el tiempo de esta sesion puede atribuirse a este bloque.

    Un bloque que prevé materias solo acepta sesiones etiquetadas con alguna de
    ellas **o sin etiquetar**: etiquetar es opcional en toda la aplicacion, y
    castigar a quien omitio el dialogo seria injusto.
    """
    if not bloque.materias:
        return True
    if not sesion.materias:
        return True
    return bool(set(bloque.materias) & set(sesion.materias))


def repartir_cumplimiento(
    bloques: list[BloquePlan], sesiones: list[Sesion]
) -> dict[int, Cumplimiento]:
    """Atribuye a cada bloque planeado el tiempo que de verdad se estudio.

    Reglas, en este orden:

    1. Un bloque **con hora** reclama los segundos de las sesiones que solapan
       su franja ``[inicio, inicio + duracion)``.
    2. Si el bloque prevé materias, solo cuentan las sesiones compatibles (ver
       ``_cuenta_para``).
    3. **Cada segundo se atribuye una sola vez.** Los bloques se procesan por
       ``(hora_inicio, id)``, asi que dos bloques solapados no pueden sumar el
       doble del tiempo realmente estudiado.
    4. Los bloques **sin hora** se reparten lo que quede del dia, por ``id``.

    Es una funcion pura: mismos datos, mismo resultado, sin tocar la base.
    """
    restante = {sesion.id: sesion.duracion_seg for sesion in sesiones}
    resultado: dict[int, Cumplimiento] = {}

    con_hora = sorted(
        (b for b in bloques if _ventana(b) is not None),
        key=lambda b: (b.hora_inicio or "", b.id),
    )
    sin_hora = sorted(
        (b for b in bloques if _ventana(b) is None), key=lambda b: b.id
    )

    for bloque in con_hora:
        ventana = _ventana(bloque)
        assert ventana is not None
        desde, hasta = ventana
        real = 0
        for sesion in sesiones:
            if restante[sesion.id] <= 0 or not _cuenta_para(bloque, sesion):
                continue
            disponible = min(restante[sesion.id], _solape_seg(sesion, desde, hasta))
            tomado = min(disponible, bloque.duracion_seg - real)
            if tomado <= 0:
                continue
            real += tomado
            restante[sesion.id] -= tomado
        resultado[bloque.id] = Cumplimiento(bloque.id, bloque.duracion_seg, real)

    for bloque in sin_hora:
        real = 0
        for sesion in sesiones:
            if restante[sesion.id] <= 0 or not _cuenta_para(bloque, sesion):
                continue
            tomado = min(restante[sesion.id], bloque.duracion_seg - real)
            if tomado <= 0:
                continue
            real += tomado
            restante[sesion.id] -= tomado
        resultado[bloque.id] = Cumplimiento(bloque.id, bloque.duracion_seg, real)

    return resultado


class ServicioCalendario:
    """Compone sesiones reales, hitos y bloques planeados en un calendario."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._sesiones = RepositorioSesiones(conexion)
        self._hitos = RepositorioHitos(conexion)
        self._bloques = RepositorioBloques(conexion)

    # -- Composicion --------------------------------------------------------

    def rango(self, proyecto_id: int, desde: date, hasta: date) -> list[DiaCalendario]:
        """Un ``DiaCalendario`` por cada dia del rango, ambos inclusive.

        Tres consultas y el reparto en memoria. **Nunca una consulta por dia**:
        pintar un mes son 31 celdas y eso serian 93 viajes a la base.
        """
        clave_desde, clave_hasta = desde.isoformat(), hasta.isoformat()
        sesiones = self._sesiones.listar_rango(proyecto_id, clave_desde, clave_hasta)
        hitos = self._hitos.listar(proyecto_id, desde=clave_desde, hasta=clave_hasta)
        bloques = self._bloques.listar(proyecto_id, clave_desde, clave_hasta)

        sesiones_por_dia: dict[str, list[Sesion]] = {}
        for sesion in sesiones:
            sesiones_por_dia.setdefault(sesion.fecha_local, []).append(sesion)
        hitos_por_dia: dict[str, list[Hito]] = {}
        for hito in hitos:
            hitos_por_dia.setdefault(hito.fecha.isoformat(), []).append(hito)
        bloques_por_dia: dict[str, list[BloquePlan]] = {}
        for bloque in bloques:
            bloques_por_dia.setdefault(bloque.fecha.isoformat(), []).append(bloque)

        dias: list[DiaCalendario] = []
        actual = desde
        while actual <= hasta:
            clave = actual.isoformat()
            del_dia = sesiones_por_dia.get(clave, [])
            planeados = bloques_por_dia.get(clave, [])
            dias.append(
                DiaCalendario(
                    fecha=actual,
                    segundos_estudiados=sum(s.duracion_seg for s in del_dia),
                    pomodoros=sum(1 for s in del_dia if s.completada),
                    hitos=hitos_por_dia.get(clave, []),
                    bloques=planeados,
                    cumplimientos=repartir_cumplimiento(planeados, del_dia),
                    sesiones=del_dia,
                )
            )
            actual += timedelta(days=1)
        return dias

    def mes(self, proyecto_id: int, ano: int, mes: int) -> list[DiaCalendario]:
        """Los dias del mes indicado."""
        primero = date(ano, mes, 1)
        siguiente = date(ano + (mes == 12), (mes % 12) + 1, 1)
        return self.rango(proyecto_id, primero, siguiente - timedelta(days=1))

    def semana(self, proyecto_id: int, lunes: date) -> list[DiaCalendario]:
        """Los siete dias que empiezan en la fecha dada."""
        return self.rango(proyecto_id, lunes, lunes + timedelta(days=6))

    def dia(self, proyecto_id: int, fecha: date) -> DiaCalendario:
        """Un unico dia, con todo su detalle."""
        return self.rango(proyecto_id, fecha, fecha)[0]

    # -- Cifras -------------------------------------------------------------

    def resumen_adherencia(
        self, proyecto_id: int, desde: date, hasta: date
    ) -> tuple[int, int]:
        """``(bloques cumplidos, bloques planeados)`` del rango.

        Es la cifra que contesta «¿estudie lo que dije que iba a estudiar?».
        """
        dias = self.rango(proyecto_id, desde, hasta)
        cumplidos = sum(dia.bloques_cumplidos for dia in dias)
        planeados = sum(len(dia.bloques) for dia in dias)
        return cumplidos, planeados

    def resumen_cumplimiento(
        self, proyecto_id: int, desde: date, hasta: date
    ) -> ResumenCumplimiento:
        """El porcentaje de dias y de horas en que no se cumplio lo planeado."""
        dias = self.rango(proyecto_id, desde, hasta)
        con_plan = [dia for dia in dias if dia.bloques]
        cumplidos = sum(
            1 for dia in con_plan if dia.bloques_cumplidos == len(dia.bloques)
        )
        planeados_seg = sum(
            c.planeado_seg for dia in dias for c in dia.cumplimientos.values()
        )
        reales_seg = sum(
            c.real_seg for dia in dias for c in dia.cumplimientos.values()
        )
        return ResumenCumplimiento(len(con_plan), cumplidos, planeados_seg, reales_seg)

    def ultimo_incumplimiento(
        self, proyecto_id: int, hoy: date | None = None
    ) -> tuple[date, BloquePlan, Cumplimiento] | None:
        """El bloque planeado mas reciente, ya pasado, que no se cumplio.

        Solo mira el pasado —un bloque de hoy o de manana no es un
        incumplimiento todavia—, y solo la ultima semana: recordar algo de
        hace un mes no ayuda a nadie.
        """
        hoy = hoy or date.today()
        ayer = hoy - timedelta(days=1)
        desde = hoy - timedelta(days=7)
        if ayer < desde:
            return None
        for dia in reversed(self.rango(proyecto_id, desde, ayer)):
            for bloque in dia.bloques:
                cumplimiento = dia.cumplimientos.get(bloque.id)
                if cumplimiento is not None and not cumplimiento.cumplido:
                    return dia.fecha, bloque, cumplimiento
        return None

    def proxima_fecha_clave(
        self, proyecto_id: int, hoy: date | None = None
    ) -> Hito | None:
        """El hito sin completar mas cercano.

        Es la unica regla de cuenta atras de la aplicacion: la barra lateral pasa
        por aqui en lugar de leer ``proyecto.fecha_objetivo``, de modo que anadir
        un mock dentro de dos semanas cambia el contador.
        """
        proximos = self._hitos.proximos(
            proyecto_id, (hoy or date.today()).isoformat(), limite=1
        )
        return proximos[0] if proximos else None
