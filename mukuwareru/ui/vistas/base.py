"""Contrato comun de las vistas principales.

Implementa la recarga perezosa: al cambiar de proyecto todas las vistas se
marcan como sucias, pero solo la visible se recarga de inmediato. Las demas
esperan a que se las muestre. Evita reconstruir siete vistas en cada cambio.
"""

from __future__ import annotations

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QWidget

from mukuwareru.contexto import Contexto


class VistaBase(QWidget):
    """Base de toda vista enganchada al conmutador principal."""

    titulo: str = ""

    # Que escribe esta vista, para quien escuche `datos_cambiados`.
    dominio: str | None = None
    # Dominios que esta vista NO muestra: sus cambios no la ensucian. Ante la
    # duda no se pone: una recarga de mas es lenta; una de menos, un dato viejo.
    ignora: frozenset[str] = frozenset()

    def __init__(self, contexto: Contexto, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.contexto = contexto
        self._sucia = True
        contexto.proyecto_cambiado.connect(self._al_cambiar_proyecto)
        contexto.datos_cambiados.connect(self._al_cambiar_datos)
        self._construir()

    # -- Ganchos que sobrescriben las subclases ----------------------------

    def _construir(self) -> None:
        """Crea los widgets. Se llama una unica vez, en el constructor."""

    def recargar(self) -> None:
        """Vuelca los datos del proyecto activo en los widgets ya creados."""

    # -- Mecanica de recarga perezosa --------------------------------------

    def _al_cambiar_proyecto(self, _proyecto: object) -> None:
        self._sucia = True
        if self.isVisible():
            self.refrescar_si_hace_falta()

    def _al_cambiar_datos(self, origen: object, dominio: object = None) -> None:
        if origen is self or dominio in self.ignora:
            return
        self._sucia = True
        if self.isVisible():
            self.refrescar_si_hace_falta()

    def refrescar_si_hace_falta(self) -> None:
        """Recarga solo si hay cambios pendientes."""
        if self._sucia:
            self.recargar()
            self._sucia = False

    def marcar_sucia(self) -> None:
        """Fuerza una recarga en la proxima vez que se muestre la vista."""
        self._sucia = True

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (API de Qt)
        super().showEvent(event)
        self.refrescar_si_hace_falta()
