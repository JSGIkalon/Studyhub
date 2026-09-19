"""Contenedor transparente.

Un ``QWidget`` plano hereda ``FONDO`` de la regla global del QSS. Dentro de una
tarjeta, cuyo fondo es ``SUPERFICIE``, eso dibuja un rectangulo mas oscuro que
no deberia estar ahi. Todo widget que solo exista para alojar una disposicion
debe crearse con esta funcion.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLayout, QWidget


def contenedor(disposicion: QLayout) -> QWidget:
    """Envuelve una disposicion en un widget sin fondo propio."""
    widget = QWidget()
    widget.setObjectName("Transparente")
    widget.setLayout(disposicion)
    return widget
