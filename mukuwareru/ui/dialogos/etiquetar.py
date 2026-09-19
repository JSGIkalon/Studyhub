"""Etiquetado opcional de una sesion terminada.

El Pomodoro no se asocia a un modulo, porque en una sesion se pueden estudiar
varios temas. Este dialogo permite marcar a posteriori que materias se tocaron,
y es siempre omitible: sin el no existiria el dato de «tiempo por materia», y
con el no obliga a nada.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Materia
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets import contenedor
from mukuwareru.utilidades import formato


class DialogoEtiquetar(QDialog):
    """Pregunta que materias se estudiaron durante la sesion recien terminada."""

    def __init__(
        self, materias: list[Materia], duracion_seg: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sesion completada")
        self.setMinimumWidth(400)
        self._casillas: dict[int, QCheckBox] = {}
        self._construir(materias, duracion_seg)

    def _construir(self, materias: list[Materia], duracion_seg: int) -> None:
        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        titulo = QLabel(f"Sesion de {formato.horas(duracion_seg)} registrada.")
        titulo.setStyleSheet("font-weight: 600;")
        columna.addWidget(titulo)

        pregunta = QLabel("¿Que materias estudiaste? Puedes marcar varias, o ninguna.")
        pregunta.setObjectName("TextoSuave")
        pregunta.setWordWrap(True)
        columna.addWidget(pregunta)

        if materias:
            caja = QVBoxLayout()
            caja.setSpacing(2)
            for materia in materias:
                casilla = QCheckBox(materia.nombre)
                casilla.setCursor(Qt.CursorShape.PointingHandCursor)
                self._casillas[materia.id] = casilla
                caja.addWidget(casilla)

            desplazable = QScrollArea()
            desplazable.setWidgetResizable(True)
            desplazable.setMaximumHeight(260)
            desplazable.setWidget(contenedor(caja))
            columna.addWidget(desplazable)
        else:
            aviso = QLabel("Este proyecto no tiene materias todavia.")
            aviso.setObjectName("TextoTenue")
            columna.addWidget(aviso)

        self._no_preguntar = QCheckBox("No volver a preguntar")
        columna.addWidget(self._no_preguntar)

        botones = QDialogButtonBox()
        omitir = botones.addButton("Omitir", QDialogButtonBox.ButtonRole.RejectRole)
        guardar = botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        guardar.setObjectName("BotonPrimario")
        guardar.setDefault(True)
        omitir.clicked.connect(self.reject)
        guardar.clicked.connect(self.accept)
        columna.addWidget(botones)

    @property
    def materias_elegidas(self) -> list[int]:
        """Identificadores de las materias marcadas."""
        return [i for i, casilla in self._casillas.items() if casilla.isChecked()]

    @property
    def no_volver_a_preguntar(self) -> bool:
        """Si el usuario pidio desactivar la pregunta."""
        return self._no_preguntar.isChecked()
