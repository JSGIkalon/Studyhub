"""Panel de entidades que todavia no estan en el lienzo.

Calca el gesto de ``ui/pomodoro/temas.py::ChipTema``: pulsar, arrastrar mas de
ocho pixeles y soltar. Lo que viaja es «que clase de cosa y cual», nunca una
copia de sus datos.

Lo que ya esta colocado **no aparece**. Es la forma mas barata de que la
no-duplicacion se note antes de intentarla; por debajo, los indices unicos de la
migracion 007 la hacen imposible de todos modos.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import DestinoNodo
from mukuwareru.nucleo.servicios import Candidato
from mukuwareru.ui.grafo.lienzo import MIME_NODO
from mukuwareru.ui.tema import tokens

_ARRASTRE_MINIMO = 8
_ANCHO = 240
_MAXIMO_VISIBLE = 120


class ChipEntidad(QPushButton):
    """Pastilla arrastrable con una entidad del proyecto."""

    def __init__(self, candidato: Candidato) -> None:
        super().__init__(candidato.nombre)
        self.setObjectName("ChipTema")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFlat(True)
        self.setToolTip(
            f"{candidato.destino.etiqueta}"
            + (f" · {candidato.detalle}" if candidato.detalle else "")
            + "\nArrastralo al lienzo. No se crea ninguna copia: el nodo apunta "
            "a esta misma entidad."
        )
        self._candidato = candidato
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
        datos.setData(
            MIME_NODO,
            f"{self._candidato.destino.value}\t{self._candidato.objeto_id}".encode(),
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


class PanelEntidades(QWidget):
    """Columna con filtro por tipo y por texto."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_ANCHO)
        self._candidatos: list[Candidato] = []

        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, tokens.ESPACIO_PEQUENO, 0)
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        titulo = QLabel("Sin colocar")
        titulo.setStyleSheet("font-weight: 600;")
        columna.addWidget(titulo)

        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        self._tipo = QComboBox()
        self._tipo.addItem("Todo", None)
        for destino in DestinoNodo:
            self._tipo.addItem(destino.etiqueta, destino)
        self._tipo.currentIndexChanged.connect(self._repintar)
        fila.addWidget(self._tipo, 1)
        columna.addLayout(fila)

        self._filtro = QLineEdit()
        self._filtro.setPlaceholderText("Filtrar…")
        self._filtro.setClearButtonEnabled(True)
        self._filtro.textChanged.connect(self._repintar)
        columna.addWidget(self._filtro)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QScrollArea.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        interior = QWidget()
        interior.setObjectName("Transparente")
        self._caja = QVBoxLayout(interior)
        self._caja.setContentsMargins(0, 0, 0, 0)
        self._caja.setSpacing(2)
        self._caja.setAlignment(Qt.AlignmentFlag.AlignTop)
        desplazable.setWidget(interior)
        columna.addWidget(desplazable, 1)

        self._pie = QLabel()
        self._pie.setObjectName("TextoTenue")
        self._pie.setWordWrap(True)
        columna.addWidget(self._pie)

    def establecer(self, candidatos: list[Candidato]) -> None:
        """Sustituye la lista y repinta."""
        self._candidatos = candidatos
        self._repintar()

    def _repintar(self) -> None:
        while (elemento := self._caja.takeAt(0)) is not None:
            if (widget := elemento.widget()) is not None:
                widget.deleteLater()

        tipo = self._tipo.currentData()
        texto = self._filtro.text().strip().lower()
        visibles = [
            c
            for c in self._candidatos
            if (tipo is None or c.destino is tipo)
            and (not texto or texto in c.nombre.lower())
        ]

        if not visibles:
            vacio = QLabel(
                "Todo colocado."
                if self._candidatos
                else "Este proyecto aun no tiene materias que colocar."
            )
            vacio.setObjectName("TextoTenue")
            vacio.setWordWrap(True)
            self._caja.addWidget(vacio)
            self._pie.setText("")
            return

        # Con 93 modulos, pintar la lista entera cuesta mas de lo que aporta:
        # para eso esta el filtro, y el pie dice cuantos quedan fuera.
        for candidato in visibles[:_MAXIMO_VISIBLE]:
            self._caja.addWidget(ChipEntidad(candidato))

        sobran = len(visibles) - _MAXIMO_VISIBLE
        self._pie.setText(
            f"y {sobran} mas · afina el filtro" if sobran > 0 else "arrastra al lienzo →"
        )
