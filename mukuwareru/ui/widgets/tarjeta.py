"""Tarjeta: la superficie elevada que estructura todas las vistas."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from mukuwareru.ui.tema import tokens


class Tarjeta(QFrame):
    """Contenedor con fondo, borde y esquinas redondeadas.

    El aspecto vive integramente en ``oscuro.qss`` mediante el nombre de objeto
    ``Tarjeta``; aqui solo se define la estructura.
    """

    def __init__(self, titulo: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Tarjeta")

        self.contenido = QVBoxLayout(self)
        self.contenido.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        self.contenido.setSpacing(tokens.ESPACIO_PEQUENO)

        if titulo:
            etiqueta = QLabel(titulo)
            etiqueta.setStyleSheet("font-weight: 600;")
            self.contenido.addWidget(etiqueta)

    def agregar(self, widget: QWidget) -> None:
        """Anade un widget al cuerpo de la tarjeta."""
        self.contenido.addWidget(widget)
