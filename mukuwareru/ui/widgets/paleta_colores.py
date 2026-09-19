"""Fila de muestras para elegir un color del tema.

Sin ``QColorDialog``: ocho colores estables que ya combinan con el tema oscuro
valen mas que 16 millones entre los que elegir uno que desentone.

Nacio dentro de ``DialogoProyecto`` y salio de ahi cuando las materias tambien
quisieron color propio. Es la misma fila, con una muestra de mas: el proyecto
tiene color obligatorio, la materia puede no tenerlo y caer al de la serie.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from mukuwareru.ui.tema import tokens

_LADO_MUESTRA = 24

# Clave interna de la muestra «Automatico». No es un color, y por eso no puede
# ser una cadena vacia ni `None`: el diccionario de muestras necesita una clave.
_AUTOMATICO = "auto"


class PaletaColores(QWidget):
    """Muestras con ``tokens.SERIE`` y, opcionalmente, «Automatico».

    ``elegido`` emite el color, o cadena vacia cuando se elige «Automatico»: las
    senales de Qt no llevan ``None``. Para leer el valor de verdad esta
    ``color()``, que si devuelve ``None``.
    """

    elegido = Signal(str)

    def __init__(
        self,
        color: str | None = None,
        *,
        permitir_ninguno: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Transparente")
        self._color = color
        self._muestras: dict[str, QPushButton] = {}

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(4)

        if permitir_ninguno:
            fila.addWidget(self._crear_muestra(_AUTOMATICO))
        for tono in tokens.SERIE:
            fila.addWidget(self._crear_muestra(tono))
        fila.addStretch(1)

        self.establecer(color)

    def _crear_muestra(self, clave: str) -> QPushButton:
        automatica = clave == _AUTOMATICO
        muestra = QPushButton()
        muestra.setCheckable(True)
        muestra.setFixedSize(QSize(_LADO_MUESTRA, _LADO_MUESTRA))
        muestra.setCursor(Qt.CursorShape.PointingHandCursor)
        muestra.setToolTip(
            "Automatico: el color de la serie, por posicion" if automatica else clave
        )
        # La muestra automatica se dibuja hueca y con borde punteado: no hay
        # ningun color que ensenar, y un gris cualquiera se leeria como un color
        # elegido mas.
        fondo = "transparent" if automatica else clave
        borde = (
            f"2px dashed {tokens.TEXTO_TENUE}" if automatica else "2px solid transparent"
        )
        muestra.setStyleSheet(
            f"QPushButton {{ background: {fondo}; border: {borde};"
            f" border-radius: {tokens.RADIO_PEQUENO}px; }}"
            f"QPushButton:checked {{ border: 2px solid {tokens.TEXTO}; }}"
        )
        muestra.clicked.connect(lambda _marcado=False, c=clave: self._elegir(c))
        self._muestras[clave] = muestra
        return muestra

    def _elegir(self, clave: str) -> None:
        self.establecer(None if clave == _AUTOMATICO else clave)
        self.elegido.emit(self._color or "")

    def establecer(self, color: str | None) -> None:
        """Marca la muestra correspondiente sin emitir ``elegido``."""
        self._color = color
        activa = color or _AUTOMATICO
        for clave, muestra in self._muestras.items():
            muestra.setChecked(clave == activa)

    def color(self) -> str | None:
        """El color elegido, o ``None`` si esta en «Automatico»."""
        return self._color
