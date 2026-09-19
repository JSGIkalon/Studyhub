"""Preferencias de la aplicacion.

Envuelve el almacen clave/valor con tipos y valores por defecto, para que
ninguna parte de la interfaz tenga que convertir cadenas ni recordar claves.

Las duraciones del Pomodoro son globales: se estudia igual sea cual sea el
proyecto. Lo que si es por proyecto (fecha objetivo, ruta de biblioteca) vive en
columnas de ``proyecto``, no aqui.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from mukuwareru.nucleo.repositorios.ajustes import RepositorioAjustes
from mukuwareru.nucleo.servicios.pomodoro import Configuracion

_TRABAJO = "pomodoro.trabajo_min"
_CORTO = "pomodoro.descanso_corto_min"
_LARGO = "pomodoro.descanso_largo_min"
_CICLO = "pomodoro.sesiones_por_ciclo"
_PREGUNTAR = "pomodoro.preguntar_materia"
_ORDEN_SECCIONES = "interfaz.orden_secciones"
_SECCIONES_OCULTAS = "interfaz.secciones_ocultas"
_BARRA_LATERAL = "interfaz.barra_lateral"

# Ocultar Ajustes dejaria la aplicacion sin ningun camino de vuelta para volver
# a mostrar lo oculto. Es el unico invariante de la disposicion, y vive aqui y
# no en la interfaz para que ninguna vista futura pueda saltarselo.
_SECCION_IRRENUNCIABLE = "ajustes"

# Limites de cordura: un pomodoro de 0 o de 12 horas no es un pomodoro.
_RANGOS = {
    _TRABAJO: (1, 180),
    _CORTO: (1, 60),
    _LARGO: (1, 120),
    _CICLO: (1, 12),
}


@dataclass(frozen=True, slots=True)
class Preferencias:
    """Ajustes globales editables desde la vista Ajustes."""

    pomodoro: Configuracion
    preguntar_materia: bool


class EstadoBarra(StrEnum):
    """Como se muestra la barra lateral.

    ``OCULTA`` no es lo mismo que ``COLAPSADA``: colapsada deja los iconos, que
    siguen ocupando 56 px. Estudiando un PDF a doble pagina esos 56 px importan.
    """

    COMPLETA = "completa"
    COLAPSADA = "colapsada"
    OCULTA = "oculta"


@dataclass(frozen=True, slots=True)
class DisposicionSecciones:
    """Orden y visibilidad de las secciones de la barra lateral.

    Deliberadamente **no** forma parte de ``Preferencias``: esa dataclass se
    guarda entera desde la vista Pomodoro y desde el dialogo de etiquetado, y
    arrastrar la disposicion por ahi haria que un olvido la borrase.
    """

    orden: tuple[str, ...]
    ocultas: frozenset[str] = frozenset()

    @property
    def visibles(self) -> tuple[str, ...]:
        """Secciones que la barra lateral debe pintar, ya en su orden."""
        return tuple(clave for clave in self.orden if clave not in self.ocultas)


def reconciliar_orden(
    guardado: Sequence[str], disponibles: Sequence[str]
) -> tuple[str, ...]:
    """Cruza el orden guardado con las secciones que existen en esta version.

    Primero lo guardado que sigue existiendo, sin repetir; despues lo que la
    version trae de nuevo, al final y en el orden del catalogo. Asi una seccion
    retirada se ignora y una nueva aparece sola, sin migracion ni numero de
    version que mantener.
    """
    conocidas = set(disponibles)
    vistas: set[str] = set()
    orden: list[str] = []
    for clave in guardado:
        if clave in conocidas and clave not in vistas:
            vistas.add(clave)
            orden.append(clave)
    orden.extend(clave for clave in disponibles if clave not in vistas)
    return tuple(orden)


class ServicioPreferencias:
    """Lee y escribe las preferencias con conversion y validacion."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._ajustes = RepositorioAjustes(conexion)

    def cargar(self) -> Preferencias:
        """Preferencias vigentes, con los valores por defecto ya aplicados."""
        por_defecto = Configuracion()
        return Preferencias(
            pomodoro=Configuracion(
                trabajo_min=self._entero(_TRABAJO, por_defecto.trabajo_min),
                descanso_corto_min=self._entero(_CORTO, por_defecto.descanso_corto_min),
                descanso_largo_min=self._entero(_LARGO, por_defecto.descanso_largo_min),
                sesiones_por_ciclo=self._entero(_CICLO, por_defecto.sesiones_por_ciclo),
            ),
            preguntar_materia=self._ajustes.obtener(_PREGUNTAR) != "0",
        )

    def guardar(self, preferencias: Preferencias) -> None:
        """Persiste las preferencias, recortadas a sus rangos validos."""
        pomodoro = preferencias.pomodoro
        for clave, valor in (
            (_TRABAJO, pomodoro.trabajo_min),
            (_CORTO, pomodoro.descanso_corto_min),
            (_LARGO, pomodoro.descanso_largo_min),
            (_CICLO, pomodoro.sesiones_por_ciclo),
        ):
            minimo, maximo = _RANGOS[clave]
            self._ajustes.establecer(clave, str(max(minimo, min(maximo, valor))))
        self._ajustes.establecer(_PREGUNTAR, "1" if preferencias.preguntar_materia else "0")

    # -- Disposicion de la barra lateral ------------------------------------

    def disposicion_secciones(self, disponibles: Sequence[str]) -> DisposicionSecciones:
        """Orden y visibilidad vigentes para las secciones indicadas.

        ``disponibles`` llega por parametro y no se importa de la interfaz: el
        nucleo no conoce ``mukuwareru.ui``, y esa regla se comprueba sola.
        """
        orden = reconciliar_orden(self._lista(_ORDEN_SECCIONES), disponibles)
        ocultas = {
            clave for clave in self._lista(_SECCIONES_OCULTAS) if clave in set(disponibles)
        }
        ocultas.discard(_SECCION_IRRENUNCIABLE)
        return DisposicionSecciones(orden=orden, ocultas=frozenset(ocultas))

    def guardar_disposicion_secciones(self, disposicion: DisposicionSecciones) -> None:
        """Persiste orden y ocultas, forzando que Ajustes siga visible."""
        ocultas = set(disposicion.ocultas)
        ocultas.discard(_SECCION_IRRENUNCIABLE)
        self._ajustes.establecer(_ORDEN_SECCIONES, ",".join(disposicion.orden))
        self._ajustes.establecer(_SECCIONES_OCULTAS, ",".join(sorted(ocultas)))

    def estado_barra(self) -> EstadoBarra:
        """Como quedo la barra lateral la ultima vez. Por defecto, completa."""
        bruto = self._ajustes.obtener(_BARRA_LATERAL)
        try:
            return EstadoBarra(bruto) if bruto else EstadoBarra.COMPLETA
        except ValueError:
            return EstadoBarra.COMPLETA

    def guardar_estado_barra(self, estado: EstadoBarra) -> None:
        """Recuerda el estado de la barra para el proximo arranque."""
        self._ajustes.establecer(_BARRA_LATERAL, estado.value)

    def restablecer_disposicion_secciones(self) -> None:
        """Vuelve al orden del catalogo con todo visible."""
        self._ajustes.establecer(_ORDEN_SECCIONES, "")
        self._ajustes.establecer(_SECCIONES_OCULTAS, "")

    def _lista(self, clave: str) -> list[str]:
        """Lee una lista separada por comas, tolerando ausencia y basura."""
        bruto = self._ajustes.obtener(clave)
        if not bruto:
            return []
        return [trozo.strip() for trozo in bruto.split(",") if trozo.strip()]

    def _entero(self, clave: str, por_defecto: int) -> int:
        """Lee un entero tolerando ausencia y valores corruptos."""
        bruto = self._ajustes.obtener(clave)
        if bruto is None:
            return por_defecto
        try:
            valor = int(bruto)
        except ValueError:
            return por_defecto
        minimo, maximo = _RANGOS[clave]
        return max(minimo, min(maximo, valor))
