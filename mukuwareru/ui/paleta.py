"""Paleta de busqueda (Ctrl+K): un campo, todo el proyecto.

Sin esto hay que recordar en que seccion vive cada cosa antes de poder buscarla.
Con esto se escribe «ethic» y sale la nota, el resaltado, la materia, el PDF y
la fecha del examen, y se salta al sitio exacto con Enter.

No conoce las vistas: emite ``elegido`` con el ``Resultado`` y es la ventana
principal quien navega.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.servicios import Familia, Resultado
from mukuwareru.ui.tema import tokens

_COLOR_FAMILIA = {
    Familia.NOTA: tokens.EXITO,
    Familia.ANOTACION: tokens.AVISO,
    Familia.MATERIA: tokens.INFO,
    Familia.MODULO: tokens.INFO,
    Familia.DOCUMENTO: tokens.NARANJA,
    Familia.HITO: tokens.ACENTO,
}


class Paleta(QDialog):
    """Buscador global flotante sobre la ventana."""

    elegido = Signal(object)  # Resultado

    def __init__(self, contexto: Contexto, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.contexto = contexto
        self.setWindowTitle("Buscar")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(560)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        self._campo = QLineEdit()
        self._campo.setPlaceholderText(
            "Buscar notas, resaltados, materias, modulos, PDFs y fechas…"
        )
        self._campo.setClearButtonEnabled(True)
        self._campo.textChanged.connect(self._buscar)
        # Las flechas mueven la lista aunque el foco siga en el campo: bajar la
        # mano al raton para elegir anularia la ventaja de un atajo de teclado.
        self._campo.installEventFilter(self)
        columna.addWidget(self._campo)

        self._lista = QListWidget()
        self._lista.setWordWrap(True)
        self._lista.setMinimumHeight(320)
        self._lista.itemActivated.connect(self._elegir)
        self._lista.itemClicked.connect(self._elegir)
        columna.addWidget(self._lista, 1)

        self._pie = QLabel("Escribe para buscar. Enter abre, Esc cierra.")
        self._pie.setObjectName("TextoTenue")
        columna.addWidget(self._pie)

        self.setStyleSheet(
            f"QDialog {{ background-color: {tokens.SUPERFICIE};"
            f" border: 1px solid {tokens.BORDE}; border-radius: {tokens.RADIO}px; }}"
        )

    # -- Busqueda -----------------------------------------------------------

    def _buscar(self, texto: str) -> None:
        self._lista.clear()
        proyecto = self.contexto.proyecto
        if proyecto is None:
            self._pie.setText("Sin proyecto seleccionado.")
            return

        resultados = self.contexto.busqueda.buscar(proyecto.id, texto)
        if not texto.strip():
            self._pie.setText("Escribe para buscar. Enter abre, Esc cierra.")
            return
        if not resultados:
            self._pie.setText(f"Nada coincide con «{texto.strip()}».")
            return

        familia_previa: Familia | None = None
        for resultado in resultados:
            if resultado.familia is not familia_previa:
                self._lista.addItem(_separador(resultado.familia))
                familia_previa = resultado.familia
            self._lista.addItem(_elemento(resultado))

        self._pie.setText(f"{len(resultados)} coincidencias")
        self._elegir_primera()

    def _elegir_primera(self) -> None:
        """Deja marcado el primer resultado real, saltando los separadores."""
        for fila in range(self._lista.count()):
            if self._lista.item(fila).data(Qt.ItemDataRole.UserRole) is not None:
                self._lista.setCurrentRow(fila)
                return

    def _elegir(self, elemento: QListWidgetItem | None = None) -> None:
        elemento = elemento or self._lista.currentItem()
        if elemento is None:
            return
        resultado = elemento.data(Qt.ItemDataRole.UserRole)
        if isinstance(resultado, Resultado):
            self.accept()
            self.elegido.emit(resultado)

    # -- Teclado -------------------------------------------------------------

    def eventFilter(self, objeto: object, evento: object) -> bool:  # noqa: N802
        """Redirige las flechas y el Enter del campo a la lista."""
        if isinstance(evento, QKeyEvent) and evento.type() is QKeyEvent.Type.KeyPress:
            tecla = evento.key()
            if tecla in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._mover(1 if tecla == Qt.Key.Key_Down else -1)
                return True
            if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._elegir()
                return True
        return super().eventFilter(objeto, evento)  # type: ignore[arg-type]

    def _mover(self, paso: int) -> None:
        """Avanza por la lista saltando las cabeceras de familia."""
        fila = self._lista.currentRow() + paso
        while 0 <= fila < self._lista.count():
            if self._lista.item(fila).data(Qt.ItemDataRole.UserRole) is not None:
                self._lista.setCurrentRow(fila)
                return
            fila += paso

    def abrir(self) -> None:
        """Muestra la paleta vacia y con el foco puesto."""
        self._campo.clear()
        self._lista.clear()
        self._pie.setText("Escribe para buscar. Enter abre, Esc cierra.")
        self._campo.setFocus()
        self.exec()


def _separador(familia: Familia) -> QListWidgetItem:
    """Cabecera de grupo. Sin dato asociado: no es elegible."""
    elemento = QListWidgetItem(familia.etiqueta.upper())
    elemento.setFlags(Qt.ItemFlag.NoItemFlags)
    elemento.setForeground(_color(familia))
    return elemento


def _elemento(resultado: Resultado) -> QListWidgetItem:
    elemento = QListWidgetItem(f"{resultado.titulo}\n{resultado.subtitulo}")
    elemento.setData(Qt.ItemDataRole.UserRole, resultado)
    elemento.setData(Qt.ItemDataRole.DecorationRole, _color(resultado.familia))
    return elemento


def _color(familia: Familia) -> QColor:
    return QColor(_COLOR_FAMILIA.get(familia, tokens.TEXTO_SUAVE))
