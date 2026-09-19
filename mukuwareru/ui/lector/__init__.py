"""Visor de PDF propio.

``QPdfView`` no expone la seleccion de texto ni el mapeo entre el viewport y las
coordenadas de pagina, sin el cual no hay resaltados anclados. Aqui se usa el
motor de Qt (``QPdfDocument``, ``QPdfSearchModel``, ``QPdfBookmarkModel``) con
una vista propia encima.
"""

from mukuwareru.ui.lector.cache import CachePaginas
from mukuwareru.ui.lector.disposicion import Disposicion
from mukuwareru.ui.lector.panel_lateral import PanelLateral
from mukuwareru.ui.lector.vista_lector import VistaLector
from mukuwareru.ui.lector.vista_paginas import Resaltado, VistaPaginas

__all__ = [
    "CachePaginas",
    "Disposicion",
    "PanelLateral",
    "Resaltado",
    "VistaLector",
    "VistaPaginas",
]
