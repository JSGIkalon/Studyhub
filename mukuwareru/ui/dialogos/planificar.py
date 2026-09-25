"""Dialogos del calendario: un hito y un bloque de estudio planeado.

Los dos siguen la misma regla que ``DialogoProyecto``: recogen datos y no
escriben nada. Quien los abre decide que hacer con el resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import BloquePlan, Hito, Materia, TipoHito
from mukuwareru.ui.tema import tokens

_ANCHO_CAMPO = 170


@dataclass(frozen=True, slots=True)
class DatosHito:
    """Lo que el formulario de un hito devuelve."""

    titulo: str
    fecha: date
    tipo: TipoHito = TipoHito.HITO
    hora: str | None = None
    nota: str | None = None


@dataclass(frozen=True, slots=True)
class DatosBloque:
    """Lo que el formulario de un bloque devuelve."""

    fecha: date
    duracion_min: int = 25
    hora_inicio: str | None = None
    titulo: str = ""
    nota: str | None = None
    materias: list[int] = field(default_factory=list)


class DialogoHito(QDialog):
    """Alta y edicion de una fecha clave."""

    def __init__(
        self, fecha: date, hito: Hito | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar fecha" if hito else "Nueva fecha clave")
        self.setMinimumWidth(380)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)

        self._titulo = QLineEdit(hito.titulo if hito else "")
        self._titulo.setPlaceholderText("Examen CFA Nivel I, Mock 2, entrega…")
        self._titulo.textChanged.connect(self._revisar)
        formulario.addRow("Titulo", self._titulo)

        self._tipo = QComboBox()
        self._tipo.setMaximumWidth(_ANCHO_CAMPO)
        for tipo in TipoHito:
            self._tipo.addItem(tipo.etiqueta, tipo)
        if hito is not None:
            self._tipo.setCurrentIndex(max(0, self._tipo.findData(hito.tipo)))
        formulario.addRow("Tipo", self._tipo)

        elegida = hito.fecha if hito else fecha
        self._fecha = QDateEdit(QDate(elegida.year, elegida.month, elegida.day))
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd/MM/yyyy")
        self._fecha.setMaximumWidth(_ANCHO_CAMPO)
        formulario.addRow("Fecha", self._fecha)

        self._con_hora = QCheckBox("A una hora concreta")
        self._con_hora.setChecked(bool(hito and hito.hora))
        self._hora = QTimeEdit(_a_qtime(hito.hora if hito else None))
        self._hora.setDisplayFormat("HH:mm")
        self._hora.setMaximumWidth(_ANCHO_CAMPO)
        self._hora.setEnabled(self._con_hora.isChecked())
        self._con_hora.toggled.connect(self._hora.setEnabled)
        formulario.addRow("Hora", self._con_hora)
        formulario.addRow("", self._hora)

        self._nota = QLineEdit(hito.nota if hito and hito.nota else "")
        self._nota.setPlaceholderText("Opcional")
        formulario.addRow("Nota", self._nota)

        columna.addLayout(formulario)

        botones = QDialogButtonBox()
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self._aceptar = botones.addButton(
            "Guardar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._aceptar.setObjectName("BotonPrimario")
        self._aceptar.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)
        self._revisar()

    def _revisar(self) -> None:
        self._aceptar.setEnabled(bool(self._titulo.text().strip()))

    def datos(self) -> DatosHito:
        """Lo introducido, sin persistir nada."""
        elegida = self._fecha.date()
        return DatosHito(
            titulo=self._titulo.text().strip(),
            fecha=date(elegida.year(), elegida.month(), elegida.day()),
            tipo=self._tipo.currentData() or TipoHito.HITO,
            hora=self._hora.time().toString("HH:mm") if self._con_hora.isChecked() else None,
            nota=self._nota.text().strip() or None,
        )


class DialogoBloque(QDialog):
    """Alta y edicion de un bloque de estudio planeado."""

    def __init__(
        self,
        fecha: date,
        materias: list[Materia],
        bloque: BloquePlan | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar bloque" if bloque else "Planificar estudio")
        self.setMinimumWidth(400)
        self._materias = materias

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)

        elegida = bloque.fecha if bloque else fecha
        self._fecha = QDateEdit(QDate(elegida.year, elegida.month, elegida.day))
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd/MM/yyyy")
        self._fecha.setMaximumWidth(_ANCHO_CAMPO)
        formulario.addRow("Dia", self._fecha)

        self._con_hora = QCheckBox("A una hora concreta")
        self._con_hora.setChecked(bloque.hora_inicio is not None if bloque else True)
        self._hora = QTimeEdit(_a_qtime(bloque.hora_inicio if bloque else "09:00"))
        self._hora.setDisplayFormat("HH:mm")
        self._hora.setMaximumWidth(_ANCHO_CAMPO)
        self._hora.setEnabled(self._con_hora.isChecked())
        self._con_hora.toggled.connect(self._hora.setEnabled)
        formulario.addRow("Hora", self._con_hora)
        formulario.addRow("", self._hora)

        self._duracion = QSpinBox()
        self._duracion.setRange(5, 600)
        self._duracion.setSingleStep(5)
        self._duracion.setSuffix(" min")
        self._duracion.setValue(bloque.duracion_min if bloque else 50)
        self._duracion.setMaximumWidth(_ANCHO_CAMPO)
        formulario.addRow("Duracion", self._duracion)

        self._titulo = QLineEdit(bloque.titulo if bloque else "")
        self._titulo.setPlaceholderText("Opcional: «repaso», «ejercicios»…")
        formulario.addRow("Titulo", self._titulo)

        columna.addLayout(formulario)

        etiqueta = QLabel("Materias previstas")
        etiqueta.setProperty("fuerte", True)
        columna.addWidget(etiqueta)

        self._lista = QListWidget()
        self._lista.setMaximumHeight(150)
        previstas = set(bloque.materias) if bloque else set()
        for materia in materias:
            elemento = QListWidgetItem(materia.nombre)
            elemento.setData(Qt.ItemDataRole.UserRole, materia.id)
            elemento.setFlags(elemento.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            elemento.setCheckState(
                Qt.CheckState.Checked
                if materia.id in previstas
                else Qt.CheckState.Unchecked
            )
            self._lista.addItem(elemento)
        columna.addWidget(self._lista)

        ayuda = QLabel(
            "Si marcas materias, solo cuenta para este bloque el tiempo etiquetado "
            "con alguna de ellas (o sin etiquetar). Dejalas todas sin marcar para "
            "que cuente cualquier sesion de la franja."
        )
        ayuda.setObjectName("TextoTenue")
        ayuda.setWordWrap(True)
        columna.addWidget(ayuda)

        botones = QDialogButtonBox()
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        aceptar = botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        aceptar.setObjectName("BotonPrimario")
        aceptar.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)

    def datos(self) -> DatosBloque:
        """Lo introducido, sin persistir nada."""
        elegida = self._fecha.date()
        marcadas = [
            int(self._lista.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self._lista.count())
            if self._lista.item(i).checkState() is Qt.CheckState.Checked
        ]
        return DatosBloque(
            fecha=date(elegida.year(), elegida.month(), elegida.day()),
            duracion_min=self._duracion.value(),
            hora_inicio=(
                self._hora.time().toString("HH:mm")
                if self._con_hora.isChecked()
                else None
            ),
            titulo=self._titulo.text().strip(),
            materias=marcadas,
        )


def _a_qtime(hora: str | None) -> QTime:
    """Convierte ``'HH:MM'`` en ``QTime``, con las nueve como respaldo."""
    if hora:
        convertida = QTime.fromString(hora, "HH:mm")
        if convertida.isValid():
            return convertida
    return QTime(9, 0)
