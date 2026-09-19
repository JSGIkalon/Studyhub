"""Tira de temas del proyecto, arrastrables al timeline.

Los temas viven en la seccion Progreso, pero arrastrar de una seccion a otra es
imposible: las vistas estan en un ``QStackedWidget`` y nunca coinciden en
pantalla. Asi que la tira se repite aqui, en pequeno y de solo lectura, para que
el gesto «este tema, ahora» exista de verdad.

No toca la base de datos: lee las materias del proyecto activo y emite arrastres.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from mukuwareru.nucleo.modelos import Materia
from mukuwareru.ui.tema import tokens

MIME_MATERIA = "application/x-mukuwareru-materia"

_ARRASTRE_MINIMO = 8
_ALTO = 32


class ChipTema(QPushButton):
    """Pastilla con el nombre de una materia. Solo sirve para arrastrarla."""

    def __init__(self, materia: Materia, color: str) -> None:
        super().__init__(materia.nombre)
        self.setObjectName("ChipTema")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(f"Arrastra «{materia.nombre}» al timeline para crear un bloque")
        self.setFlat(True)
        self.setStyleSheet(f"color: {color};")
        # Fijo: en una fila con doce temas, un chip elastico se comprime hasta
        # cortar el nombre por la mitad. La fila se desplaza en su lugar.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._materia = materia
        self._origen: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if event.button() is Qt.MouseButton.LeftButton:
            self._origen = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if self._origen is None:
            return
        if (event.position().toPoint() - self._origen).manhattanLength() < _ARRASTRE_MINIMO:
            return

        datos = QMimeData()
        # El id va delante y el nombre detras: el nombre puede llevar cualquier
        # caracter, el id no, asi que se parte por el primer separador.
        datos.setData(
            MIME_MATERIA,
            f"{self._materia.id}\t{self._materia.nombre}".encode(),
        )
        arrastre = QDrag(self)
        arrastre.setMimeData(datos)
        arrastre.setPixmap(self.grab())
        arrastre.setHotSpot(self._origen)
        self._origen = None
        arrastre.exec(Qt.DropAction.CopyAction)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        self._origen = None
        super().mouseReleaseEvent(event)


class TiraTemas(QScrollArea):
    """Fila horizontal de temas del proyecto activo, con desplazamiento.

    Un proyecto de CFA tiene diez temas de nombres largos. Apretarlos en el ancho
    de la ventana los corta; se desplazan, como el propio timeline.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("TiraTemas")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setFixedHeight(_ALTO)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        interior = QWidget()
        interior.setObjectName("Transparente")
        self._caja = QHBoxLayout(interior)
        self._caja.setContentsMargins(0, 0, 0, 0)
        self._caja.setSpacing(tokens.ESPACIO_PEQUENO)
        self._caja.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._titulo = QLabel("Temas")
        self._titulo.setObjectName("TextoTenue")
        self._caja.addWidget(self._titulo)

        self._aviso = QLabel()
        self._aviso.setObjectName("TextoTenue")
        self._caja.addWidget(self._aviso)
        self.setWidget(interior)

    def establecer(self, materias: list[Materia]) -> None:
        """Repinta la tira con las materias indicadas."""
        # El titulo y el aviso se quedan; los chips van detras.
        while self._caja.count() > 2:
            elemento = self._caja.takeAt(2)
            if elemento is not None and (widget := elemento.widget()) is not None:
                widget.deleteLater()

        if not materias:
            self._aviso.setText("sin temas todavia · se crean en Progreso")
            return

        self._aviso.setText("arrastra uno al timeline  →")
        for indice, materia in enumerate(materias):
            color = materia.color or tokens.color_serie(indice)
            self._caja.addWidget(ChipTema(materia, color))
