"""Tokens de diseno: la unica fuente de verdad visual del proyecto.

La hoja de estilos ``oscuro.qss`` es una plantilla con marcadores ``{{clave}}``
que se sustituyen con estos valores al arrancar. Asi el mismo color sirve para
QSS y para el codigo que pinta con ``QPainter`` (anillo del Pomodoro,
graficos), sin duplicar constantes.
"""

from __future__ import annotations

from typing import Final

# --- Superficies -----------------------------------------------------------
FONDO: Final = "#0E0E10"          # lienzo de la aplicacion
FONDO_LATERAL: Final = "#121214"  # barra lateral
SUPERFICIE: Final = "#17171A"     # tarjetas
SUPERFICIE_ALTA: Final = "#1E1E22"  # hover, campos de entrada
BORDE: Final = "#26262B"
BORDE_SUTIL: Final = "#1F1F24"

# --- Texto -----------------------------------------------------------------
TEXTO: Final = "#EDEDEF"
TEXTO_SUAVE: Final = "#9B9BA3"
TEXTO_TENUE: Final = "#6B6B73"

# --- Acento y estados ------------------------------------------------------
ACENTO: Final = "#E5484D"
ACENTO_HOVER: Final = "#EC5D62"
ACENTO_TENUE: Final = "#2A1416"   # fondo del elemento de navegacion activo
EXITO: Final = "#30A46C"
AVISO: Final = "#F5A524"
INFO: Final = "#3E63DD"
NARANJA: Final = "#F76B15"

# Paleta ciclica para las barras de progreso por materia.
SERIE: Final = (EXITO, AVISO, NARANJA, ACENTO, INFO, "#8E4EC6", "#0D9488", "#D6409F")

# --- Geometria -------------------------------------------------------------
RADIO: Final = 10
RADIO_PEQUENO: Final = 6
ESPACIO: Final = 16
ESPACIO_PEQUENO: Final = 8
ESPACIO_GRANDE: Final = 24
ANCHO_LATERAL: Final = 244
ANCHO_LATERAL_COLAPSADA: Final = 56

# --- Tipografia ------------------------------------------------------------
FUENTE: Final = "Segoe UI"
TAM_BASE: Final = 13
TAM_PEQUENO: Final = 11
TAM_TITULO: Final = 22
TAM_METRICA: Final = 28


def como_diccionario() -> dict[str, str]:
    """Expone los tokens en mayusculas como cadenas, para expandir el QSS."""
    modulo = globals()
    return {
        clave: str(valor)
        for clave, valor in modulo.items()
        if clave.isupper() and isinstance(valor, str | int)
    }


def expandir(plantilla: str) -> str:
    """Sustituye cada ``{{TOKEN}}`` de la plantilla por su valor."""
    resultado = plantilla
    for clave, valor in como_diccionario().items():
        resultado = resultado.replace(f"{{{{{clave}}}}}", valor)
    return resultado


def color_serie(indice: int) -> str:
    """Color estable para el elemento ``indice`` de una serie."""
    return SERIE[indice % len(SERIE)]


def color_o_serie(color: str | None, indice: int) -> str:
    """El color propio si lo hay; si no, el de la serie por posicion.

    El respaldo vive aqui y en ningun otro sitio: una materia sin color propio
    tiene que pintarse igual en el Panel y en Progreso, y eso solo se sostiene
    si las dos vistas preguntan lo mismo.
    """
    return color or color_serie(indice)
