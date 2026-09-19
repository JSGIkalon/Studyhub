"""Editor de comentarios de una anotacion, con imagenes pegadas del portapapeles.

Un ``QTextEdit`` normal ya acepta Ctrl+V con una imagen, pero solo la referencia
por un identificador de recurso interno a la sesion: su ``toHtml()`` no
sobrevive a guardarlo y releerlo en otro momento. Aqui cada imagen pegada se
reinserta como un ``data:`` URI en base64, que es autocontenido y cabe en la
misma columna de texto que ya usaba el comentario.
"""

from __future__ import annotations

import base64

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, Qt
from PySide6.QtGui import QImage, QTextCursor, QTextDocument
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout, QWidget

from mukuwareru.ui.tema import tokens

_ANCHO_MAXIMO_IMAGEN = 640
_PREFIJO_ENRIQUECIDO = "<!doctype html"


def es_enriquecido(comentario: str) -> bool:
    """Si el comentario es el HTML que produce este editor (trae imagenes)."""
    return comentario.lstrip().lower().startswith(_PREFIJO_ENRIQUECIDO)


def texto_sin_formato(comentario: str) -> str:
    """Version en una linea, sin etiquetas ni imagenes: para listas y resumenes."""
    if not es_enriquecido(comentario):
        return comentario
    documento = QTextDocument()
    documento.setHtml(comentario)
    # Cada imagen incrustada deja el caracter de reemplazo U+FFFC en el texto.
    plano = documento.toPlainText().replace("￼", "[imagen]")
    return " ".join(plano.split())


class _EditorConImagenes(QTextEdit):
    """``QTextEdit`` que incrusta lo pegado del portapapeles como ``data:`` URI."""

    def insertFromMimeData(self, fuente: QMimeData) -> None:  # noqa: N802 (API de Qt)
        if fuente.hasImage():
            imagen = QImage(fuente.imageData())
            if not imagen.isNull():
                self._insertar_imagen(imagen)
                return
        super().insertFromMimeData(fuente)

    def _insertar_imagen(self, imagen: QImage) -> None:
        if imagen.width() > _ANCHO_MAXIMO_IMAGEN:
            imagen = imagen.scaledToWidth(
                _ANCHO_MAXIMO_IMAGEN, Qt.TransformationMode.SmoothTransformation
            )
        datos = QByteArray()
        dispositivo = QBuffer(datos)
        dispositivo.open(QIODevice.OpenModeFlag.WriteOnly)
        imagen.save(dispositivo, "PNG")  # type: ignore[call-overload]
        codificada = base64.b64encode(datos.data()).decode("ascii")
        uri = f"data:image/png;base64,{codificada}"
        cursor = self.textCursor()
        cursor.insertHtml(
            f'<img src="{uri}" width="{imagen.width()}" height="{imagen.height()}">'
        )
        cursor.insertText(" ")


class DialogoNota(QDialog):
    """Edita el comentario de una anotacion; admite pegar una imagen (Ctrl+V)."""

    def __init__(
        self, titulo: str, comentario: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(480, 340)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        ayuda = QLabel("Puedes pegar una imagen del portapapeles con Ctrl+V.")
        ayuda.setObjectName("TextoTenue")
        columna.addWidget(ayuda)

        self._editor = _EditorConImagenes()
        self._editor.setAcceptRichText(True)
        if es_enriquecido(comentario):
            self._editor.setHtml(comentario)
        else:
            self._editor.setPlainText(comentario)
        columna.addWidget(self._editor, 1)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)

        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def comentario(self) -> str | None:
        """El texto final: HTML si lleva alguna imagen, texto plano si no."""
        html = self._editor.toHtml()
        if "<img" in html:
            return html
        texto = self._editor.toPlainText().strip()
        return texto or None
