"""Texto plano a partir del HTML de una nota.

El editor de notas guarda HTML autocontenido con las imagenes pegadas como
``data:`` URI en base64 (ver ``ui/dialogos/nota.py``). Buscar con ``LIKE`` sobre
ese HTML es lento y, peor, **falso**: «gif» o «AAA» aparecen dentro del base64 de
cualquier imagen. De ahi la columna ``nota.cuerpo_plano``, que se deriva aqui.

Se usa ``html.parser`` y no ``QTextDocument`` por dos razones: el nucleo no puede
importar Qt, y asi la extraccion se prueba con pytest sin arrancar una
``QApplication``.
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser

_PREFIJO_ENRIQUECIDO = "<!doctype html"

# El caracter de reemplazo que Qt deja en el texto por cada imagen incrustada.
_OBJETO_INCRUSTADO = "￼"

# Etiquetas cuyo contenido no es texto visible.
_INVISIBLES = frozenset({"script", "style", "head", "title"})

# Etiquetas que separan palabras: sin esto, «<p>uno</p><p>dos</p>» daria
# «unodos» y una busqueda por «uno» seguiria funcionando, pero el resumen que se
# muestra en la lista de notas seria ilegible.
_SEPARADORAS = frozenset({
    "p", "br", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "hr", "table", "ul", "ol",
})


class _Extractor(HTMLParser):
    """Acumula el texto visible de un fragmento HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._trozos: list[str] = []
        self._ignorando = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _INVISIBLES:
            self._ignorando += 1
        elif tag == "img":
            self._trozos.append(" [imagen] ")
        elif tag in _SEPARADORAS:
            self._trozos.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _INVISIBLES and self._ignorando:
            self._ignorando -= 1
        elif tag in _SEPARADORAS:
            self._trozos.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._ignorando:
            self._trozos.append(data)

    def resultado(self) -> str:
        return "".join(self._trozos)


def es_enriquecido(texto: str) -> bool:
    """Si el texto es el HTML que produce el editor de notas."""
    return texto.lstrip().lower().startswith(_PREFIJO_ENRIQUECIDO)


def a_texto_plano(texto: str) -> str:
    """Version en una linea, sin etiquetas ni imagenes: para buscar y resumir.

    Un texto que no viene del editor se devuelve tal cual (normalizando los
    espacios): no hay nada que desmontar y pasarlo por el parser solo abriria la
    puerta a que un ``<`` escrito a mano se comiera media nota.
    """
    if not texto:
        return ""
    if not es_enriquecido(texto):
        return " ".join(texto.replace(_OBJETO_INCRUSTADO, " [imagen] ").split())

    extractor = _Extractor()
    extractor.feed(texto)
    extractor.close()
    plano = extractor.resultado().replace(_OBJETO_INCRUSTADO, " [imagen] ")
    return " ".join(unescape(plano).split())


def primera_linea(texto: str, maximo: int = 80) -> str:
    """Titulo implicito de una nota sin titulo, recortado por palabras.

    Recortar a mitad de palabra se lee peor que recortar antes; solo se parte una
    palabra si es tan larga que no cabe entera.
    """
    plano = a_texto_plano(texto)
    if len(plano) <= maximo:
        return plano
    recorte = plano[:maximo]
    if " " in recorte:
        recorte = recorte.rsplit(" ", 1)[0]
    return recorte.rstrip() + "…"
