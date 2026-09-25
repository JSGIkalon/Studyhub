"""Vistas principales y su registro de navegacion.

``SECCIONES`` es el **catalogo**: declara que secciones existen, con que icono y
con que clase. Anadir una es anadir una linea aqui.

El **orden y la visibilidad** ya no se deciden en esta lista, sino en las
preferencias del usuario (``ServicioPreferencias.disposicion_secciones``), que se
reconcilian con este catalogo en cada arranque. Por eso el conmutador de la
ventana construye siempre todas las secciones, aunque alguna este oculta.
"""

from __future__ import annotations

from dataclasses import dataclass

from mukuwareru.ui.vistas.ajustes import VistaAjustes
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.vistas.biblioteca import VistaBiblioteca
from mukuwareru.ui.vistas.calendario import VistaCalendario
from mukuwareru.ui.vistas.estadisticas import VistaEstadisticas
from mukuwareru.ui.vistas.notas import VistaNotas
from mukuwareru.ui.vistas.panel import VistaPanel
from mukuwareru.ui.vistas.pomodoro import VistaPomodoro
from mukuwareru.ui.vistas.progreso import VistaProgreso
from mukuwareru.ui.vistas.resultados import VistaResultados


@dataclass(frozen=True, slots=True)
class Seccion:
    """Una entrada de navegacion y la vista que le corresponde."""

    clave: str
    etiqueta: str
    icono: str
    clase: type[VistaBase]


SECCIONES: tuple[Seccion, ...] = (
    Seccion("panel", "Panel", "panel", VistaPanel),
    Seccion("pomodoro", "Pomodoro", "reloj", VistaPomodoro),
    Seccion("biblioteca", "Biblioteca", "documento", VistaBiblioteca),
    # «Notas» absorbio a la antigua seccion «Anotaciones» en cuanto a su lugar
    # en la barra lateral, pero los resaltados y marcadores del PDF siguen
    # viviendo en el lector: aqui solo hay cuadernos, secciones y notas que se
    # pueden ligar. La clave `anotaciones` que quedara guardada en las
    # preferencias de alguna instalacion se descarta sola al reconciliar el
    # orden.
    Seccion("notas", "Notas", "nota", VistaNotas),
    Seccion("calendario", "Calendario", "calendario", VistaCalendario),
    Seccion("progreso", "Progreso", "grafico", VistaProgreso),
    # Entre Progreso y Estadisticas a proposito: el orden mental es temario ->
    # notas -> tiempo. La clave nueva la coloca sola `reconciliar_orden` en las
    # instalaciones que ya tenian un orden guardado, sin migracion.
    Seccion("resultados", "Resultados", "diana", VistaResultados),
    Seccion("estadisticas", "Estadisticas", "estadisticas", VistaEstadisticas),
    Seccion("ajustes", "Ajustes", "engranaje", VistaAjustes),
)

__all__ = ["SECCIONES", "Seccion", "VistaBase"]
