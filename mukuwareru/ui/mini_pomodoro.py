"""Mini ventana del Pomodoro para cuando Mukuwareru esta minimizado.

Es la unica ventana secundaria de la aplicacion, y existe por una razon concreta:
mientras se estudia, la ventana principal esta minimizada casi todo el rato. Un
temporizador que solo se ve al restaurar la ventana no cumple su funcion.

Se muestra sola al minimizar con el reloj en marcha y se esconde al restaurar.
No aparece en la barra de tareas (``Qt.Tool``) para no duplicar la entrada de
Mukuwareru, y se puede arrastrar a cualquier sitio de la pantalla.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mukuwareru.nucleo.servicios import Estado, Fase
from mukuwareru.ui.tema import tokens
from mukuwareru.utilidades import formato

_MARGEN_PANTALLA = 24

_COLOR_FASE = {
    Fase.TRABAJO: tokens.ACENTO,
    Fase.DESCANSO_CORTO: tokens.INFO,
    Fase.DESCANSO_LARGO: tokens.EXITO,
}


class MiniPomodoro(QWidget):
    """Reloj flotante: fase, tiempo y control de pausa.

    Sirve a las dos formas de cronometrar. Con el Pomodoro cuenta hacia atras;
    con una sesion de trabajo indefinida cuenta hacia arriba y saca el boton de
    detener, que ahi es imprescindible: esa sesion no termina sola y la ventana
    principal esta minimizada.
    """

    alternar_pedido = Signal()
    detener_pedido = Signal()
    restaurar_pedido = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MiniPomodoro")
        self.setWindowTitle("Mukuwareru · Pomodoro")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._arrastre: QPoint | None = None
        # En cuanto el usuario la mueve, la posicion es suya: `colocar_por_defecto`
        # se llama en cada aparicion y sin esta marca la devolveria a la esquina.
        self._colocada = False
        self._construir()

    def _construir(self) -> None:
        caja = QVBoxLayout(self)
        caja.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO_PEQUENO, tokens.ESPACIO, tokens.ESPACIO_PEQUENO
        )
        caja.setSpacing(2)

        cabecera = QHBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        self._fase = QLabel()
        self._fase.setObjectName("MiniFase")
        cabecera.addWidget(self._fase, 1)

        cerrar = QPushButton("✕")  # cruz de cerrar; el aspa no es una «x»
        cerrar.setObjectName("MiniCerrar")
        cerrar.setFixedSize(20, 20)
        cerrar.setToolTip("Volver a Mukuwareru")
        cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        cerrar.clicked.connect(self.restaurar_pedido.emit)
        cabecera.addWidget(cerrar)
        caja.addLayout(cabecera)

        self._tiempo = QLabel()
        self._tiempo.setObjectName("MiniTiempo")
        caja.addWidget(self._tiempo)

        controles = QHBoxLayout()
        controles.setSpacing(tokens.ESPACIO_PEQUENO)

        self._boton = QPushButton()
        self._boton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton.clicked.connect(self.alternar_pedido.emit)
        controles.addWidget(self._boton, 1)

        self._boton_detener = QPushButton("Detener")
        self._boton_detener.setToolTip("Cierra la sesion y registra el tiempo.")
        self._boton_detener.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_detener.clicked.connect(self.detener_pedido.emit)
        self._boton_detener.setVisible(False)
        controles.addWidget(self._boton_detener, 1)
        caja.addLayout(controles)

        self._pista = QLabel("Doble clic para volver")
        self._pista.setObjectName("TextoTenue")
        caja.addWidget(self._pista)

    # -- Datos --------------------------------------------------------------

    def actualizar(self, fase: Fase, restante_seg: int, estado: Estado) -> None:
        """Refresca fase, cuenta atras y texto del boton."""
        self._boton_detener.setVisible(False)
        self._pista.setText("Doble clic para volver")
        self._volcar(fase.etiqueta.upper(), restante_seg, estado, _COLOR_FASE[fase])

    def actualizar_libre(self, transcurrido_seg: int, estado: Estado) -> None:
        """Lo mismo para una sesion indefinida: cuenta hacia arriba y se detiene.

        El boton de detener solo aparece aqui. Un pomodoro acaba solo cuando
        llega a cero; esta sesion no acaba hasta que alguien lo dice, y ese
        alguien tiene la ventana principal minimizada.
        """
        self._boton_detener.setVisible(True)
        self._pista.setText("Detener registra el tiempo")
        self._volcar("TRABAJO INDEFINIDO", transcurrido_seg, estado, tokens.ACENTO)

    def _volcar(self, etiqueta: str, segundos: int, estado: Estado, color: str) -> None:
        self._fase.setText(etiqueta)
        self._fase.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700;")
        self._tiempo.setText(formato.duracion_reloj(segundos))
        self._tiempo.setStyleSheet(f"color: {color}; font-size: 30px; font-weight: 700;")
        self._boton.setText("Pausar" if estado is Estado.CORRIENDO else "Reanudar")
        self.adjustSize()

    def colocar_por_defecto(self) -> None:
        """Esquina inferior derecha, si el usuario no la ha movido todavia."""
        if self._colocada:
            return
        pantalla = self.screen()
        if pantalla is None:
            return
        disponible = pantalla.availableGeometry()
        self.move(
            disponible.right() - self.width() - _MARGEN_PANTALLA,
            disponible.bottom() - self.height() - _MARGEN_PANTALLA,
        )
        self._colocada = True

    def posicion_guardada(self) -> tuple[int, int] | None:
        """Donde quedo, para persistirla entre sesiones."""
        return (self.x(), self.y()) if self._colocada else None

    def restaurar_posicion(self, x: int, y: int) -> None:
        """Recupera la posicion de la sesion anterior, si sigue en pantalla."""
        pantalla = self.screen()
        if pantalla is not None and not pantalla.availableGeometry().contains(x, y):
            # Un segundo monitor desconectado dejaria el reloj fuera de la vista.
            return
        self.move(x, y)
        self._colocada = True

    # -- Arrastre -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if event.button() is Qt.MouseButton.LeftButton:
            self._arrastre = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if self._arrastre is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._arrastre)
            self._colocada = True
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        self._arrastre = None
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        self.restaurar_pedido.emit()
        event.accept()
