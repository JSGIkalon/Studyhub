"""Horas, prioridad y fecha limite de una asignatura.

Sigue la regla de ``DialogoPesos``: recoge datos y no escribe nada. Quien lo
abre decide que hacer con el resultado.

Las horas restantes se calculan solas y solo se dejan editar si se pide
expresamente. Un campo que se recalcula mientras lo escribes es un campo que
pelea contigo; uno que no se puede corregir nunca es peor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Prioridad
from mukuwareru.nucleo.servicios import CargaMateria
from mukuwareru.ui.tema import tokens

_MAXIMO_HORAS = 9999.0


@dataclass(frozen=True, slots=True)
class DatosCarga:
    """Lo que el formulario devuelve. No persiste nada."""

    horas_estimadas: float | None
    horas_restantes_manual: float | None
    prioridad: Prioridad
    fecha_limite: date | None


class DialogoCarga(QDialog):
    """Carga declarada de una asignatura: horas, prioridad y fecha limite."""

    def __init__(self, carga: CargaMateria, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Carga de {carga.nombre}")
        self.setMinimumWidth(440)
        self._carga = carga

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)

        self._estimadas = QDoubleSpinBox()
        self._estimadas.setRange(0.0, _MAXIMO_HORAS)
        self._estimadas.setDecimals(1)
        self._estimadas.setSingleStep(1.0)
        self._estimadas.setSpecialValueText("Sin estimar")
        self._estimadas.setSuffix(" h")
        self._estimadas.setValue(carga.horas_estimadas or 0.0)
        self._estimadas.valueChanged.connect(self._recalcular)
        formulario.addRow("Horas estimadas", self._estimadas)

        if carga.desglosada:
            # La estimacion sale de los modulos; tocarla aqui no serviria de
            # nada, asi que se dice en vez de dejar un campo que miente.
            self._estimadas.setEnabled(False)
            self._estimadas.setToolTip(
                "Sale de las horas de los modulos de esta asignatura."
            )

        self._dedicadas = QLabel()
        self._dedicadas.setObjectName("TextoSuave")
        formulario.addRow("Horas dedicadas", self._dedicadas)

        self._restantes = QDoubleSpinBox()
        self._restantes.setRange(0.0, _MAXIMO_HORAS)
        self._restantes.setDecimals(1)
        self._restantes.setSingleStep(1.0)
        self._restantes.setSuffix(" h")
        formulario.addRow("Horas restantes", self._restantes)

        self._manual = QCheckBox("Fijar las horas restantes a mano")
        self._manual.setToolTip(
            "Por defecto son las estimadas menos las dedicadas. Marcalo si esa "
            "resta no refleja lo que de verdad te queda."
        )
        self._manual.setChecked(carga.sobrescrita)
        self._manual.toggled.connect(self._recalcular)
        formulario.addRow("", self._manual)

        self._prioridad = QComboBox()
        for nivel in Prioridad:
            self._prioridad.addItem(nivel.etiqueta, nivel)
        self._prioridad.setCurrentIndex(int(carga.prioridad))
        formulario.addRow("Prioridad", self._prioridad)

        self._con_limite = QCheckBox("Tiene fecha limite")
        self._con_limite.setChecked(carga.fecha_limite is not None)
        self._con_limite.toggled.connect(self._alternar_limite)
        formulario.addRow("", self._con_limite)

        self._limite = QDateEdit()
        self._limite.setCalendarPopup(True)
        self._limite.setDisplayFormat("dd/MM/yyyy")
        self._limite.setDate(
            QDate(carga.fecha_limite) if carga.fecha_limite else QDate.currentDate()
        )
        self._limite.setEnabled(carga.fecha_limite is not None)
        formulario.addRow("Fecha limite", self._limite)

        columna.addLayout(formulario)

        self._pie = QLabel()
        self._pie.setObjectName("TextoTenue")
        self._pie.setWordWrap(True)
        columna.addWidget(self._pie)

        botones = QDialogButtonBox()
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        aceptar = botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        aceptar.setObjectName("BotonPrimario")
        aceptar.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)

        self._recalcular()

    # -- Estado del formulario -------------------------------------------------

    def _alternar_limite(self, activo: bool) -> None:
        self._limite.setEnabled(activo)

    def _recalcular(self) -> None:
        """Mantiene las horas restantes al dia mientras no se fijen a mano."""
        manual = self._manual.isChecked()
        self._restantes.setEnabled(manual)

        dedicadas = self._carga.horas_dedicadas
        self._dedicadas.setText(
            f"{dedicadas:.1f} h"
            + ("  ·  de los modulos ya completados" if self._carga.desglosada else "")
        )

        if manual:
            if self._carga.horas_restantes_manual is not None:
                self._restantes.setValue(self._carga.horas_restantes_manual)
        else:
            self._restantes.setValue(max(0.0, self._estimadas.value() - dedicadas))

        if self._estimadas.value() <= 0 and not manual:
            self._pie.setText(
                "Sin horas estimadas esta asignatura no entra en el reparto del "
                "plan: el ritmo se sigue calculando contando modulos."
            )
        else:
            self._pie.setText("")

    # -- Resultado -------------------------------------------------------------

    def datos(self) -> DatosCarga:
        """Lo introducido, sin persistir nada."""
        estimadas = self._estimadas.value()
        return DatosCarga(
            horas_estimadas=estimadas if estimadas > 0 else None,
            horas_restantes_manual=(
                self._restantes.value() if self._manual.isChecked() else None
            ),
            prioridad=self._prioridad.currentData(),
            fecha_limite=(
                self._limite.date().toPython() if self._con_limite.isChecked() else None
            ),
        )


def color_de_prioridad(prioridad: Prioridad) -> str:
    """Color con que se pinta cada nivel. Vive aqui para no repetirlo.

    La prioridad baja usa el texto tenue y no un color propio: lo que no urge no
    tiene por que llamar la atencion.
    """
    return {
        Prioridad.BAJA: tokens.TEXTO_TENUE,
        Prioridad.MEDIA: tokens.TEXTO_SUAVE,
        Prioridad.ALTA: tokens.AVISO,
        Prioridad.CRITICA: tokens.ACENTO,
    }[prioridad]


__all__ = ["DatosCarga", "DialogoCarga", "color_de_prioridad"]
