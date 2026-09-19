"""El timeline: el recorrido de la sesion como una fila de bloques.

Es el elemento principal de la vista Pomodoro. Se lee de izquierda a derecha
—trabajo, descanso, trabajo…— y el personaje dice por donde se va.

Dos ritmos de refresco distintos, y la diferencia importa:

* ``reconstruir`` rehace las tarjetas. Solo cuando cambia la forma del recorrido.
* ``actualizar`` toca la tarjeta activa y mueve al caminante. Una vez por segundo.

Reconstruir cada segundo destruiria y recrearia diez widgets por tic, y el
arrastre en curso se quedaria sin origen a mitad del gesto.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from mukuwareru.nucleo.servicios import RelojPomodoro
from mukuwareru.ui.pomodoro import bloque as tarjetas
from mukuwareru.ui.pomodoro.bloque import MIME_BLOQUE, TarjetaBloque, color_de
from mukuwareru.ui.pomodoro.caminante import Caminante
from mukuwareru.ui.pomodoro.temas import MIME_MATERIA
from mukuwareru.ui.tema import tokens

_MARGEN_SUPERIOR = 48       # sitio para el caminante, encima de las tarjetas
_MARGEN_INFERIOR = 8
_SEPARACION = 10
_ALTO_CARRIL = _MARGEN_SUPERIOR + tarjetas.ALTO + _MARGEN_INFERIOR


class _Riel(QWidget):
    """Fila de tarjetas con el caminante encima y la guia de soltado."""

    mover_pedido = Signal(int, int)          # origen, hueco de destino
    tema_soltado = Signal(int, str, int)     # materia_id, nombre, hueco
    nuevo_pedido = Signal(int)               # hueco
    editar_pedido = Signal(int)
    duplicar_pedido = Signal(int)
    eliminar_pedido = Signal(int)
    ir_pedido = Signal(int)
    duracion_pedida = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("RielTimeline")
        self.setAcceptDrops(True)
        self.setMinimumHeight(_ALTO_CARRIL)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self._tarjetas: list[TarjetaBloque] = []
        self._hueco = -1
        self._indice_pintado = -1
        self._reloj: RelojPomodoro | None = None

        self._caja = QHBoxLayout(self)
        self._caja.setContentsMargins(
            tokens.ESPACIO_PEQUENO, _MARGEN_SUPERIOR, tokens.ESPACIO_PEQUENO,
            _MARGEN_INFERIOR,
        )
        self._caja.setSpacing(_SEPARACION)
        self._caja.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._boton_nuevo = QPushButton("+")
        self._boton_nuevo.setObjectName("BloqueNuevo")
        self._boton_nuevo.setFixedSize(44, tarjetas.ALTO)
        self._boton_nuevo.setToolTip("Anadir un bloque al final del recorrido")
        self._boton_nuevo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_nuevo.clicked.connect(lambda: self.nuevo_pedido.emit(-1))

        self._caminante = Caminante(self)
        self._caminante.raise_()

    # -- Construccion -------------------------------------------------------

    def reconstruir(self, reloj: RelojPomodoro) -> None:
        """Rehace las tarjetas a partir del recorrido."""
        while (elemento := self._caja.takeAt(0)) is not None:
            if (widget := elemento.widget()) is None:
                continue
            widget.setParent(None)
            # El boton «+» se reutiliza; las tarjetas y los conectores, no.
            if widget is not self._boton_nuevo:
                widget.deleteLater()
        self._tarjetas.clear()

        recorrido = reloj.recorrido
        for indice, bloque in enumerate(recorrido.bloques):
            if indice:
                self._caja.addWidget(_conector(), 0, Qt.AlignmentFlag.AlignVCenter)
            tarjeta = TarjetaBloque(bloque, indice)
            tarjeta.editar_pedido.connect(self.editar_pedido.emit)
            tarjeta.duplicar_pedido.connect(self.duplicar_pedido.emit)
            tarjeta.eliminar_pedido.connect(self.eliminar_pedido.emit)
            tarjeta.ir_pedido.connect(self.ir_pedido.emit)
            tarjeta.duracion_pedida.connect(self.duracion_pedida.emit)
            self._caja.addWidget(tarjeta, 0, Qt.AlignmentFlag.AlignTop)
            self._tarjetas.append(tarjeta)

        self._caja.addWidget(self._boton_nuevo, 0, Qt.AlignmentFlag.AlignVCenter)
        self._boton_nuevo.show()
        self._indice_pintado = -1
        self.actualizar_estado(reloj)
        # El caminante se coloca por la geometria de las tarjetas, que Qt aun no
        # ha calculado: se recoloca en cuanto el layout termine.
        QTimer.singleShot(0, self._recolocar)

    def actualizar_estado(self, reloj: RelojPomodoro) -> None:
        """Refresca el estado de las tarjetas y coloca al caminante."""
        self._reloj = reloj
        recorrido = reloj.recorrido
        if len(self._tarjetas) != len(recorrido.bloques):
            return

        activo = recorrido.indice
        for indice, tarjeta in enumerate(self._tarjetas):
            bloque = recorrido.bloques[indice]
            es_activo = indice == activo
            if es_activo:
                tarjeta.aplicar(
                    bloque,
                    indice,
                    activo=True,
                    progreso=reloj.progreso,
                    movible=reloj.movible(indice),
                )
            else:
                tarjeta.aplicar(bloque, indice, movible=reloj.movible(indice))

        self._colocar_caminante(reloj)

    def _recolocar(self) -> None:
        """Vuelve a situar al caminante con la geometria ya calculada."""
        if self._reloj is not None:
            self._colocar_caminante(self._reloj)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (API de Qt)
        super().resizeEvent(event)
        self._recolocar()

    def _colocar_caminante(self, reloj: RelojPomodoro) -> None:
        indice = reloj.recorrido.indice
        if not 0 <= indice < len(self._tarjetas):
            self._caminante.hide()
            return

        tarjeta = self._tarjetas[indice]
        self._caminante.establecer_color(color_de(tarjeta.bloque))
        # Dentro del bloque avanza con el progreso; entre bloques da un paso
        # suave. Se distinguen por si cambio el indice desde la ultima vez.
        salto = indice != self._indice_pintado
        self._indice_pintado = indice
        avance = int((tarjeta.width() - 24) * reloj.progreso)
        self._caminante.ir_a(tarjeta.x() + 12 + avance, tarjeta.y(), suave=salto)
        self._caminante.show()
        self._caminante.raise_()

    def tarjeta_activa(self, indice: int) -> QWidget | None:
        """Tarjeta en esa posicion, para poder traerla a la vista."""
        return self._tarjetas[indice] if 0 <= indice < len(self._tarjetas) else None

    # -- Soltar -------------------------------------------------------------

    def _hueco_en(self, punto: QPoint) -> int:
        """Hueco entre bloques al que corresponde esa posicion del raton."""
        for indice, tarjeta in enumerate(self._tarjetas):
            if punto.x() < tarjeta.x() + tarjeta.width() // 2:
                return indice
        return len(self._tarjetas)

    def _aceptable(self, evento: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> bool:
        formatos = evento.mimeData()
        return formatos.hasFormat(MIME_BLOQUE) or formatos.hasFormat(MIME_MATERIA)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (API de Qt)
        if self._aceptable(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 (API de Qt)
        if not self._aceptable(event):
            return
        hueco = self._hueco_en(event.position().toPoint())
        if hueco != self._hueco:
            self._hueco = hueco
            self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 (API de Qt)
        self._hueco = -1
        self.update()
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (API de Qt)
        if not self._aceptable(event):
            return
        hueco = self._hueco_en(event.position().toPoint())
        self._hueco = -1
        self.update()

        datos = event.mimeData()
        if datos.hasFormat(MIME_BLOQUE):
            try:
                origen = int(bytes(datos.data(MIME_BLOQUE).data()).decode())
            except ValueError:
                return
            self.mover_pedido.emit(origen, hueco)
        else:
            bruto = bytes(datos.data(MIME_MATERIA).data()).decode()
            identificador, _, nombre = bruto.partition("\t")
            try:
                numero = int(identificador)
            except ValueError:
                return
            self.tema_soltado.emit(numero, nombre, hueco)
        event.acceptProposedAction()

    # -- Pintado ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Riel de fondo: la linea que une los bloques y da la idea de recorrido.
        if self._tarjetas:
            primera, ultima = self._tarjetas[0], self._tarjetas[-1]
            centro = primera.y() + primera.height() // 2
            pluma = QPen(QColor(tokens.BORDE), 2)
            pintor.setPen(pluma)
            pintor.drawLine(
                primera.x(), centro, ultima.x() + ultima.width(), centro
            )

        if self._hueco >= 0:
            pintor.setPen(QPen(QColor(tokens.ACENTO), 3))
            x = self._x_del_hueco(self._hueco)
            arriba = _MARGEN_SUPERIOR - 6
            pintor.drawLine(x, arriba, x, arriba + tarjetas.ALTO + 12)
        pintor.end()

    def _x_del_hueco(self, hueco: int) -> int:
        if not self._tarjetas:
            return tokens.ESPACIO_PEQUENO
        if hueco >= len(self._tarjetas):
            ultima = self._tarjetas[-1]
            return ultima.x() + ultima.width() + _SEPARACION // 2
        return self._tarjetas[hueco].x() - _SEPARACION // 2


class Timeline(QScrollArea):
    """Contenedor con desplazamiento horizontal del riel de bloques."""

    mover_pedido = Signal(int, int)
    tema_soltado = Signal(int, str, int)
    nuevo_pedido = Signal(int)
    editar_pedido = Signal(int)
    duplicar_pedido = Signal(int)
    eliminar_pedido = Signal(int)
    ir_pedido = Signal(int)
    duracion_pedida = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Timeline")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setFixedHeight(_ALTO_CARRIL + 14)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._riel = _Riel()
        self.setWidget(self._riel)

        for senal in (
            "mover_pedido", "tema_soltado", "nuevo_pedido", "editar_pedido",
            "duplicar_pedido", "eliminar_pedido", "ir_pedido", "duracion_pedida",
        ):
            getattr(self._riel, senal).connect(getattr(self, senal).emit)

    def reconstruir(self, reloj: RelojPomodoro) -> None:
        """Rehace el riel y deja el bloque en curso a la vista."""
        self._riel.reconstruir(reloj)
        indice = reloj.recorrido.indice
        QTimer.singleShot(0, lambda: self.mostrar_actual(indice))

    def actualizar_estado(self, reloj: RelojPomodoro) -> None:
        """Refresco por segundo: estado de las tarjetas y paso del caminante."""
        self._riel.actualizar_estado(reloj)

    def mostrar_actual(self, indice: int) -> None:
        """Desplaza el riel para que ese bloque quede visible."""
        if (tarjeta := self._riel.tarjeta_activa(indice)) is not None:
            self.ensureWidgetVisible(tarjeta, 120, 0)

    def tarjeta(self, indice: int) -> QWidget | None:
        """Tarjeta de ese bloque, para anclarle el editor."""
        return self._riel.tarjeta_activa(indice)


def _conector() -> QLabel:
    """Flecha entre dos bloques."""
    # Mismo glifo que el boton de contraer la barra lateral, a proposito.
    flecha = QLabel("›")  # noqa: RUF001
    flecha.setObjectName("ConectorTimeline")
    flecha.setFixedWidth(12)
    flecha.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return flecha
