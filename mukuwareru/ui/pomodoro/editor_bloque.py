"""Editor de un bloque: un panel que sale pegado a la tarjeta.

No es un modal a proposito. Cambiar «25 min» por «45 min» tiene que costar dos
clics, no abrir una ventana, aceptar y volver. El panel se ancla bajo el bloque,
aplica cada cambio al vuelo y se cierra con Esc o pulsando fuera.

No toca el recorrido: emite ``cambiado`` con el bloque ya modificado y es la
vista quien decide si eso entra o no.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Materia
from mukuwareru.nucleo.servicios import Bloque, Fase
from mukuwareru.ui.tema import tokens

_ANCHO = 320
_ATAJOS_MIN = (15, 25, 45, 50)
_ICONOS = ("", "libro", "documento", "grafico", "marcador", "nota", "reloj", "panel")


class PanelEdicionBloque(QFrame):
    """Panel flotante con los datos de un bloque."""

    cambiado = Signal(int, object)   # indice, Bloque
    duplicar_pedido = Signal(int)
    eliminar_pedido = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("EditorBloque")
        self.setFixedWidth(_ANCHO)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._indice = -1
        self._bloque: Bloque | None = None
        self._silencio = False
        self._materias: list[Materia] = []

        self._construir()

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        caja = QVBoxLayout(self)
        caja.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        caja.setSpacing(tokens.ESPACIO_PEQUENO)

        self._titulo = QLabel()
        self._titulo.setProperty("fuerte", True)
        caja.addWidget(self._titulo)

        caja.addWidget(self._selector_tipo())

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)
        formulario.setContentsMargins(0, 0, 0, 0)

        self._nombre = QLineEdit()
        self._nombre.setPlaceholderText("Trabajo")
        self._nombre.textEdited.connect(self._emitir)
        formulario.addRow("Nombre", self._nombre)

        self._materia = QComboBox()
        self._materia.currentIndexChanged.connect(self._emitir)
        formulario.addRow("Tema", self._materia)

        self._duracion = QSpinBox()
        self._duracion.setRange(1, 240)
        self._duracion.setSuffix(" min")
        self._duracion.valueChanged.connect(self._emitir)
        formulario.addRow("Duracion", self._duracion)

        self._icono = QComboBox()
        for nombre in _ICONOS:
            self._icono.addItem(nombre or "sin icono", nombre)
        self._icono.currentIndexChanged.connect(self._emitir)
        formulario.addRow("Icono", self._icono)
        caja.addLayout(formulario)

        caja.addWidget(self._atajos_duracion())
        caja.addWidget(self._paleta())

        self._nota = QPlainTextEdit()
        self._nota.setPlaceholderText("Objetivo de este bloque (opcional)")
        self._nota.setFixedHeight(52)
        self._nota.textChanged.connect(self._emitir)
        caja.addWidget(self._nota)

        pie = QHBoxLayout()
        pie.setSpacing(tokens.ESPACIO_PEQUENO)
        duplicar = QPushButton("Duplicar")
        duplicar.setCursor(Qt.CursorShape.PointingHandCursor)
        duplicar.clicked.connect(self._duplicar)
        pie.addWidget(duplicar)

        self._eliminar = QPushButton("Eliminar")
        self._eliminar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eliminar.clicked.connect(self._eliminar_bloque)
        pie.addWidget(self._eliminar)
        pie.addStretch(1)

        cerrar = QPushButton("Listo")
        cerrar.setObjectName("BotonPrimario")
        cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        cerrar.clicked.connect(self.close)
        pie.addWidget(cerrar)
        caja.addLayout(pie)

    def _selector_tipo(self) -> QWidget:
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        self._grupo_tipo = QButtonGroup(self)
        self._grupo_tipo.setExclusive(True)
        self._botones_tipo: dict[Fase, QPushButton] = {}
        for fase in (Fase.TRABAJO, Fase.DESCANSO_CORTO, Fase.DESCANSO_LARGO):
            boton = QPushButton(
                "Trabajo" if fase is Fase.TRABAJO
                else ("Descanso" if fase is Fase.DESCANSO_CORTO else "Largo")
            )
            boton.setObjectName("TipoBloque")
            boton.setCheckable(True)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.clicked.connect(lambda _m=False, f=fase: self._cambiar_tipo(f))
            self._grupo_tipo.addButton(boton)
            self._botones_tipo[fase] = boton
            fila.addWidget(boton, 1)

        contenedor = QWidget()
        contenedor.setObjectName("Transparente")
        contenedor.setLayout(fila)
        return contenedor

    def _atajos_duracion(self) -> QWidget:
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(tokens.ESPACIO_PEQUENO)
        for minutos in _ATAJOS_MIN:
            boton = QPushButton(str(minutos))
            boton.setObjectName("AtajoDuracion")
            boton.setFixedHeight(24)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.clicked.connect(lambda _m=False, v=minutos: self._duracion.setValue(v))
            fila.addWidget(boton, 1)

        contenedor = QWidget()
        contenedor.setObjectName("Transparente")
        contenedor.setLayout(fila)
        return contenedor

    def _paleta(self) -> QWidget:
        """Fila de colores. El «auto» devuelve el color de la fase."""
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        # Apretado a proposito: ocho muestras mas el «auto» tienen que caber en
        # el ancho del panel sin comprimirse hasta recortar el texto.
        fila.setSpacing(4)

        automatico = QPushButton("auto")
        automatico.setObjectName("AtajoDuracion")
        automatico.setFixedHeight(20)
        automatico.setToolTip("Usar el color de la fase")
        automatico.setCursor(Qt.CursorShape.PointingHandCursor)
        automatico.clicked.connect(lambda: self._cambiar_color(None))
        fila.addWidget(automatico)

        for color in tokens.SERIE:
            muestra = QPushButton()
            muestra.setObjectName("MuestraColor")
            muestra.setFixedSize(20, 20)
            muestra.setCursor(Qt.CursorShape.PointingHandCursor)
            muestra.setToolTip(color)
            muestra.setStyleSheet(
                f"background: {color}; border: none; border-radius: 10px;"
            )
            muestra.clicked.connect(lambda _m=False, c=color: self._cambiar_color(c))
            fila.addWidget(muestra)
        fila.addStretch(1)

        contenedor = QWidget()
        contenedor.setObjectName("Transparente")
        contenedor.setLayout(fila)
        return contenedor

    # -- Apertura -----------------------------------------------------------

    def abrir(
        self,
        bloque: Bloque,
        indice: int,
        materias: list[Materia],
        ancla: QWidget,
        *,
        se_puede_borrar: bool = True,
    ) -> None:
        """Vuelca el bloque y muestra el panel debajo de su tarjeta."""
        self._indice = indice
        self._bloque = bloque
        self._materias = materias
        self._eliminar.setEnabled(se_puede_borrar)

        self._silencio = True
        self._titulo.setText(f"Bloque {indice + 1} · {bloque.tipo.etiqueta}")
        self._botones_tipo[bloque.tipo].setChecked(True)
        self._nombre.setText(bloque.nombre)
        self._duracion.setValue(bloque.duracion_min)
        self._nota.setPlainText(bloque.nota)

        self._materia.clear()
        self._materia.addItem("— sin tema —", None)
        for materia in materias:
            self._materia.addItem(materia.nombre, materia.id)
        elegido = self._materia.findData(bloque.materia_id)
        self._materia.setCurrentIndex(max(0, elegido))

        posicion = self._icono.findData(bloque.icono or "")
        self._icono.setCurrentIndex(max(0, posicion))
        self._silencio = False

        esquina = ancla.mapToGlobal(QPoint(0, ancla.height() + 6))
        self.move(esquina)
        self.show()
        self._nombre.setFocus()

    # -- Cambios ------------------------------------------------------------

    def _cambiar_tipo(self, fase: Fase) -> None:
        if self._bloque is None:
            return
        self._titulo.setText(f"Bloque {self._indice + 1} · {fase.etiqueta}")
        self._emitir()

    def _cambiar_color(self, color: str | None) -> None:
        if self._bloque is None:
            return
        self._bloque = replace(self._bloque, color=color)
        self._emitir()

    def _tipo_elegido(self) -> Fase:
        for fase, boton in self._botones_tipo.items():
            if boton.isChecked():
                return fase
        return Fase.TRABAJO

    def _emitir(self) -> None:
        """Manda el bloque ya editado. El recorrido lo aplica la vista."""
        if self._silencio or self._bloque is None:
            return

        materia_id = self._materia.currentData()
        nombre_materia = ""
        if materia_id is not None:
            nombre_materia = next(
                (m.nombre for m in self._materias if m.id == materia_id), ""
            )

        editado = replace(
            self._bloque,
            tipo=self._tipo_elegido(),
            nombre=self._nombre.text().strip(),
            duracion_min=self._duracion.value(),
            materia_id=materia_id,
            materia=nombre_materia,
            icono=self._icono.currentData() or None,
            nota=self._nota.toPlainText().strip(),
        )
        self._bloque = editado
        self.cambiado.emit(self._indice, editado)

    def _duplicar(self) -> None:
        indice = self._indice
        self.close()
        self.duplicar_pedido.emit(indice)

    def _eliminar_bloque(self) -> None:
        indice = self._indice
        self.close()
        self.eliminar_pedido.emit(indice)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (API de Qt)
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
