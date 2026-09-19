"""Lienzo del grafo de dependencias.

**Aviso para quien venga a cambiar colores:** nada de lo que hay aqui se estiliza
con ``oscuro.qss``. Un ``QGraphicsItem`` no es un widget y el QSS no lo alcanza,
asi que los colores salen directamente de ``ui/tema/tokens.py`` dentro de cada
``paint()``, igual que en ``widgets/anillo.py``. Una regla en la hoja de estilos
para ``ItemNodo`` no haria nada y costaria una tarde entenderlo.
"""

from mukuwareru.ui.grafo.arista import ItemArista
from mukuwareru.ui.grafo.lienzo import MIME_NODO, LienzoGrafo
from mukuwareru.ui.grafo.nodo import ALTO_NODO, ANCHO_NODO, ItemNodo
from mukuwareru.ui.grafo.panel_entidades import PanelEntidades

__all__ = [
    "ALTO_NODO",
    "ANCHO_NODO",
    "MIME_NODO",
    "ItemArista",
    "ItemNodo",
    "LienzoGrafo",
    "PanelEntidades",
]
