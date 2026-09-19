"""Aplicacion del tema oscuro."""

from __future__ import annotations

from importlib import resources

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from mukuwareru.ui.tema import tokens


def aplicar(app: QApplication) -> None:
    """Instala estilo, paleta, fuente y hoja de estilos sobre la aplicacion."""
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(_paleta())
    app.setFont(QFont(tokens.FUENTE, tokens.TAM_BASE))

    plantilla = resources.files("mukuwareru.ui.tema").joinpath("oscuro.qss")
    app.setStyleSheet(tokens.expandir(plantilla.read_text(encoding="utf-8")))


def _paleta() -> QPalette:
    """Paleta base.

    El QSS no cubre los dialogos nativos ni los menus, asi que la paleta evita
    que aparezcan en claro.
    """
    p = QPalette()
    fondo, superficie = QColor(tokens.FONDO), QColor(tokens.SUPERFICIE_ALTA)
    texto, acento = QColor(tokens.TEXTO), QColor(tokens.ACENTO)

    p.setColor(QPalette.ColorRole.Window, fondo)
    p.setColor(QPalette.ColorRole.WindowText, texto)
    p.setColor(QPalette.ColorRole.Base, superficie)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.SUPERFICIE))
    p.setColor(QPalette.ColorRole.Text, texto)
    p.setColor(QPalette.ColorRole.Button, superficie)
    p.setColor(QPalette.ColorRole.ButtonText, texto)
    p.setColor(QPalette.ColorRole.ToolTipBase, superficie)
    p.setColor(QPalette.ColorRole.ToolTipText, texto)
    p.setColor(QPalette.ColorRole.Highlight, acento)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(tokens.TEXTO_TENUE))

    apagado = QColor(tokens.TEXTO_TENUE)
    for rol in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, rol, apagado)
    return p
