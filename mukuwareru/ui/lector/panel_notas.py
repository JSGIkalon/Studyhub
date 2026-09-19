"""Pestana «Notas» del lector: todo lo escrito sobre este PDF, en una lista.

**Una sola lista, a proposito.** Antes habia dos pestanas —las anotaciones
ancladas por un lado y las notas sueltas relacionadas por otro— y obligaban a
mirar en dos sitios para la misma pregunta: «¿que tengo escrito sobre esto?».
Ahora conviven ordenadas por pagina, y cada fila dice de que tipo es y donde
vive.

**Todo lo que se escribe va a un cuaderno.** Ya no se crean notas ni marcadores
anclados al PDF; lo unico que se pone sobre la pagina es un resaltado, que no es
escribir sino marcar. Las anotaciones antiguas de otros tipos se siguen listando
y editando: lo que desaparece es el camino para crear nuevas.

Desde aqui se puede, sin salir del PDF: crear una nota de cuaderno ligada a la
pagina que se esta leyendo, relacionar una nota que ya existe, abrir la nota
completa en la vista Notas y saltar a la pagina de cualquier anotacion.

No toca la base de datos: emite senales y es ``VistaLector`` quien persiste.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Anotacion, TipoAnotacion
from mukuwareru.nucleo.repositorios import NotaListada
from mukuwareru.ui.tema import tokens
from mukuwareru.utilidades.texto import a_texto_plano, primera_linea

_ETIQUETAS = {
    TipoAnotacion.MARCADOR: ("Marcador", tokens.ACENTO),
    TipoAnotacion.NOTA: ("Nota", tokens.INFO),
    TipoAnotacion.RESALTADO: ("Resaltado", tokens.AVISO),
}
_COLOR_SUELTA = tokens.EXITO
_MAXIMO_RESUMEN = 110


@dataclass(frozen=True, slots=True)
class _Fila:
    """Una entrada de la lista: o una anotacion anclada, o una nota suelta."""

    pagina: int | None
    anotacion: Anotacion | None = None
    nota: NotaListada | None = None


def _resumen(anotacion: Anotacion) -> str:
    """Linea de contenido: el comentario manda sobre el texto citado."""
    for campo in (anotacion.comentario, anotacion.texto_seleccionado):
        bruto = (campo or "").strip()
        if not bruto:
            continue
        if texto := a_texto_plano(bruto).strip():
            return texto if len(texto) <= _MAXIMO_RESUMEN else texto[:_MAXIMO_RESUMEN] + "…"
    return "Sin comentario"


class PanelNotas(QWidget):
    """Anotaciones del documento y notas sueltas ligadas a el, juntas."""

    pagina_pedida = Signal(int)
    editar_pedido = Signal(object)  # Anotacion
    eliminar_pedido = Signal(object)
    nota_suelta_pedida = Signal()   # nota nueva en un cuaderno, ligada a la pagina
    vincular_pedido = Signal()      # relacionar una nota que ya existe
    abrir_nota_pedida = Signal(int)
    desvincular_pedido = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Transparente")

        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, tokens.ESPACIO_PEQUENO, 0, 0)
        caja.setSpacing(tokens.ESPACIO_PEQUENO)

        cuaderno = QHBoxLayout()
        cuaderno.setSpacing(tokens.ESPACIO_PEQUENO)
        nueva = QPushButton("Nota en cuaderno")
        nueva.setToolTip(
            "Crea una nota en un cuaderno, ya relacionada con esta pagina (Ctrl+M)."
        )
        nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        nueva.clicked.connect(self.nota_suelta_pedida.emit)
        cuaderno.addWidget(nueva, 1)

        vincular = QPushButton("Relacionar…")
        vincular.setToolTip("Liga una nota que ya existe con esta pagina.")
        vincular.setCursor(Qt.CursorShape.PointingHandCursor)
        vincular.clicked.connect(self.vincular_pedido.emit)
        cuaderno.addWidget(vincular, 1)
        caja.addLayout(cuaderno)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoTenue")
        self._resumen.setWordWrap(True)
        caja.addWidget(self._resumen)

        self._lista = QListWidget()
        self._lista.setWordWrap(True)
        self._lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._lista.customContextMenuRequested.connect(self._menu)
        self._lista.itemClicked.connect(self._al_pulsar)
        self._lista.itemDoubleClicked.connect(self._al_pulsar_dos_veces)
        caja.addWidget(self._lista, 1)

    # -- Datos --------------------------------------------------------------

    def establecer(
        self,
        anotaciones: list[Anotacion],
        notas: list[NotaListada] | None = None,
        documento_id: int | None = None,
    ) -> None:
        """Vuelca todo lo escrito sobre el documento, ordenado por pagina.

        Las notas sueltas ligadas al documento entero no tienen pagina y van al
        final: valen para cualquiera, asi que no pertenecen a ninguna.
        """
        notas = notas or []
        self._lista.clear()

        filas = [_Fila(pagina=a.pagina, anotacion=a) for a in anotaciones]
        filas += [
            _Fila(pagina=_pagina_de(listada, documento_id), nota=listada)
            for listada in notas
        ]
        # `None` al final: sin clave numerica no se pueden ordenar juntos.
        filas.sort(key=lambda f: (f.pagina is None, f.pagina or 0))

        if not filas:
            self._resumen.setText(
                "Nada escrito sobre este PDF todavia. Selecciona texto y usa el "
                "boton derecho, o crea una nota de cuaderno ligada a esta pagina."
            )
            return

        self._resumen.setText(
            f"{len(anotaciones)} resaltados  ·  {len(notas)} notas de cuaderno"
        )
        for fila in filas:
            self._lista.addItem(_elemento(fila))

    def marcar_pagina(self, indice: int) -> None:
        """Resalta la primera entrada de la pagina visible, si la hay."""
        for numero in range(self._lista.count()):
            elemento = self._lista.item(numero)
            fila = elemento.data(Qt.ItemDataRole.UserRole)
            if isinstance(fila, _Fila) and fila.pagina == indice:
                self._lista.setCurrentItem(elemento)
                return
        self._lista.clearSelection()

    # -- Interaccion --------------------------------------------------------

    def _fila_de(self, elemento: QListWidgetItem | None) -> _Fila | None:
        if elemento is None:
            return None
        fila = elemento.data(Qt.ItemDataRole.UserRole)
        return fila if isinstance(fila, _Fila) else None

    def _al_pulsar(self, elemento: QListWidgetItem) -> None:
        fila = self._fila_de(elemento)
        if fila is not None and fila.pagina is not None:
            self.pagina_pedida.emit(fila.pagina)

    def _al_pulsar_dos_veces(self, elemento: QListWidgetItem) -> None:
        fila = self._fila_de(elemento)
        if fila is None:
            return
        if fila.anotacion is not None:
            self.editar_pedido.emit(fila.anotacion)
        elif fila.nota is not None:
            self.abrir_nota_pedida.emit(fila.nota.nota.id)

    def _menu(self, posicion: QPoint) -> None:
        # El clic derecho no selecciona el elemento (solo el izquierdo lo hace),
        # asi que hay que mirar que hay bajo el cursor, no `currentItem()`.
        elemento = self._lista.itemAt(posicion)
        fila = self._fila_de(elemento)
        if fila is None or elemento is None:
            return
        self._lista.setCurrentItem(elemento)

        menu = QMenu(self)
        if fila.pagina is not None:
            menu.addAction(
                f"Ir a la pagina {fila.pagina + 1}",
                lambda: self.pagina_pedida.emit(fila.pagina),
            )
        if fila.anotacion is not None:
            menu.addAction(
                "Editar comentario…", lambda: self.editar_pedido.emit(fila.anotacion)
            )
            menu.addSeparator()
            menu.addAction("Eliminar", lambda: self.eliminar_pedido.emit(fila.anotacion))
        elif fila.nota is not None:
            identificador = fila.nota.nota.id
            menu.addAction(
                "Abrir en Notas", lambda: self.abrir_nota_pedida.emit(identificador)
            )
            menu.addSeparator()
            menu.addAction(
                "Quitar la relacion con este PDF",
                lambda: self.desvincular_pedido.emit(identificador),
            )
        menu.exec(self._lista.viewport().mapToGlobal(posicion))


def _pagina_de(listada: NotaListada, documento_id: int | None) -> int | None:
    """Pagina a la que apunta la nota **en este documento**.

    Se filtra por documento porque una nota puede estar ligada a varios PDFs, y
    la pagina de otro no dice nada sobre el que se esta leyendo.
    """
    for vinculo in listada.nota.vinculos:
        if vinculo.documento_id is None or vinculo.pagina is None:
            continue
        if documento_id is None or vinculo.documento_id == documento_id:
            return vinculo.pagina
    return None


def _elemento(fila: _Fila) -> QListWidgetItem:
    """Una entrada de la lista, con su ubicacion y su color por tipo."""
    ubicacion = "documento entero" if fila.pagina is None else f"p. {fila.pagina + 1}"

    if fila.anotacion is not None:
        etiqueta, color = _ETIQUETAS[fila.anotacion.tipo]
        texto = f"{ubicacion}  ·  {etiqueta}\n{_resumen(fila.anotacion)}"
    else:
        assert fila.nota is not None
        nota = fila.nota.nota
        titulo = nota.titulo.strip() or primera_linea(nota.cuerpo_plano) or "Nota"
        # La ruta del cuaderno va en la propia fila: sin ella, una nota suelta y
        # una anclada se confunden, y hay que abrirla para saber de donde sale.
        texto = (
            f"{ubicacion}  ·  {fila.nota.cuaderno} -> {fila.nota.seccion}\n"
            f"{titulo}"
        )
        color = _COLOR_SUELTA

    elemento = QListWidgetItem(texto)
    elemento.setData(Qt.ItemDataRole.UserRole, fila)
    elemento.setForeground(QColor(tokens.TEXTO_SUAVE))
    # El tipo se distingue por color: en un panel estrecho no cabe mas.
    elemento.setData(Qt.ItemDataRole.DecorationRole, QColor(color))
    return elemento
