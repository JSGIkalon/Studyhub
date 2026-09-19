"""Tarjeta de un PDF en la biblioteca."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from mukuwareru.nucleo.modelos import Documento
from mukuwareru.ui import iconos
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets.contenedor import contenedor
from mukuwareru.ui.widgets.tarjeta import Tarjeta
from mukuwareru.utilidades import formato


class TarjetaDocumento(Tarjeta):
    """Nombre, metadatos y avance de lectura. Se abre con doble clic."""

    abrir = Signal(object)  # Documento

    def __init__(
        self, documento: Documento, notas: int = 0, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent=parent)
        self.documento = documento
        self._notas = notas
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"{documento.ruta_relativa}\n\nDoble clic para abrir")
        self._construir()

    def _construir(self) -> None:
        cabecera = QHBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        simbolo = QLabel()
        simbolo.setPixmap(iconos.pixmap("documento", tokens.ACENTO, 20))
        simbolo.setFixedWidth(24)
        cabecera.addWidget(simbolo, 0, Qt.AlignmentFlag.AlignTop)

        nombre = QLabel(self.documento.nombre)
        nombre.setStyleSheet("font-weight: 600;")
        nombre.setWordWrap(True)
        cabecera.addWidget(nombre, 1)

        # Que un PDF tenga notas ligadas se ve desde la rejilla: es la senal de
        # que ya se trabajo sobre el, que el porcentaje leido no distingue.
        if self._notas:
            insignia = QLabel(f"{self._notas} ▪")
            insignia.setToolTip(f"{self._notas} notas ligadas a este PDF")
            insignia.setStyleSheet(f"color: {tokens.INFO}; font-weight: 600;")
            cabecera.addWidget(insignia, 0, Qt.AlignmentFlag.AlignTop)

        self.contenido.addWidget(contenedor(cabecera))

        detalle = QLabel(self._detalle())
        detalle.setObjectName("TextoTenue")
        self.contenido.addWidget(detalle)

        self.contenido.addWidget(_BarraLectura(self.documento))

    def _detalle(self) -> str:
        partes = [formato.tamano(self.documento.bytes)]
        if self.documento.paginas:
            partes.append(f"{self.documento.paginas} paginas")
        partes.append(_texto_apertura(self.documento.abierto_en))
        if "/" in self.documento.ruta_relativa:
            partes.append(self.documento.ruta_relativa.rsplit("/", 1)[0])
        return "  ·  ".join(partes)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        self.abrir.emit(self.documento)
        super().mouseDoubleClickEvent(event)


class _BarraLectura(QWidget):
    """Franja fina con el avance de lectura del documento."""

    def __init__(self, documento: Documento) -> None:
        super().__init__()
        self.setObjectName("Transparente")
        caja = QHBoxLayout(self)
        caja.setContentsMargins(0, 2, 0, 0)
        caja.setSpacing(tokens.ESPACIO_PEQUENO)

        porcentaje = _avance(documento)
        pista = QWidget()
        pista.setFixedHeight(4)
        pista.setStyleSheet(
            f"background-color: {tokens.SUPERFICIE_ALTA}; border-radius: 2px;"
        )
        relleno = QWidget(pista)
        relleno.setStyleSheet(f"background-color: {tokens.EXITO}; border-radius: 2px;")
        relleno.setFixedHeight(4)
        pista.resizeEvent = lambda evento: relleno.setFixedWidth(  # type: ignore[method-assign]
            round(evento.size().width() * porcentaje / 100)
        )
        caja.addWidget(pista, 1)

        etiqueta = QLabel(f"{porcentaje} %" if documento.paginas else "sin abrir")
        etiqueta.setObjectName("TextoTenue")
        etiqueta.setFixedWidth(56)
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        caja.addWidget(etiqueta)


def _avance(documento: Documento) -> int:
    """Porcentaje leido segun la ultima pagina visitada."""
    if not documento.paginas:
        return 0
    return formato.porcentaje(documento.pagina_actual + 1, documento.paginas)


def _texto_apertura(momento: datetime | None) -> str:
    if momento is None:
        return "sin abrir"
    dias = (date.today() - momento.date()).days
    if dias == 0:
        return f"hoy {momento:%H:%M}"
    if dias == 1:
        return "ayer"
    return formato.fecha_corta(momento.date())
