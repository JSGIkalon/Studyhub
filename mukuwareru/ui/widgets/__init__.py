"""Widgets reutilizables, sin conocimiento del dominio."""

from mukuwareru.ui.widgets.anillo import AnilloProgreso
from mukuwareru.ui.widgets.anillo_reloj import AnilloReloj
from mukuwareru.ui.widgets.barra_atencion import BarraAtencion
from mukuwareru.ui.widgets.barra_materia import BarraMateria
from mukuwareru.ui.widgets.contenedor import contenedor
from mukuwareru.ui.widgets.grafico import GraficoBarras
from mukuwareru.ui.widgets.paleta_colores import PaletaColores
from mukuwareru.ui.widgets.tarjeta import Tarjeta
from mukuwareru.ui.widgets.tarjeta_documento import TarjetaDocumento
from mukuwareru.ui.widgets.tarjeta_metrica import ListaResumen, TarjetaMetrica

__all__ = [
    "AnilloProgreso",
    "AnilloReloj",
    "BarraAtencion",
    "BarraMateria",
    "GraficoBarras",
    "ListaResumen",
    "PaletaColores",
    "Tarjeta",
    "TarjetaDocumento",
    "TarjetaMetrica",
    "contenedor",
]
