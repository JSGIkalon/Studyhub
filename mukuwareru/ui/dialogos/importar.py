"""Asistente de importacion del temario desde Excel.

Elegir archivo, revisar la vista previa y confirmar. La vista previa es
obligatoria: importar a ciegas sobre el temario propio es demasiado arriesgado.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.modelos import Proyecto
from mukuwareru.nucleo.servicios import InformeImportacion
from mukuwareru.ui.tema import tokens
from mukuwareru.utilidades import formato
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)


class DialogoImportar(QDialog):
    """Dialogo de importacion con vista previa."""

    def __init__(
        self, contexto: Contexto, proyecto: Proyecto, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.contexto = contexto
        self.proyecto = proyecto
        self._informe: InformeImportacion | None = None

        self.setWindowTitle("Importar temario desde Excel")
        self.setMinimumSize(620, 520)
        self._construir()

    def _construir(self) -> None:
        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        explicacion = QLabel(
            f"Se importara en «{self.proyecto.nombre}». Reimportar el mismo "
            "archivo no duplica nada: los modulos se reconocen por su nombre y "
            "las sesiones por su fecha."
        )
        explicacion.setObjectName("TextoSuave")
        explicacion.setWordWrap(True)
        columna.addWidget(explicacion)

        fila = QHBoxLayout()
        self._ruta = QLabel("Ningun archivo seleccionado")
        self._ruta.setObjectName("TextoTenue")
        fila.addWidget(self._ruta, 1)

        elegir = QPushButton("Seleccionar archivo…")
        elegir.clicked.connect(self._elegir)
        fila.addWidget(elegir)
        columna.addLayout(fila)

        self._arbol = QTreeWidget()
        self._arbol.setHeaderLabels(["Materia / Modulo", "Estado"])
        self._arbol.setColumnWidth(0, 400)
        self._arbol.setAlternatingRowColors(False)
        columna.addWidget(self._arbol, 1)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoSuave")
        self._resumen.setWordWrap(True)
        columna.addWidget(self._resumen)

        self._botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self._aceptar = self._botones.button(QDialogButtonBox.StandardButton.Ok)
        self._aceptar.setText("Importar")
        self._aceptar.setObjectName("BotonPrimario")
        self._aceptar.setEnabled(False)
        self._botones.accepted.connect(self._importar)
        self._botones.rejected.connect(self.reject)
        columna.addWidget(self._botones)

    # -- Paso 1: elegir archivo --------------------------------------------

    def _elegir(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Excel", str(Path.cwd()), "Libros de Excel (*.xlsx *.xlsm)"
        )
        if ruta:
            self._analizar(Path(ruta))

    # -- Paso 2: vista previa ----------------------------------------------

    def _analizar(self, ruta: Path) -> None:
        try:
            informe = self.contexto.importacion.analizar(ruta)
        except Exception as error:  # noqa: BLE001 - cualquier fallo de lectura
            _log.exception("Fallo al analizar %s", ruta)
            QMessageBox.critical(
                self, "No se pudo leer el archivo", f"{type(error).__name__}: {error}"
            )
            return

        self._informe = informe
        self._ruta.setText(str(ruta))
        self._pintar(informe)

        if not informe.modulos and not informe.sesiones:
            self._resumen.setText(
                "No se encontro nada importable. Se esperan una hoja con "
                "columnas «Tema» y «Modulo», y otra con «Fecha» y «Horas»."
            )
            self._aceptar.setEnabled(False)
            return

        partes = [
            f"<b>{len(informe.materias)}</b> materias",
            f"<b>{len(informe.modulos)}</b> modulos "
            f"({informe.completados} completados)",
            f"<b>{len(informe.sesiones)}</b> sesiones ({informe.horas:.1f} h)",
        ]
        if informe.descartadas:
            partes.append(f"{len(informe.descartadas)} filas descartadas")
        if informe.hojas_ausentes:
            partes.append(f"hojas no encontradas: {', '.join(informe.hojas_ausentes)}")
        self._resumen.setText(" · ".join(partes))
        self._aceptar.setEnabled(True)

    def _pintar(self, informe: InformeImportacion) -> None:
        self._arbol.clear()
        por_materia: dict[str, QTreeWidgetItem] = {}

        for modulo in informe.modulos:
            if (raiz := por_materia.get(modulo.materia)) is None:
                raiz = QTreeWidgetItem(self._arbol, [modulo.materia, ""])
                raiz.setExpanded(False)
                por_materia[modulo.materia] = raiz
            QTreeWidgetItem(
                raiz, [modulo.nombre, "Completado" if modulo.completado else "Pendiente"]
            )

        for materia, raiz in por_materia.items():
            hechos = sum(1 for m in informe.modulos if m.materia == materia and m.completado)
            raiz.setText(1, f"{hechos} / {raiz.childCount()}")

        if informe.sesiones:
            sesiones = QTreeWidgetItem(self._arbol, ["Sesiones de estudio", ""])
            for sesion in informe.sesiones:
                QTreeWidgetItem(
                    sesiones,
                    [
                        formato.fecha_corta(sesion.fecha.date()),
                        formato.horas(sesion.segundos),
                    ],
                )
            sesiones.setText(1, f"{len(informe.sesiones)} dias")

        if informe.descartadas:
            descartadas = QTreeWidgetItem(self._arbol, ["Filas descartadas", ""])
            for texto in informe.descartadas:
                QTreeWidgetItem(descartadas, [texto, ""])
            descartadas.setText(1, str(len(informe.descartadas)))

    # -- Paso 3: confirmar --------------------------------------------------

    def _importar(self) -> None:
        if self._informe is None:
            return
        try:
            resultado = self.contexto.importacion.aplicar(self.proyecto.id, self._informe)
        except Exception as error:  # noqa: BLE001 - la transaccion ya hizo rollback
            _log.exception("Fallo al aplicar la importacion")
            QMessageBox.critical(
                self, "La importacion fallo", f"No se escribio nada.\n\n{error}"
            )
            return

        QMessageBox.information(
            self,
            "Importacion completada",
            f"Materias creadas: {resultado.materias_creadas}\n"
            f"Modulos creados: {resultado.modulos_creados}\n"
            f"Modulos actualizados: {resultado.modulos_actualizados}\n"
            f"Sesiones creadas: {resultado.sesiones_creadas}\n"
            f"Sesiones ya existentes: {resultado.sesiones_omitidas}",
        )
        self.accept()
