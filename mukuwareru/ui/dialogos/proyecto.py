"""Alta y edicion de un proyecto.

Un solo dialogo para las dos cosas: los campos son los mismos y mantener dos
formularios en paralelo garantiza que uno se quede atras.

No escribe en la base de datos. Devuelve ``DatosProyecto`` y quien lo abrio
decide que hacer, igual que hace ``PanelNotas`` con las anotaciones. Renombrar
puede mover una carpeta del disco, y esa regla vive en ``ServicioProyectos``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Proyecto
from mukuwareru.nucleo.servicios import DatosProyecto
from mukuwareru.ui import iconos
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets import PaletaColores, contenedor
from mukuwareru.utilidades import rutas

_ANCHO_CAMPO = 170

# Iconos ofrecidos. Se excluye «mas», que es el signo de anadir y no representa
# nada; la etiqueta describe el dibujo, no el uso que se le da en la barra.
ICONOS = (
    ("libro", "Libro"),
    ("grafico", "Grafico"),
    ("documento", "Documento"),
    ("reloj", "Reloj"),
    ("panel", "Panel"),
    ("marcador", "Marcador"),
    ("estadisticas", "Estadisticas"),
    ("calendario", "Calendario"),
    ("engranaje", "Engranaje"),
)


class DialogoProyecto(QDialog):
    """Formulario de un proyecto. ``proyecto=None`` significa uno nuevo."""

    def __init__(self, proyecto: Proyecto | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._proyecto = proyecto
        self._color = proyecto.color if proyecto else tokens.ACENTO

        self.setWindowTitle("Editar proyecto" if proyecto else "Nuevo proyecto")
        self.setMinimumWidth(460)
        self._construir()
        self._volcar(proyecto)

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        columna = QVBoxLayout(self)
        columna.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO, tokens.ESPACIO
        )
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)

        self._nombre = QLineEdit()
        self._nombre.setPlaceholderText("CFA Level I, Master, Oposicion…")
        self._nombre.textChanged.connect(self._revisar)
        formulario.addRow("Nombre", self._nombre)

        self._icono = QComboBox()
        self._icono.setMaximumWidth(_ANCHO_CAMPO)
        for clave, etiqueta in ICONOS:
            self._icono.addItem(etiqueta, clave)
        formulario.addRow("Icono", self._icono)

        # El proyecto tiene color obligatorio, asi que aqui no hay «Automatico».
        self._paleta = PaletaColores(self._color)
        self._paleta.elegido.connect(self._elegir_color)
        formulario.addRow("Color", self._paleta)

        self._sin_fecha = QCheckBox("Sin fecha objetivo")
        self._sin_fecha.toggled.connect(self._al_marcar_sin_fecha)
        self._fecha = QDateEdit()
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd/MM/yyyy")
        self._fecha.setMaximumWidth(_ANCHO_CAMPO)

        caja_fecha = QVBoxLayout()
        caja_fecha.setSpacing(2)
        caja_fecha.addWidget(self._fecha)
        caja_fecha.addWidget(self._sin_fecha)
        formulario.addRow("Fecha objetivo", contenedor(caja_fecha))

        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)
        self._biblioteca = QLineEdit()
        fila.addWidget(self._biblioteca, 1)
        explorar = QPushButton("Examinar…")
        explorar.clicked.connect(self._elegir_biblioteca)
        fila.addWidget(explorar)
        formulario.addRow("Carpeta de PDFs", contenedor(fila))

        columna.addLayout(formulario)

        self._pista = QLabel()
        self._pista.setObjectName("TextoTenue")
        self._pista.setWordWrap(True)
        columna.addWidget(self._pista)

        botones = QDialogButtonBox()
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self._aceptar = botones.addButton(
            "Guardar" if self._proyecto else "Crear", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._aceptar.setObjectName("BotonPrimario")
        self._aceptar.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        columna.addWidget(botones)

    # -- Estado -------------------------------------------------------------

    def _volcar(self, proyecto: Proyecto | None) -> None:
        hoy = date.today()
        if proyecto is None:
            self._sin_fecha.setChecked(True)
            self._fecha.setDate(QDate(hoy.year, hoy.month, hoy.day))
            self._biblioteca.setPlaceholderText(str(rutas.carpeta_biblioteca()))
            self._elegir_color(tokens.ACENTO)
            self._revisar()
            return

        self._nombre.setText(proyecto.nombre)
        indice = self._icono.findData(proyecto.icono)
        self._icono.setCurrentIndex(max(0, indice))
        self._elegir_color(proyecto.color)

        objetivo = proyecto.fecha_objetivo
        self._sin_fecha.setChecked(objetivo is None)
        elegida = objetivo or hoy
        self._fecha.setDate(QDate(elegida.year, elegida.month, elegida.day))

        self._biblioteca.setText(proyecto.ruta_biblioteca or "")
        self._biblioteca.setPlaceholderText(
            str(rutas.carpeta_biblioteca() / proyecto.nombre)
        )
        self._revisar()

    def _elegir_color(self, color: str) -> None:
        self._color = color
        self._paleta.establecer(color)
        self._retintar_iconos()

    def _retintar_iconos(self) -> None:
        """Los iconos del selector se pintan con el color elegido.

        Es la unica forma de ver como quedara el proyecto en la barra lateral
        antes de aceptar, que es donde el color importa.
        """
        for indice in range(self._icono.count()):
            clave = self._icono.itemData(indice)
            self._icono.setItemIcon(indice, iconos.icono(str(clave), self._color))

    def _al_marcar_sin_fecha(self, marcado: bool) -> None:
        self._fecha.setEnabled(not marcado)
        self._revisar()

    def _revisar(self) -> None:
        """Un proyecto sin nombre no es un proyecto."""
        nombre = self._nombre.text().strip()
        self._aceptar.setEnabled(bool(nombre))
        if self._biblioteca.text().strip():
            self._pista.setText("Los PDFs se buscaran en la carpeta indicada.")
        elif nombre:
            self._pista.setText(
                f"Los PDFs se buscaran en {rutas.carpeta_biblioteca() / nombre}"
            )
        else:
            self._pista.setText("")

    def _elegir_biblioteca(self) -> None:
        inicial = self._biblioteca.text() or str(rutas.carpeta_biblioteca())
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta de la biblioteca", inicial)
        if carpeta:
            self._biblioteca.setText(str(Path(carpeta)))
            self._revisar()

    # -- Resultado ----------------------------------------------------------

    def datos(self) -> DatosProyecto:
        """Lo introducido en el formulario, sin persistir nada."""
        elegida = self._fecha.date()
        return DatosProyecto(
            nombre=self._nombre.text().strip(),
            icono=str(self._icono.currentData() or "libro"),
            color=self._color,
            fecha_objetivo=(
                None
                if self._sin_fecha.isChecked()
                else date(elegida.year(), elegida.month(), elegida.day())
            ),
            ruta_biblioteca=self._biblioteca.text().strip() or None,
        )
