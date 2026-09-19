"""Elegir con que se relaciona una nota.

La materia manda: al elegirla se filtran los modulos, de modo que nunca se puede
enlazar «Capital Structure» desde una nota de Ethics. Antes la lista era plana y
salian los 75 modulos del proyecto juntos, que es exactamente la confusion que
este dialogo elimina.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Documento, Materia, Modulo
from mukuwareru.ui.tema import tokens

_SIN_FILTRO = -1

MATERIA = "materia"
MODULO = "modulo"
DOCUMENTO = "documento"


@dataclass(frozen=True, slots=True)
class DestinoElegido:
    """Con que se quiere relacionar la nota."""

    clase: str            # MATERIA | MODULO | DOCUMENTO
    objeto_id: int
    pagina: int | None = None


class DialogoVincular(QDialog):
    """Materia, modulo o PDF, con los modulos filtrados por su materia."""

    def __init__(
        self,
        materias: list[Materia],
        modulos: dict[int, list[Modulo]],
        documentos: list[Documento],
        *,
        materia_sugerida: int | None = None,
        pagina_sugerida: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Relacionar la nota")
        self.setMinimumWidth(440)
        self._modulos = modulos

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)

        self._materia = QComboBox()
        self._materia.addItem("— todas las materias —", _SIN_FILTRO)
        for materia in materias:
            self._materia.addItem(materia.nombre, materia.id)
        if materia_sugerida is not None:
            self._materia.setCurrentIndex(max(0, self._materia.findData(materia_sugerida)))
        self._materia.currentIndexChanged.connect(self._al_cambiar_materia)
        formulario.addRow("Materia", self._materia)

        self._clase = QComboBox()
        self._clase.addItem("La materia entera", MATERIA)
        self._clase.addItem("Un modulo o lectura", MODULO)
        self._clase.addItem("Un PDF", DOCUMENTO)
        self._clase.setCurrentIndex(1)
        self._clase.currentIndexChanged.connect(self._al_cambiar_clase)
        formulario.addRow("Relacionar con", self._clase)

        self._modulo = QComboBox()
        formulario.addRow("Modulo", self._modulo)
        self._fila_modulo = self._modulo

        self._documento = QComboBox()
        for documento in documentos:
            self._documento.addItem(documento.nombre, documento.id)
        formulario.addRow("PDF", self._documento)

        self._pagina = QSpinBox()
        self._pagina.setRange(0, 99999)
        self._pagina.setSpecialValueText("Todo el documento")
        self._pagina.setValue(0 if pagina_sugerida is None else pagina_sugerida + 1)
        formulario.addRow("Pagina", self._pagina)

        columna.addLayout(formulario)

        self._aviso = QLabel()
        self._aviso.setObjectName("TextoTenue")
        self._aviso.setWordWrap(True)
        columna.addWidget(self._aviso)

        botones = QDialogButtonBox()
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self._aceptar = botones.addButton(
            "Relacionar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._aceptar.setObjectName("BotonPrimario")
        self._aceptar.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)

        self._al_cambiar_materia()
        self._al_cambiar_clase()

    # -- Cascada ------------------------------------------------------------

    def _al_cambiar_materia(self) -> None:
        """Rellena los modulos con los de la materia elegida, y solo esos."""
        materia_id = self._materia.currentData()
        anterior = self._modulo.currentData()

        self._modulo.blockSignals(True)
        self._modulo.clear()
        if materia_id == _SIN_FILTRO:
            # Sin materia elegida se listan todos, pero cualificados con su
            # materia para que se sepa de donde sale cada uno.
            for identificador, modulos in self._modulos.items():
                nombre_materia = self._nombre_materia(identificador)
                for modulo in modulos:
                    self._modulo.addItem(f"{nombre_materia} · {modulo.nombre}", modulo.id)
        else:
            for modulo in self._modulos.get(int(materia_id), []):
                self._modulo.addItem(modulo.nombre, modulo.id)

        indice = self._modulo.findData(anterior)
        self._modulo.setCurrentIndex(max(0, indice))
        self._modulo.blockSignals(False)
        self._revisar()

    def _nombre_materia(self, materia_id: int) -> str:
        indice = self._materia.findData(materia_id)
        return self._materia.itemText(indice) if indice >= 0 else "?"

    def _al_cambiar_clase(self) -> None:
        clase = self._clase.currentData()
        self._modulo.setEnabled(clase == MODULO)
        self._documento.setEnabled(clase == DOCUMENTO)
        self._pagina.setEnabled(clase == DOCUMENTO)
        self._revisar()

    def _revisar(self) -> None:
        clase = self._clase.currentData()
        if clase == MATERIA:
            valido = self._materia.currentData() != _SIN_FILTRO
            self._aviso.setText(
                "" if valido else "Elige una materia concreta para relacionarla."
            )
        elif clase == MODULO:
            valido = self._modulo.count() > 0
            self._aviso.setText(
                "" if valido else "Esa materia no tiene modulos todavia."
            )
        else:
            valido = self._documento.count() > 0
            self._aviso.setText(
                "" if valido else "El proyecto no tiene PDFs en la biblioteca."
            )
        self._aceptar.setEnabled(valido)

    # -- Resultado ----------------------------------------------------------

    def destino(self) -> DestinoElegido | None:
        """Lo elegido, o ``None`` si la seleccion no es valida."""
        clase = str(self._clase.currentData())
        if clase == MATERIA:
            materia_id = self._materia.currentData()
            if materia_id == _SIN_FILTRO:
                return None
            return DestinoElegido(MATERIA, int(materia_id))
        if clase == MODULO:
            if self._modulo.currentData() is None:
                return None
            return DestinoElegido(MODULO, int(self._modulo.currentData()))
        if self._documento.currentData() is None:
            return None
        pagina = self._pagina.value()
        return DestinoElegido(
            DOCUMENTO,
            int(self._documento.currentData()),
            pagina=None if pagina == 0 else pagina - 1,
        )
