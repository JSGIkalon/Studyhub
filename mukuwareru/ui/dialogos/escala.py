"""Escala de notas del proyecto.

Sigue la regla de ``DialogoPesos``: recoge datos y no escribe nada.

La escala **no cambia ningun dato guardado**: las evaluaciones se siguen
anotando en puntos obtenidos sobre posibles, que es como vienen los examenes.
Esto solo decide como se leen. Cambiarla de 0-100 a 0-5 no toca ni una nota.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.servicios import EscalaNotas
from mukuwareru.ui.tema import tokens

_LIMITE = 10000.0

# Las dos escalas que cubren casi todos los casos: la universitaria colombiana y
# el porcentaje de las certificaciones.
_PRESETS: tuple[tuple[str, EscalaNotas], ...] = (
    ("0 a 5 · aprobado 3,0", EscalaNotas(0.0, 5.0, 3.0)),
    ("0 a 10 · aprobado 5,0", EscalaNotas(0.0, 10.0, 5.0)),
    ("0 a 100 % · aprobado 60", EscalaNotas(0.0, 100.0, 60.0)),
)


class DialogoEscala(QDialog):
    """Minimo, maximo y nota de aprobado."""

    def __init__(self, escala: EscalaNotas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Escala de notas")
        self.setMinimumWidth(420)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        ayuda = QLabel(
            "Las notas se guardan siempre como puntos obtenidos sobre posibles. "
            "Esto solo decide como se leen, asi que cambiarlo no altera ninguna "
            "nota que ya tengas."
        )
        ayuda.setObjectName("TextoTenue")
        ayuda.setWordWrap(True)
        columna.addWidget(ayuda)

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)
        self._minimo = self._campo(escala.minimo)
        self._maximo = self._campo(escala.maximo)
        self._aprobado = self._campo(escala.aprobado)
        formulario.addRow("Nota minima", self._minimo)
        formulario.addRow("Nota maxima", self._maximo)
        formulario.addRow("Aprobado a partir de", self._aprobado)
        columna.addLayout(formulario)

        atajos = QHBoxLayout()
        atajos.setSpacing(tokens.ESPACIO_PEQUENO)
        for etiqueta, preset in _PRESETS:
            boton = QPushButton(etiqueta)
            boton.clicked.connect(lambda _=False, e=preset: self._aplicar(e))
            atajos.addWidget(boton)
        atajos.addStretch(1)
        columna.addLayout(atajos)

        self._pie = QLabel()
        self._pie.setObjectName("TextoSuave")
        self._pie.setWordWrap(True)
        columna.addWidget(self._pie)

        self._botones = QDialogButtonBox()
        self._botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self._aceptar = self._botones.addButton(
            "Guardar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._aceptar.setObjectName("BotonPrimario")
        self._aceptar.setDefault(True)
        self._botones.accepted.connect(self.accept)
        self._botones.rejected.connect(self.reject)
        columna.addWidget(self._botones)

        self._revisar()

    def _campo(self, valor: float) -> QDoubleSpinBox:
        campo = QDoubleSpinBox()
        campo.setRange(-_LIMITE, _LIMITE)
        campo.setDecimals(2)
        campo.setSingleStep(0.5)
        campo.setValue(valor)
        campo.valueChanged.connect(self._revisar)
        return campo

    def _aplicar(self, escala: EscalaNotas) -> None:
        self._minimo.setValue(escala.minimo)
        self._maximo.setValue(escala.maximo)
        self._aprobado.setValue(escala.aprobado)

    def _revisar(self) -> None:
        """Impide guardar una escala imposible, y dice por que."""
        escala = self.escala()
        if escala.valida:
            self._pie.setText(
                f"Aprobar es el {escala.fraccion_aprobado * 100:.0f} % de los puntos."
            )
        else:
            self._pie.setText(
                "La nota maxima tiene que ser mayor que la minima, y el aprobado "
                "quedar entre las dos."
            )
        self._aceptar.setEnabled(escala.valida)

    def escala(self) -> EscalaNotas:
        """Lo introducido, sin persistir nada."""
        return EscalaNotas(
            minimo=self._minimo.value(),
            maximo=self._maximo.value(),
            aprobado=self._aprobado.value(),
        )
