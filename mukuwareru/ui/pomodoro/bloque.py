"""Tarjeta de un bloque del timeline.

Lo que hay que entender de un vistazo, en este orden: si es trabajo o descanso,
de que va, cuanto dura y en que punto esta. Nada mas cabe en 176 px.

El estado no se pinta reescribiendo hojas de estilo, sino con la propiedad
dinamica ``estado`` que el QSS consulta (``#BloqueTimeline[estado="activo"]``).
Reescribir el stylesheet de un widget cada segundo obliga a Qt a recalcular el
arbol entero, y el progreso se refresca una vez por segundo.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDrag,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
)

from mukuwareru.nucleo.servicios import Bloque
from mukuwareru.ui import iconos
from mukuwareru.ui.pomodoro.reloj_compacto import COLOR_FASE
from mukuwareru.ui.tema import tokens
from mukuwareru.utilidades import formato

# Formato propio y no ``text/plain``: asi el timeline distingue un bloque suyo de
# un tema arrastrado desde la tira y de cualquier texto que suelte el escritorio.
MIME_BLOQUE = "application/x-mukuwareru-bloque"

ANCHO = 176
ALTO = 96

# Umbral de arrastre: por debajo de esto es un clic, no un movimiento.
_ARRASTRE_MINIMO = 8

_PASO_RUEDA_MIN = 5



def color_de(bloque: Bloque) -> str:
    """Color del bloque: el suyo si lo tiene, o el de su fase."""
    return bloque.color or COLOR_FASE[bloque.tipo]


def segunda_linea(bloque: Bloque) -> str:
    """Que poner bajo el nombre, sin repetirlo.

    Un bloque creado arrastrando un tema se llama igual que su tema, y escribir
    «Ethics / Ethics» en dos lineas no informa de nada. Un descanso tampoco tiene
    tema que ensenar.
    """
    if bloque.materia and bloque.materia != bloque.etiqueta:
        return bloque.materia
    if bloque.materia or not bloque.es_trabajo:
        return ""
    return bloque.nota or "sin tema"


class TarjetaBloque(QFrame):
    """Un tramo del recorrido: tipo, nombre, tema, duracion y progreso."""

    editar_pedido = Signal(int)      # indice
    duplicar_pedido = Signal(int)
    eliminar_pedido = Signal(int)
    ir_pedido = Signal(int)
    duracion_pedida = Signal(int, int)  # indice, minutos

    def __init__(self, bloque: Bloque, indice: int) -> None:
        super().__init__()
        self.setObjectName("BloqueTimeline")
        self.setFixedSize(ANCHO, ALTO)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._bloque = bloque
        self._indice = indice
        self._progreso = 0.0
        self._activo = False
        self._movible = True
        self._origen: QPoint | None = None
        # Huella de lo ya pintado: `aplicar` llega una vez por segundo para todas
        # las tarjetas, y repintar diez que no han cambiado es trabajo tirado.
        self._huella: tuple[object, ...] = ()

        self._construir()
        self.aplicar(bloque, indice)

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        caja = QVBoxLayout(self)
        caja.setContentsMargins(12, 10, 12, 12)
        caja.setSpacing(2)

        cabecera = QHBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        self._pastilla = QLabel()
        self._pastilla.setObjectName("BloquePastilla")
        cabecera.addWidget(self._pastilla, 1)

        self._marca = QLabel()
        self._marca.setObjectName("BloqueMarca")
        cabecera.addWidget(self._marca, 0, Qt.AlignmentFlag.AlignRight)
        caja.addLayout(cabecera)

        self._nombre = QLabel()
        self._nombre.setObjectName("BloqueNombre")
        self._nombre.setWordWrap(False)
        caja.addWidget(self._nombre)

        self._tema = QLabel()
        self._tema.setObjectName("BloqueTema")
        caja.addWidget(self._tema)

        caja.addStretch(1)

        self._duracion = QLabel()
        self._duracion.setObjectName("BloqueDuracion")
        caja.addWidget(self._duracion)

    # -- Datos --------------------------------------------------------------

    @property
    def indice(self) -> int:
        """Posicion del bloque en el recorrido."""
        return self._indice

    @property
    def bloque(self) -> Bloque:
        """Bloque que esta pintando."""
        return self._bloque

    def aplicar(
        self,
        bloque: Bloque,
        indice: int,
        *,
        activo: bool = False,
        progreso: float = 0.0,
        movible: bool = True,
    ) -> None:
        """Vuelca el bloque en la tarjeta y ajusta su estado visual."""
        self._bloque = bloque
        self._indice = indice
        self._activo = activo
        self._progreso = max(0.0, min(1.0, progreso))
        self._movible = movible

        huella = (
            bloque.id, bloque.tipo, bloque.etiqueta, bloque.duracion_min,
            bloque.materia, bloque.color, bloque.icono, bloque.nota,
            bloque.completado, activo, movible,
        )
        if huella == self._huella:
            if activo:
                self.establecer_progreso(self._progreso, self._restante_seg())
            return
        self._huella = huella

        color = color_de(bloque)
        self._pastilla.setText(
            "TRABAJO" if bloque.es_trabajo else bloque.tipo.etiqueta.upper()
        )
        self._pastilla.setStyleSheet(f"color: {color};")

        self._nombre.setText(self._recortado(bloque.etiqueta))
        self._tema.setText(self._recortado(segunda_linea(bloque), 24))
        self._duracion.setText(f"{bloque.duracion_min} min")

        if bloque.completado:
            self._marca.setText("✓")
            self._marca.setStyleSheet(f"color: {tokens.EXITO};")
        elif activo:
            self._marca.setText(formato.duracion_reloj(self._restante_seg()))
            self._marca.setStyleSheet(f"color: {color}; font-weight: 700;")
        else:
            self._marca.setText("")

        if bloque.completado:
            self._marcar("completado")
        else:
            self._marcar("activo" if activo else "pendiente")

        # El icono del bloque se pinta como marca de agua en `paintEvent`, no
        # como widget: un QLabel mas dejaria la tarjeta sin sitio para el nombre.
        self.setToolTip(self._ayuda())
        self.update()

    def establecer_progreso(self, progreso: float, restante_seg: int) -> None:
        """Refresco por segundo del bloque activo: solo la barra y el reloj."""
        self._progreso = max(0.0, min(1.0, progreso))
        self._marca.setText(formato.duracion_reloj(restante_seg))
        self.update()

    def _restante_seg(self) -> int:
        return max(0, int(self._bloque.duracion_seg * (1.0 - self._progreso)))

    def _marcar(self, estado: str) -> None:
        descanso = "1" if self._bloque.tipo.es_descanso else "0"
        if self.property("estado") == estado and self.property("descanso") == descanso:
            return
        self.setProperty("estado", estado)
        self.setProperty("descanso", descanso)
        estilo = self.style()
        estilo.unpolish(self)
        estilo.polish(self)

    def _recortado(self, texto: str, maximo: int = 20) -> str:
        limpio = " ".join(texto.split())
        return limpio if len(limpio) <= maximo else limpio[: maximo - 1] + "…"

    def _ayuda(self) -> str:
        partes = [f"{self._bloque.etiqueta} · {self._bloque.duracion_min} min"]
        if self._bloque.materia:
            partes.append(self._bloque.materia)
        if self._bloque.nota:
            partes.append(self._bloque.nota)
        if not self._movible:
            partes.append("En marcha: para el reloj para moverlo.")
        else:
            partes.append("Clic para editar · arrastra para reordenar · rueda: ±5 min")
        return "\n".join(partes)

    # -- Pintado ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API de Qt)
        """El QSS pinta el marco; aqui va lo que el QSS no sabe hacer."""
        super().paintEvent(event)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(color_de(self._bloque))

        if self._bloque.icono:
            mapa = iconos.pixmap(self._bloque.icono, tokens.TEXTO_TENUE, 20)
            if not mapa.isNull():
                pintor.setOpacity(0.5)
                pintor.drawPixmap(self.width() - 32, self.height() - 30, mapa)
                pintor.setOpacity(1.0)

        # Barra de relleno del bloque en curso, pegada al borde inferior.
        if self._activo and not self._bloque.completado:
            alto = 4.0
            base = QRectF(1, self.height() - alto - 1, self.width() - 2, alto)
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(QColor(tokens.SUPERFICIE_ALTA))
            pintor.drawRoundedRect(base, 2, 2)
            if self._progreso > 0:
                relleno = QRectF(base)
                relleno.setWidth(max(3.0, base.width() * self._progreso))
                pintor.setBrush(color)
                pintor.drawRoundedRect(relleno, 2, 2)

        # Filo de color a la izquierda: distingue trabajo de descanso incluso de
        # refilon, cuando la tarjeta esta medio tapada por el desplazamiento.
        filo = QPen(color, 3)
        filo.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(filo)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        opacidad = 0.35 if self._bloque.completado else 1.0
        pintor.setOpacity(opacidad)
        pintor.drawLine(3, 12, 3, self.height() - 14)
        pintor.end()

    # -- Interaccion --------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if event.button() is Qt.MouseButton.LeftButton:
            self._origen = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if self._origen is None or not self._movible:
            return
        recorrido = (event.position().toPoint() - self._origen).manhattanLength()
        if recorrido < _ARRASTRE_MINIMO:
            return

        datos = QMimeData()
        datos.setData(MIME_BLOQUE, str(self._indice).encode())
        arrastre = QDrag(self)
        arrastre.setMimeData(datos)
        arrastre.setPixmap(self.grab())
        arrastre.setHotSpot(self._origen)
        self._origen = None
        arrastre.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if self._origen is not None and event.button() is Qt.MouseButton.LeftButton:
            self._origen = None
            self.editar_pedido.emit(self._indice)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        """Doble clic: llevar el reloj a este bloque sin pasar por el editor."""
        self._origen = None
        self.ir_pedido.emit(self._indice)
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (API de Qt)
        """Rueda sobre la tarjeta: cambia la duracion sin abrir nada."""
        pasos = event.angleDelta().y() // 120
        if pasos == 0 or self._bloque.completado:
            event.ignore()
            return
        minutos = max(1, self._bloque.duracion_min + pasos * _PASO_RUEDA_MIN)
        self.duracion_pedida.emit(self._indice, minutos)
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802 (API de Qt)
        menu = QMenu(self)
        menu.addAction("Editar…", lambda: self.editar_pedido.emit(self._indice))
        menu.addAction("Empezar por aqui", lambda: self.ir_pedido.emit(self._indice))
        menu.addSeparator()
        duplicar = menu.addAction("Duplicar", lambda: self.duplicar_pedido.emit(self._indice))
        eliminar = menu.addAction("Eliminar", lambda: self.eliminar_pedido.emit(self._indice))
        for accion in (duplicar, eliminar):
            accion.setEnabled(self._movible)
        menu.exec(event.globalPos())
