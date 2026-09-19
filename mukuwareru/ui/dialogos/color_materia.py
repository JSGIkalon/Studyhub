"""Color de una materia.

Recoge datos y no escribe nada, como el resto de dialogos. A diferencia del
proyecto, una materia puede **no** tener color propio: entonces se pinta con el
de la serie segun su posicion, que es lo que hacian todas hasta ahora.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Materia
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets import PaletaColores


class DialogoColorMateria(QDialog):
    """Elige el color de una materia, o lo devuelve a «Automatico»."""

    def __init__(self, materia: Materia, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Color de {materia.nombre}")
        self.setMinimumWidth(360)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        self._paleta = PaletaColores(materia.color, permitir_ninguno=True)
        columna.addWidget(self._paleta)

        ayuda = QLabel(
            "La muestra punteada es «Automatico»: la materia toma el color que "
            "le toque por su posicion en la lista, como hasta ahora. El color "
            "elegido se usa en el Panel y en Progreso."
        )
        ayuda.setObjectName("TextoTenue")
        ayuda.setWordWrap(True)
        columna.addWidget(ayuda)

        botones = QDialogButtonBox()
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        aceptar = botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        aceptar.setObjectName("BotonPrimario")
        aceptar.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)

    def color(self) -> str | None:
        """El color elegido, o ``None`` para volver al de la serie."""
        return self._paleta.color()
