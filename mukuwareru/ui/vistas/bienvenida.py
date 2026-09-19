"""Estado vacio: no hay ningun proyecto.

**No es una seccion** y **no es un dialogo modal.** Vive en el conmutador, igual
que el lector, y se muestra en lugar de la seccion elegida mientras no haya
proyecto activo.

Que no sea modal es deliberado por dos razones. Un asistente de primer arranque
solo cubre el arranque en frio, no el «acabo de borrar mi ultimo proyecto», que
lleva al mismo sitio; y un modal disparado desde el constructor de la ventana
dejaria colgada la prueba de humo, que construye varias ventanas seguidas y no
tiene a nadie que pulse un boton.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from mukuwareru.ui import iconos
from mukuwareru.ui.tema import tokens
from mukuwareru.utilidades import rutas


class PanelBienvenida(QWidget):
    """Invita a crear el primer proyecto y no ofrece nada mas."""

    crear_proyecto = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PanelBienvenida")
        self._construir()

    def _construir(self) -> None:
        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)
        columna.setAlignment(Qt.AlignmentFlag.AlignCenter)
        columna.addStretch(1)

        logo = QLabel()
        logo.setPixmap(iconos.icono_aplicacion().pixmap(96, 96))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        columna.addWidget(logo)
        columna.addSpacing(tokens.ESPACIO)

        titulo = QLabel("Bienvenido a Mukuwareru")
        titulo.setObjectName("TituloVista")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        columna.addWidget(titulo)

        texto = QLabel(
            "Un proyecto es un examen, un curso o una carrera: agrupa su temario, "
            "sus PDFs, tus notas y el tiempo que le dedicas.\n"
            "Crea el primero para empezar."
        )
        texto.setObjectName("TextoSuave")
        texto.setWordWrap(True)
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto.setMaximumWidth(460)
        columna.addWidget(texto, alignment=Qt.AlignmentFlag.AlignCenter)
        columna.addSpacing(tokens.ESPACIO)

        boton = QPushButton("  Crear mi primer proyecto")
        boton.setObjectName("BotonPrimario")
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.setIcon(iconos.icono("mas", tokens.TEXTO))
        boton.setMinimumHeight(36)
        boton.clicked.connect(self.crear_proyecto.emit)
        columna.addWidget(boton, alignment=Qt.AlignmentFlag.AlignCenter)

        columna.addStretch(1)

        ruta = QLabel(f"Tus datos se guardan en {rutas.raiz_datos()}")
        ruta.setObjectName("TextoTenue")
        ruta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ruta.setWordWrap(True)
        columna.addWidget(ruta)
