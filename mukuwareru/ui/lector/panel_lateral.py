"""Panel lateral del lector: miniaturas, indice y busqueda.

El indice y la busqueda se apoyan en los modelos que Qt ya proporciona
(``QPdfBookmarkModel`` y ``QPdfSearchModel``). Solo las miniaturas son propias,
porque hay que rasterizarlas de forma perezosa.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument, QPdfSearchModel
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.ui.lector.panel_notas import PanelNotas
from mukuwareru.ui.tema import tokens

_ANCHO_MINIATURA = 116
_MARGEN_CELDA = 10       # aire alrededor de la miniatura dentro de su celda
_ALTO_ETIQUETA = 20      # sitio para el numero de pagina, debajo del papel
_PROPORCION_A4 = 1.414   # alto/ancho, por si el documento no dice otra cosa
_POR_TANDA = 4           # miniaturas rasterizadas en cada vuelta del temporizador
_RETARDO_BUSQUEDA_MS = 300

# `QModelIndex.data()` exige un entero. Ojo: los dos enums de Qt no son iguales.
# `QPdfBookmarkModel.Role` es un IntEnum y admite `int()`, pero
# `QPdfSearchModel.Role` es un Enum normal y hay que leer su `.value`.
_ROL_PAGINA = QPdfSearchModel.Role.Page.value
_ROL_ANTES = QPdfSearchModel.Role.ContextBefore.value
_ROL_DESPUES = QPdfSearchModel.Role.ContextAfter.value


def _icono_sin_tinte(lienzo: QPixmap) -> QIcon:
    """Icono que se ve igual seleccionado que sin seleccionar.

    Qt genera solas las variantes ``Selected`` y ``Active`` de un icono tinendolo
    con el color de resalte. En una miniatura eso pinta la pagina entera de rojo
    en cuanto se selecciona. Se registran las tres variantes a mano con el mismo
    mapa de pixeles para que no invente ninguna.
    """
    icono = QIcon()
    for modo in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
        icono.addPixmap(lienzo, modo)
    return icono


class PanelLateral(QTabWidget):
    """Pestanas de navegacion dentro del documento."""

    pagina_pedida = Signal(int)
    resultados_cambiados = Signal(object)  # QPdfSearchModel | None
    nota_pedida = Signal(int)              # id de una nota suelta relacionada

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._documento: QPdfDocument | None = None
        self.setDocumentMode(True)

        self._miniaturas = _Miniaturas()
        self._miniaturas.pagina_pedida.connect(self.pagina_pedida.emit)
        self.addTab(self._miniaturas, "Miniaturas")

        self._indice = _Indice()
        self._indice.pagina_pedida.connect(self.pagina_pedida.emit)
        self.addTab(self._indice, "Indice")

        self._busqueda = _Busqueda()
        self._busqueda.pagina_pedida.connect(self.pagina_pedida.emit)
        self._busqueda.resultados_cambiados.connect(self.resultados_cambiados.emit)
        self.addTab(self._busqueda, "Buscar")

        # Una sola pestana para todo lo escrito sobre el PDF: lo anclado dentro
        # y las notas de cuaderno ligadas a el. Separarlas obligaba a mirar en
        # dos sitios para la misma pregunta.
        self.notas = PanelNotas()
        self.notas.pagina_pedida.connect(self.pagina_pedida.emit)
        self.notas.abrir_nota_pedida.connect(self.nota_pedida.emit)
        self.addTab(self.notas, "Notas")

    def establecer_documento(self, documento: QPdfDocument) -> None:
        """Reinicia las tres pestanas con el documento recien abierto."""
        self._documento = documento
        self._miniaturas.establecer_documento(documento)
        self._indice.establecer_documento(documento)
        self._busqueda.establecer_documento(documento)

    def marcar_pagina(self, indice: int) -> None:
        """Sincroniza la miniatura y la nota resaltadas con la pagina visible."""
        self._miniaturas.marcar(indice)
        self.notas.marcar_pagina(indice)

    def enfocar_busqueda(self) -> None:
        """Lleva el foco al campo de busqueda."""
        self.setCurrentWidget(self._busqueda)
        self._busqueda.enfocar()

    def mostrar_notas(self) -> None:
        """Trae al frente la pestana de anotaciones."""
        self.setCurrentWidget(self.notas)


class _Miniaturas(QListWidget):
    """Lista de paginas en miniatura, rasterizadas poco a poco.

    Dos detalles que no son opcionales:

    * ``QPdfDocument.render`` **no pinta el fondo del papel**: devuelve la tinta
      sobre pixeles transparentes. Compuesta directamente sobre el panel oscuro,
      una pagina blanca se ve negra. Cada miniatura se dibuja sobre blanco, igual
      que hace el lienzo del lector.
    * La celda se dimensiona con la proporcion real del documento. Con un alto
      fijo, un PDF apaisado deja media celda vacia entre pagina y pagina.
    """

    pagina_pedida = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Miniaturas")
        self._documento: QPdfDocument | None = None
        self._pendientes: list[int] = []
        self._alto = int(_ANCHO_MINIATURA * _PROPORCION_A4)

        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setWordWrap(False)
        self.itemClicked.connect(
            lambda elemento: self.pagina_pedida.emit(elemento.data(Qt.ItemDataRole.UserRole))
        )

        # Rasterizar 500 miniaturas de golpe congelaria la ventana; se generan
        # en tandas pequenas para que la interfaz siga respondiendo.
        self._temporizador = QTimer(self)
        self._temporizador.setInterval(16)
        self._temporizador.timeout.connect(self._generar_tanda)

    def establecer_documento(self, documento: QPdfDocument) -> None:
        """Crea un elemento por pagina y encola su rasterizado."""
        self._temporizador.stop()
        self._documento = documento
        self.clear()

        self._alto = self._alto_de_celda(documento)
        self.setIconSize(QSize(_ANCHO_MINIATURA, self._alto))
        self.setGridSize(
            QSize(
                _ANCHO_MINIATURA + 2 * _MARGEN_CELDA,
                self._alto + _MARGEN_CELDA + _ALTO_ETIQUETA,
            )
        )

        vacia = _icono_sin_tinte(self._papel_vacio())
        for numero in range(documento.pageCount()):
            elemento = QListWidgetItem(str(numero + 1))
            elemento.setData(Qt.ItemDataRole.UserRole, numero)
            elemento.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            elemento.setIcon(vacia)
            self.addItem(elemento)

        self._pendientes = list(range(documento.pageCount()))
        if self._pendientes:
            self._temporizador.start()

    def marcar(self, indice: int) -> None:
        """Selecciona la miniatura correspondiente sin emitir senales."""
        if 0 <= indice < self.count() and self.currentRow() != indice:
            self.blockSignals(True)
            self.setCurrentRow(indice)
            self.blockSignals(False)
            self.scrollToItem(self.item(indice))

    # -- Rasterizado --------------------------------------------------------

    def _alto_de_celda(self, documento: QPdfDocument) -> int:
        """Alto de celda segun la proporcion de la primera pagina."""
        if documento.pageCount() > 0:
            tamano = documento.pagePointSize(0)
            if tamano.width() > 0 and tamano.height() > 0:
                return int(_ANCHO_MINIATURA * tamano.height() / tamano.width())
        return int(_ANCHO_MINIATURA * _PROPORCION_A4)

    def _papel_vacio(self) -> QPixmap:
        """Hoja en blanco que reserva el hueco mientras llega el rasterizado."""
        lienzo = QPixmap(_ANCHO_MINIATURA, self._alto)
        lienzo.fill(QColor(tokens.SUPERFICIE_ALTA))
        return lienzo

    def _generar_tanda(self) -> None:
        if self._documento is None or not self._pendientes:
            self._temporizador.stop()
            return

        dpr = self.devicePixelRatioF()
        for _ in range(_POR_TANDA):
            if not self._pendientes:
                self._temporizador.stop()
                return
            numero = self._pendientes.pop(0)
            if (elemento := self.item(numero)) is None:
                continue
            if (lienzo := self._rasterizar(numero, dpr)) is not None:
                elemento.setIcon(_icono_sin_tinte(lienzo))

    def _rasterizar(self, numero: int, dpr: float) -> QPixmap | None:
        """Dibuja la pagina sobre papel blanco, ajustada a la celda."""
        if self._documento is None:
            return None
        tamano_pdf = self._documento.pagePointSize(numero)
        if tamano_pdf.width() <= 0 or tamano_pdf.height() <= 0:
            return None

        proporcion = tamano_pdf.height() / tamano_pdf.width()
        if _ANCHO_MINIATURA * proporcion <= self._alto:
            ancho, alto = _ANCHO_MINIATURA, max(1, round(_ANCHO_MINIATURA * proporcion))
        else:
            ancho, alto = max(1, round(self._alto / proporcion)), self._alto

        # Se rasteriza a la densidad real de la pantalla: en un portatil a 150 %
        # una miniatura de 116 px logicos se veria borrosa.
        pixeles = QSize(round(ancho * dpr), round(alto * dpr))
        imagen: QImage = self._documento.render(numero, pixeles)
        if imagen.isNull():
            return None

        lienzo = QPixmap(pixeles)
        lienzo.setDevicePixelRatio(dpr)
        lienzo.fill(QColor("#FFFFFF"))
        pintor = QPainter(lienzo)
        pintor.drawImage(0, 0, imagen)
        pintor.end()
        return lienzo


class _Indice(QTreeView):
    """Tabla de contenido del PDF, si el documento la trae."""

    pagina_pedida = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._modelo = QPdfBookmarkModel(self)
        self.setModel(self._modelo)
        self.setHeaderHidden(True)
        self.clicked.connect(self._al_pulsar)

    def establecer_documento(self, documento: QPdfDocument) -> None:
        """Enlaza el modelo de marcadores de Qt con el documento."""
        self._modelo.setDocument(documento)
        self.expandToDepth(0)

    def _al_pulsar(self, indice: QModelIndex) -> None:
        # `data()` exige un entero: pasarle el enum directamente es un TypeError.
        pagina = indice.data(int(QPdfBookmarkModel.Role.Page))
        if pagina is not None:
            self.pagina_pedida.emit(int(pagina))


class _Busqueda(QWidget):
    """Campo de busqueda y lista de coincidencias con su contexto."""

    pagina_pedida = Signal(int)
    resultados_cambiados = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Transparente")
        self._modelo = QPdfSearchModel(self)
        # El modelo busca pagina a pagina y avisa por varias vias distintas;
        # `countChanged` por si solo se queda corto en el ultimo lote.
        for senal in (
            self._modelo.countChanged,
            self._modelo.rowsInserted,
            self._modelo.modelReset,
        ):
            senal.connect(self._programar_refresco)

        # Los avisos llegan en rafaga; reconstruir la lista en cada uno haria
        # parpadear la interfaz en un PDF grande.
        self._refresco = QTimer(self)
        self._refresco.setSingleShot(True)
        self._refresco.setInterval(80)
        self._refresco.timeout.connect(self._al_cambiar_resultados)

        self._campo = QLineEdit()
        self._campo.setPlaceholderText("Buscar en el documento…")
        self._campo.setClearButtonEnabled(True)
        self._campo.textChanged.connect(self._al_escribir)

        # Buscar en cada pulsacion recorreria el PDF entero letra a letra.
        self._rebote = QTimer(self)
        self._rebote.setSingleShot(True)
        self._rebote.setInterval(_RETARDO_BUSQUEDA_MS)
        self._rebote.timeout.connect(self._buscar)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoTenue")

        self._lista = QListWidget()
        self._lista.itemClicked.connect(
            lambda elemento: self.pagina_pedida.emit(elemento.data(Qt.ItemDataRole.UserRole))
        )

        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, tokens.ESPACIO_PEQUENO, 0, 0)
        caja.setSpacing(tokens.ESPACIO_PEQUENO)
        caja.addWidget(self._campo)
        caja.addWidget(self._resumen)
        caja.addWidget(self._lista, 1)

    @property
    def modelo(self) -> QPdfSearchModel:
        """Modelo de busqueda, para que el lector pinte los hallazgos."""
        return self._modelo

    def establecer_documento(self, documento: QPdfDocument) -> None:
        """Reinicia la busqueda con el documento recien abierto."""
        self._refresco.stop()
        self._modelo.setDocument(documento)
        self._campo.clear()
        self._lista.clear()
        self._resumen.clear()

    def enfocar(self) -> None:
        """Lleva el foco al campo y selecciona lo que hubiera escrito."""
        self._campo.setFocus()
        self._campo.selectAll()

    def _al_escribir(self, _texto: str) -> None:
        self._rebote.start()

    def _buscar(self) -> None:
        self._modelo.setSearchString(self._campo.text().strip())

    def _programar_refresco(self, *_argumentos: object) -> None:
        self._refresco.start()

    def _al_cambiar_resultados(self) -> None:
        self._lista.clear()
        total = self._modelo.rowCount(QModelIndex())

        if not self._campo.text().strip():
            self._resumen.clear()
            self.resultados_cambiados.emit(None)
            return

        self._resumen.setText(
            f"{total} coincidencia" + ("s" if total != 1 else "") if total else "Sin resultados"
        )
        for fila in range(total):
            indice = self._modelo.index(fila, 0)
            pagina = int(indice.data(_ROL_PAGINA) or 0)
            antes = str(indice.data(_ROL_ANTES) or "")
            despues = str(indice.data(_ROL_DESPUES) or "")
            elemento = QListWidgetItem(f"p. {pagina + 1}   …{antes.strip()}{despues.strip()}…")
            elemento.setData(Qt.ItemDataRole.UserRole, pagina)
            self._lista.addItem(elemento)

        self.resultados_cambiados.emit(self._modelo)
