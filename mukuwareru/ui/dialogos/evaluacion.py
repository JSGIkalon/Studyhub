"""Alta y edicion del resultado de un examen.

Sigue la regla de ``DialogoHito``: recoge datos y no escribe nada. Quien lo abre
decide que hacer con el resultado.

La escala es la del examen —puntos obtenidos sobre posibles—, asi que sirve
igual para 38/50 de un simulacro, 8,5/10 de un parcial o 4,2/5 de un quiz. El
porcentaje se ensena al lado, calculado en vivo, para no tener que hacerlo de
cabeza.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Evaluacion, Hito, LineaEvaluacion, Materia
from mukuwareru.nucleo.servicios import DatosEvaluacion
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets import contenedor

_ANCHO_CAMPO = 170
_ANCHO_PUNTOS = 90
_MAXIMO_PUNTOS = 99999.0


class DialogoEvaluacion(QDialog):
    """Formulario de una evaluacion, con desglose por asignatura plegable."""

    def __init__(
        self,
        materias: list[Materia],
        hitos: list[Hito],
        evaluacion: Evaluacion | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar resultado" if evaluacion else "Nuevo resultado")
        self.setMinimumWidth(520)
        self._materias = materias
        self._hitos = hitos
        self._lineas: dict[int, tuple[QDoubleSpinBox, QDoubleSpinBox, QLabel]] = {}

        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        columna.addLayout(self._construir_formulario(evaluacion))
        columna.addWidget(self._construir_desglose())

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

        self._volcar(evaluacion)

    # -- Construccion ----------------------------------------------------------

    def _construir_formulario(self, evaluacion: Evaluacion | None) -> QFormLayout:
        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)

        self._titulo = QLineEdit()
        self._titulo.setPlaceholderText("Mock 3, Parcial de Econometria, Quiz 4…")
        self._titulo.textChanged.connect(self._revisar)
        formulario.addRow("Titulo", self._titulo)

        self._fecha = QDateEdit()
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd/MM/yyyy")
        self._fecha.setMaximumWidth(_ANCHO_CAMPO)
        formulario.addRow("Fecha", self._fecha)

        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)
        self._obtenidos = _campo_puntos()
        self._posibles = _campo_puntos(minimo=0.01, valor=100.0)
        self._obtenidos.valueChanged.connect(self._recalcular)
        self._posibles.valueChanged.connect(self._recalcular)
        fila.addWidget(self._obtenidos)
        fila.addWidget(QLabel("de"))
        fila.addWidget(self._posibles)
        self._porcentaje = QLabel()
        self._porcentaje.setProperty("fuerte", True)
        fila.addWidget(self._porcentaje)
        fila.addStretch(1)
        formulario.addRow("Puntuacion", contenedor(fila))

        # Una evaluacion sin nota es una evaluacion PENDIENTE: declarada con su
        # peso y su fecha, todavia sin corregir. Es lo que permite preguntar
        # «que necesito en el final» antes de hacerlo.
        self._pendiente = QCheckBox("Todavia no la he hecho (pendiente)")
        self._pendiente.setToolTip(
            "Se guarda el peso y la fecha, pero no la nota. No entra en ninguna "
            "media y si en el peso que te queda por evaluar."
        )
        self._pendiente.toggled.connect(self._al_marcar_pendiente)
        formulario.addRow("", self._pendiente)

        self._peso = QDoubleSpinBox()
        self._peso.setRange(0.0, _MAXIMO_PUNTOS)
        self._peso.setDecimals(1)
        self._peso.setSingleStep(0.5)
        self._peso.setValue(1.0)
        self._peso.setFixedWidth(_ANCHO_PUNTOS)
        self._peso.setToolTip(
            "Cuanto manda esta evaluacion en la nota de sus asignaturas. Es "
            "relativo: 30 y 70 dicen lo mismo que 3 y 7. Dejalo en 1 si todas "
            "cuentan igual."
        )
        formulario.addRow("Peso", self._peso)

        self._hito = QComboBox()
        self._hito.setMaximumWidth(260)
        self._hito.addItem("— ninguna —", None)
        for hito in self._hitos:
            self._hito.addItem(f"{hito.titulo} · {hito.fecha:%d/%m/%Y}", hito.id)
        self._hito.currentIndexChanged.connect(self._al_elegir_hito)
        formulario.addRow("Fecha del calendario", self._hito)

        self._nota = QLineEdit()
        self._nota.setPlaceholderText("Opcional")
        formulario.addRow("Nota", self._nota)
        return formulario

    def _construir_desglose(self) -> QWidget:
        caja = QVBoxLayout()
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(tokens.ESPACIO_PEQUENO)

        self._desglosar = QCheckBox("Desglosar por asignatura")
        self._desglosar.setToolTip(
            "Sin desglose solo se guarda la nota global: cuenta para la media, "
            "pero no dice en que asignatura fallaste."
        )
        caja.addWidget(self._desglosar)

        self._panel = QWidget()
        panel = QVBoxLayout(self._panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(tokens.ESPACIO_PEQUENO)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setMinimumHeight(180)
        lienzo = QWidget()
        rejilla = QGridLayout(lienzo)
        rejilla.setContentsMargins(0, 0, tokens.ESPACIO_PEQUENO, 0)
        rejilla.setHorizontalSpacing(tokens.ESPACIO)
        rejilla.setVerticalSpacing(tokens.ESPACIO_PEQUENO)

        for indice, texto in enumerate(("Asignatura", "Obtenidos", "Posibles", "%")):
            cabecera = QLabel(texto)
            cabecera.setProperty("fuerte", True)
            rejilla.addWidget(cabecera, 0, indice)

        for fila, materia in enumerate(self._materias, start=1):
            nombre = QLabel(materia.nombre)
            nombre.setWordWrap(True)
            rejilla.addWidget(nombre, fila, 0)

            obtenidos = _campo_puntos()
            posibles = _campo_puntos()
            acierto = QLabel("—")
            acierto.setObjectName("TextoSuave")
            obtenidos.valueChanged.connect(self._recalcular)
            posibles.valueChanged.connect(self._recalcular)

            rejilla.addWidget(obtenidos, fila, 1)
            rejilla.addWidget(posibles, fila, 2)
            rejilla.addWidget(acierto, fila, 3)
            self._lineas[materia.id] = (obtenidos, posibles, acierto)

        rejilla.setColumnStretch(0, 1)
        rejilla.setRowStretch(len(self._materias) + 1, 1)
        desplazable.setWidget(lienzo)
        panel.addWidget(desplazable)

        pie = QHBoxLayout()
        pie.setSpacing(tokens.ESPACIO_PEQUENO)
        self._suma = QLabel()
        self._suma.setObjectName("TextoSuave")
        self._suma.setWordWrap(True)
        pie.addWidget(self._suma, 1)
        self._usar_suma = QPushButton("Usar la suma del desglose")
        self._usar_suma.clicked.connect(self._volcar_suma)
        pie.addWidget(self._usar_suma)
        panel.addLayout(pie)

        ayuda = QLabel(
            "Deja en cero los «posibles» de una asignatura que no entrara en "
            "este examen. El desglose no tiene que cuadrar con la nota global."
        )
        ayuda.setObjectName("TextoTenue")
        ayuda.setWordWrap(True)
        panel.addWidget(ayuda)

        self._panel.setVisible(False)
        self._desglosar.toggled.connect(self._panel.setVisible)
        self._desglosar.toggled.connect(self._recalcular)
        caja.addWidget(self._panel)
        return contenedor(caja)

    # -- Estado ----------------------------------------------------------------

    def _volcar(self, evaluacion: Evaluacion | None) -> None:
        hoy = date.today()
        if evaluacion is None:
            self._fecha.setDate(QDate(hoy.year, hoy.month, hoy.day))
            self._revisar()
            self._recalcular()
            return

        self._titulo.setText(evaluacion.titulo)
        self._fecha.setDate(
            QDate(evaluacion.fecha.year, evaluacion.fecha.month, evaluacion.fecha.day)
        )
        self._pendiente.setChecked(evaluacion.pendiente)
        if evaluacion.puntos_obtenidos is not None:
            self._obtenidos.setValue(evaluacion.puntos_obtenidos)
        self._posibles.setValue(evaluacion.puntos_posibles)
        self._peso.setValue(evaluacion.peso)
        self._nota.setText(evaluacion.nota or "")
        if evaluacion.hito_id is not None:
            self._hito.setCurrentIndex(max(0, self._hito.findData(evaluacion.hito_id)))

        for linea in evaluacion.materias:
            campos = self._lineas.get(linea.materia_id)
            if campos is not None:
                campos[0].setValue(linea.puntos_obtenidos)
                campos[1].setValue(linea.puntos_posibles)
        # Se abre desplegado si ya tenia desglose: cerrarlo escondería el dato
        # que se viene a corregir.
        self._desglosar.setChecked(bool(evaluacion.materias))

        self._revisar()
        self._recalcular()

    def _al_elegir_hito(self) -> None:
        """Copia titulo y fecha del hito elegido. Ahorra casi todo el tecleo."""
        elegido = self._hito.currentData()
        if elegido is None:
            return
        hito = next((h for h in self._hitos if h.id == elegido), None)
        if hito is None:
            return
        if not self._titulo.text().strip():
            self._titulo.setText(hito.titulo)
        self._fecha.setDate(QDate(hito.fecha.year, hito.fecha.month, hito.fecha.day))

    def _al_marcar_pendiente(self, pendiente: bool) -> None:
        """Una pendiente no tiene nota, ni global ni desglosada.

        Se desactivan los campos en vez de esconderlos: asi se ve que siguen ahi
        para cuando se corrija, que es la edicion natural de este dialogo.
        """
        self._obtenidos.setEnabled(not pendiente)
        self._desglosar.setEnabled(not pendiente)
        if pendiente:
            self._desglosar.setChecked(False)
        self._recalcular()

    def _revisar(self) -> None:
        self._aceptar.setEnabled(bool(self._titulo.text().strip()))

    def _recalcular(self) -> None:
        """Porcentaje global, porcentajes por linea y el aviso de descuadre."""
        posibles = self._posibles.value()
        obtenidos = self._obtenidos.value()
        if self._pendiente.isChecked():
            self._porcentaje.setText("pendiente")
        else:
            self._porcentaje.setText(
                f"{obtenidos * 100 / posibles:.1f} %" if posibles > 0 else "—"
            )

        suma_obtenidos = suma_posibles = 0.0
        for campo_obtenidos, campo_posibles, acierto in self._lineas.values():
            linea_posibles = campo_posibles.value()
            linea_obtenidos = campo_obtenidos.value()
            if linea_posibles <= 0:
                acierto.setText("—")
                continue
            acierto.setText(f"{linea_obtenidos * 100 / linea_posibles:.0f} %")
            suma_obtenidos += linea_obtenidos
            suma_posibles += linea_posibles

        if not self._desglosar.isChecked() or suma_posibles <= 0:
            self._suma.setText("")
            self._usar_suma.setEnabled(False)
            return

        texto = f"El desglose suma {suma_obtenidos:g} de {suma_posibles:g}"
        descuadra = (
            abs(suma_obtenidos - obtenidos) > 0.1 or abs(suma_posibles - posibles) > 0.1
        )
        if descuadra:
            # Se avisa, no se impide: los simulacros redondean por tema y un
            # desglose parcial sigue siendo informacion util.
            texto += f"  ·  la nota global dice {obtenidos:g} de {posibles:g}."
        else:
            texto += "  ·  coincide con la nota global."
        self._suma.setText(texto)
        self._usar_suma.setEnabled(descuadra)

    def _volcar_suma(self) -> None:
        obtenidos = sum(
            campo.value()
            for campo, posibles, _ in self._lineas.values()
            if posibles.value() > 0
        )
        posibles = sum(
            campo.value() for _, campo, _ in self._lineas.values() if campo.value() > 0
        )
        if posibles <= 0:
            return
        self._obtenidos.setValue(obtenidos)
        self._posibles.setValue(posibles)

    # -- Resultado -------------------------------------------------------------

    def datos(self) -> DatosEvaluacion:
        """Lo introducido, sin persistir nada."""
        elegida = self._fecha.date()
        lineas: list[LineaEvaluacion] = []
        if self._desglosar.isChecked() and not self._pendiente.isChecked():
            for materia_id, (obtenidos, posibles, _) in self._lineas.items():
                # Posibles a cero significa «esta asignatura no entraba»: es mas
                # natural que una tercera casilla por fila.
                if posibles.value() > 0:
                    lineas.append(
                        LineaEvaluacion(materia_id, obtenidos.value(), posibles.value())
                    )

        return DatosEvaluacion(
            titulo=self._titulo.text().strip(),
            fecha=date(elegida.year(), elegida.month(), elegida.day()),
            puntos_obtenidos=(
                None if self._pendiente.isChecked() else self._obtenidos.value()
            ),
            puntos_posibles=self._posibles.value(),
            peso=self._peso.value(),
            hito_id=self._hito.currentData(),
            nota=self._nota.text().strip() or None,
            materias=tuple(lineas),
        )


def _campo_puntos(*, minimo: float = 0.0, valor: float = 0.0) -> QDoubleSpinBox:
    """Casilla de puntuacion con decimales: 38, 8,5 o 4,2 caben igual."""
    campo = QDoubleSpinBox()
    campo.setRange(minimo, _MAXIMO_PUNTOS)
    campo.setDecimals(2)
    campo.setSingleStep(1.0)
    campo.setValue(valor)
    campo.setFixedWidth(_ANCHO_PUNTOS)
    campo.setAlignment(Qt.AlignmentFlag.AlignRight)
    return campo
