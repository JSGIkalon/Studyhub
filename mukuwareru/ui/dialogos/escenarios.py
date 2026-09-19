"""«Y si saco un 3,5 en el final»: simulacion sobre las evaluaciones pendientes.

Nada de lo que se haga aqui toca una nota real. El dialogo pide un calculo al
servicio, que es una funcion de lectura, y pinta el resultado. Se cierra y no
queda rastro: es a proposito, porque un escenario que se guardara dejaria de
distinguirse de lo que de verdad ha pasado.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Evaluacion
from mukuwareru.nucleo.servicios import Calculo, EscalaNotas
from mukuwareru.ui.tema import tokens
from mukuwareru.utilidades import formato


class DialogoEscenarios(QDialog):
    """Una fila por evaluacion pendiente y el resultado recalculado en vivo."""

    def __init__(
        self,
        pendientes: Sequence[Evaluacion],
        escala: EscalaNotas,
        simular: Callable[[dict[int, float]], Calculo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Escenarios")
        self.setMinimumWidth(520)
        self._escala = escala
        self._simular = simular
        self._campos: dict[int, QDoubleSpinBox] = {}

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        ayuda = QLabel(
            "Supon una nota para cada evaluacion que te queda y mira como saldria "
            "la final. Esto no modifica ninguna nota real."
        )
        ayuda.setObjectName("TextoTenue")
        ayuda.setWordWrap(True)
        columna.addWidget(ayuda)

        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(tokens.ESPACIO)
        rejilla.setVerticalSpacing(tokens.ESPACIO_PEQUENO)
        for indice, texto in enumerate(("Evaluacion", "Fecha", "Peso", "Nota supuesta")):
            cabecera = QLabel(texto)
            cabecera.setStyleSheet("font-weight: 600;")
            rejilla.addWidget(cabecera, 0, indice)

        for fila, evaluacion in enumerate(pendientes, start=1):
            rejilla.addWidget(QLabel(evaluacion.titulo), fila, 0)

            fecha = QLabel(formato.fecha_corta(evaluacion.fecha))
            fecha.setObjectName("TextoTenue")
            rejilla.addWidget(fecha, fila, 1)

            peso = QLabel(f"{evaluacion.peso:g}")
            peso.setObjectName("TextoSuave")
            rejilla.addWidget(peso, fila, 2)

            campo = QDoubleSpinBox()
            campo.setRange(escala.minimo, escala.maximo)
            campo.setDecimals(2 if escala.recorrido <= 10 else 0)
            campo.setSingleStep(0.5 if escala.recorrido <= 10 else 5.0)
            # Se arranca en el aprobado: es la pregunta que casi siempre se hace.
            campo.setValue(escala.aprobado)
            campo.valueChanged.connect(self._recalcular)
            self._campos[evaluacion.id] = campo
            rejilla.addWidget(campo, fila, 3)

        rejilla.setColumnStretch(0, 1)
        columna.addLayout(rejilla)

        atajos = QVBoxLayout()
        atajos.setSpacing(tokens.ESPACIO_PEQUENO)
        for etiqueta, valor in (
            ("Todo al aprobado", escala.aprobado),
            ("Todo al maximo", escala.maximo),
            ("Todo al minimo", escala.minimo),
        ):
            boton = QPushButton(etiqueta)
            boton.clicked.connect(lambda _=False, v=valor: self._rellenar(v))
            atajos.addWidget(boton)
        columna.addLayout(atajos)

        self._resultado = QLabel()
        self._resultado.setObjectName("TextoSuave")
        self._resultado.setWordWrap(True)
        columna.addWidget(self._resultado)

        botones = QDialogButtonBox()
        cerrar = botones.addButton("Cerrar", QDialogButtonBox.ButtonRole.AcceptRole)
        cerrar.setDefault(True)
        botones.accepted.connect(self.accept)
        columna.addWidget(botones)

        self._recalcular()

    def _rellenar(self, valor: float) -> None:
        for campo in self._campos.values():
            campo.setValue(valor)

    def _recalcular(self) -> None:
        """Pide el calculo hipotetico y lo escribe. No guarda nada."""
        supuestos = {
            identificador: self._escala.a_fraccion(campo.value())
            for identificador, campo in self._campos.items()
        }
        calculo = self._simular(supuestos)
        aprueba = calculo.nota_acumulada >= self._escala.fraccion_aprobado
        self._resultado.setText(
            "Nota final con estos supuestos: "
            f"{self._escala.formatear(calculo.nota_acumulada)}"
            f"  ·  {'aprobado' if aprueba else 'suspenso'}"
        )
