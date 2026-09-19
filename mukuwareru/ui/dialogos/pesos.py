"""Reparto del peso de cada asignatura dentro de un proyecto.

Sigue la regla de ``DialogoHito``: recoge datos y no escribe nada. Quien lo abre
decide que hacer con el resultado.

Los pesos son numeros relativos y la columna de la derecha ensena, en vivo, en
que porcentaje se traducen. Asi valen tanto «3 / 2 / 1» en un master como los
pesos del examen del CFA, y no hay nada que cuadrar a mano.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Materia
from mukuwareru.ui.tema import tokens

_ANCHO_PESO = 110
_MAXIMO_PESO = 9999.0


class DialogoPesos(QDialog):
    """Una fila por materia con su peso y la cuota que representa."""

    def __init__(
        self,
        materias: list[Materia],
        totales: Mapping[int, int],
        *,
        propuesta_cfa: Mapping[int, float] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Peso de las asignaturas")
        self.setMinimumWidth(520)
        self._materias = materias
        self._totales = totales
        self._propuesta_cfa = dict(propuesta_cfa or {})
        self._campos: dict[int, QDoubleSpinBox] = {}
        self._cuotas: dict[int, QLabel] = {}

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        ayuda = QLabel(
            "El peso es un numero relativo: la aplicacion lo normaliza sola. "
            "Puedes escribir los porcentajes del examen o simplemente 3, 2 y 1. "
            "Dejalo todo en cero para volver al progreso por conteo de modulos."
        )
        ayuda.setObjectName("TextoTenue")
        ayuda.setWordWrap(True)
        columna.addWidget(ayuda)

        columna.addWidget(self._construir_tabla(), 1)

        self._total = QLabel()
        self._total.setObjectName("TextoSuave")
        self._total.setWordWrap(True)
        columna.addWidget(self._total)

        columna.addLayout(self._construir_atajos())

        botones = QDialogButtonBox()
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        aceptar = botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        aceptar.setObjectName("BotonPrimario")
        aceptar.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)

        self._recalcular()

    def _construir_tabla(self) -> QWidget:
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setMinimumHeight(240)

        lienzo = QWidget()
        rejilla = QGridLayout(lienzo)
        rejilla.setContentsMargins(0, 0, tokens.ESPACIO_PEQUENO, 0)
        rejilla.setHorizontalSpacing(tokens.ESPACIO)
        rejilla.setVerticalSpacing(tokens.ESPACIO_PEQUENO)

        for indice, texto in enumerate(("Asignatura", "Modulos", "Peso", "Cuota")):
            cabecera = QLabel(texto)
            cabecera.setStyleSheet("font-weight: 600;")
            rejilla.addWidget(cabecera, 0, indice)

        for fila, materia in enumerate(self._materias, start=1):
            total = self._totales.get(materia.id, 0)

            nombre = QLabel(materia.nombre)
            nombre.setWordWrap(True)
            rejilla.addWidget(nombre, fila, 0)

            recuento = QLabel(str(total))
            recuento.setObjectName("TextoTenue" if total else "TextoSuave")
            rejilla.addWidget(recuento, fila, 1)

            campo = QDoubleSpinBox()
            campo.setRange(0.0, _MAXIMO_PESO)
            campo.setDecimals(1)
            campo.setSingleStep(0.5)
            campo.setFixedWidth(_ANCHO_PESO)
            campo.setValue(materia.peso)
            campo.valueChanged.connect(self._recalcular)
            self._campos[materia.id] = campo
            rejilla.addWidget(campo, fila, 2)

            cuota = QLabel()
            cuota.setObjectName("TextoSuave")
            self._cuotas[materia.id] = cuota
            rejilla.addWidget(cuota, fila, 3)

        rejilla.setColumnStretch(0, 1)
        rejilla.setRowStretch(len(self._materias) + 1, 1)
        desplazable.setWidget(lienzo)
        return desplazable

    def _construir_atajos(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        if self._propuesta_cfa:
            cfa = QPushButton("Pesos del CFA Nivel I")
            cfa.setToolTip(
                "Rellena las asignaturas reconocidas con el punto medio del rango "
                "oficial del examen, reescalado para sumar 100. Puedes retocarlo "
                "despues."
            )
            cfa.clicked.connect(self._aplicar_cfa)
            fila.addWidget(cfa)

        igual = QPushButton("Repartir por igual")
        igual.setToolTip("Todas las asignaturas con el mismo peso.")
        igual.clicked.connect(self._repartir_igual)
        fila.addWidget(igual)

        limpiar = QPushButton("Quitar pesos")
        limpiar.setToolTip("Vuelve al progreso por conteo de modulos.")
        limpiar.clicked.connect(self._limpiar)
        fila.addWidget(limpiar)

        fila.addStretch(1)
        return fila

    # -- Atajos ----------------------------------------------------------------

    def _aplicar_cfa(self) -> None:
        """Rellena lo reconocido y deja a cero lo que no esta en el curriculo."""
        for materia_id, campo in self._campos.items():
            campo.setValue(self._propuesta_cfa.get(materia_id, 0.0))

    def _repartir_igual(self) -> None:
        for campo in self._campos.values():
            campo.setValue(1.0)

    def _limpiar(self) -> None:
        for campo in self._campos.values():
            campo.setValue(0.0)

    # -- Cuotas ----------------------------------------------------------------

    def _recalcular(self) -> None:
        """Actualiza la columna de cuotas y el pie con el diagnostico."""
        valores = {i: c.value() for i, c in self._campos.items()}
        suma = sum(valores.values())

        for materia_id, etiqueta in self._cuotas.items():
            if suma <= 0:
                etiqueta.setText("—")
            else:
                etiqueta.setText(f"{valores[materia_id] * 100 / suma:.1f} %")

        if suma <= 0:
            self._total.setText(
                "Sin pesos: el avance se calcula contando modulos, como hasta ahora."
            )
            return

        avisos = [
            materia.nombre
            for materia in self._materias
            if valores.get(materia.id, 0.0) > 0 and not self._totales.get(materia.id, 0)
        ]
        texto = f"Suma de pesos: {suma:.1f}  ·  las cuotas siempre suman 100 %."
        if avisos:
            # Un peso sobre una asignatura sin modulos no se puede medir, asi que
            # queda fuera del calculo. Callarselo haria que el porcentaje
            # ponderado no cuadrase con las cuotas de esta tabla.
            texto += (
                "\nSin modulos todavia, asi que no cuentan para el avance ponderado: "
                + ", ".join(avisos)
                + "."
            )
        self._total.setText(texto)

    def pesos(self) -> dict[int, float]:
        """Lo introducido, sin persistir nada."""
        return {materia_id: campo.value() for materia_id, campo in self._campos.items()}
