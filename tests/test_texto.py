"""Extraccion de texto plano del HTML de una nota."""

from __future__ import annotations

from mukuwareru.utilidades.texto import a_texto_plano, es_enriquecido, primera_linea

_HTML = (
    "<!doctype html><html><head><style>p { color: red }</style></head>"
    "<body><p>Primera linea</p><p>Segunda linea</p></body></html>"
)


def test_el_texto_llano_se_devuelve_tal_cual() -> None:
    assert a_texto_plano("una nota sencilla") == "una nota sencilla"


def test_el_texto_vacio_no_falla() -> None:
    assert a_texto_plano("") == ""


def test_reconoce_el_html_del_editor() -> None:
    assert es_enriquecido(_HTML) is True
    assert es_enriquecido("  <!DOCTYPE HTML>...") is True
    assert es_enriquecido("<p>escrito a mano</p>") is False


def test_quita_etiquetas_y_separa_los_parrafos() -> None:
    plano = a_texto_plano(_HTML)
    assert plano == "Primera linea Segunda linea"


def test_las_etiquetas_invisibles_no_aportan_texto() -> None:
    assert "color" not in a_texto_plano(_HTML)


def test_una_imagen_en_base64_no_contamina_la_busqueda() -> None:
    """El motivo de que exista `cuerpo_plano` en lugar de un LIKE sobre el HTML."""
    html = (
        "<!doctype html><html><body><p>Sobre las normas</p>"
        '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAgifAAA" '
        'width="10" height="10"></body></html>'
    )
    plano = a_texto_plano(html)
    assert plano == "Sobre las normas [imagen]"
    assert "base64" not in plano
    # Sin la extraccion, buscar «gif» encontraria esta nota por su base64.
    assert "gif" not in plano.lower()


def test_el_caracter_de_objeto_incrustado_se_traduce() -> None:
    assert a_texto_plano("antes ￼ despues") == "antes [imagen] despues"


def test_se_deshacen_las_entidades() -> None:
    html = "<!doctype html><html><body><p>M&aacute;s del 50 &amp; algo</p></body></html>"
    assert a_texto_plano(html) == "Más del 50 & algo"


def test_los_espacios_quedan_normalizados() -> None:
    html = "<!doctype html><html><body><p>uno</p>\n\n   <p>  dos  </p></body></html>"
    assert a_texto_plano(html) == "uno dos"


def test_primera_linea_recorta_por_palabras() -> None:
    texto = "palabra " * 30
    resumen = primera_linea(texto, maximo=20)
    assert len(resumen) <= 21          # 20 mas los puntos suspensivos
    assert resumen.endswith("…")
    assert not resumen.startswith(" ")
    # No parte una palabra por la mitad.
    assert "palabr…" not in resumen


def test_primera_linea_devuelve_el_texto_corto_intacto() -> None:
    assert primera_linea("corta") == "corta"


def test_primera_linea_parte_una_palabra_inmensa() -> None:
    """Sin espacios no hay donde cortar: mejor recortar que devolver todo."""
    resumen = primera_linea("a" * 200, maximo=10)
    assert resumen == "a" * 10 + "…"
