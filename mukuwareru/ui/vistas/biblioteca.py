"""Biblioteca: los PDFs del proyecto, descubiertos solos.

No hay importacion manual. Se deja el archivo en la carpeta del proyecto y
aparece, tanto al abrir la vista como cuando cambia el contenido de la carpeta.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Documento
from mukuwareru.nucleo.servicios.biblioteca import ruta_biblioteca
from mukuwareru.ui import iconos
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import TarjetaDocumento, vaciar
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)
_COLUMNAS = 3
_RETARDO_VIGILANCIA_MS = 800


class VistaBiblioteca(VistaBase):
    """Rejilla de PDFs con busqueda y escaneo automatico."""

    titulo = "Biblioteca"
    dominio = "documentos"
    ignora = frozenset({"calendario", "resultados", "sesiones"})
    abrir_documento = Signal(object)  # Documento

    def _construir(self) -> None:
        self._filtro = ""
        self._vigilante = QFileSystemWatcher(self)
        self._vigilante.directoryChanged.connect(self._al_cambiar_carpeta)

        # Los cambios en disco llegan en rafagas; un retardo evita escanear
        # cinco veces mientras se copia una carpeta entera.
        self._rebote = QTimer(self)
        self._rebote.setSingleShot(True)
        self._rebote.setInterval(_RETARDO_VIGILANCIA_MS)
        self._rebote.timeout.connect(self._escanear)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE, 0
        )
        raiz.setSpacing(tokens.ESPACIO_PEQUENO)
        raiz.addLayout(self._construir_cabecera())

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        raiz.addWidget(desplazable, 1)

        lienzo = QWidget()
        columna = QVBoxLayout(lienzo)
        columna.setContentsMargins(0, tokens.ESPACIO_PEQUENO, 0, tokens.ESPACIO_GRANDE)
        columna.setSpacing(tokens.ESPACIO)

        self._rejilla = QGridLayout()
        self._rejilla.setSpacing(tokens.ESPACIO)
        columna.addLayout(self._rejilla)
        columna.addStretch(1)
        desplazable.setWidget(lienzo)

    def _construir_cabecera(self) -> QVBoxLayout:
        cabecera = QVBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        fila = QHBoxLayout()
        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        fila.addWidget(titulo)
        fila.addStretch(1)

        self._buscador = QLineEdit()
        self._buscador.setPlaceholderText("Buscar por nombre…")
        self._buscador.setClearButtonEnabled(True)
        self._buscador.setFixedWidth(240)
        self._buscador.textChanged.connect(self._al_filtrar)
        fila.addWidget(self._buscador)

        anadir = QPushButton("  Anadir PDFs")
        anadir.setObjectName("BotonPrimario")
        anadir.setIcon(iconos.icono("mas", "#FFFFFF"))
        anadir.setToolTip("Copia PDFs a la carpeta de este proyecto")
        anadir.clicked.connect(self._anadir_pdfs)
        fila.addWidget(anadir)

        carpeta = QPushButton("  Abrir carpeta")
        carpeta.setIcon(iconos.icono("documento", tokens.TEXTO_SUAVE))
        carpeta.clicked.connect(self._abrir_carpeta)
        fila.addWidget(carpeta)

        refrescar = QPushButton("Actualizar")
        refrescar.clicked.connect(self._escanear)
        fila.addWidget(refrescar)
        cabecera.addLayout(fila)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoSuave")
        cabecera.addWidget(self._resumen)
        return cabecera

    # -- Datos --------------------------------------------------------------

    def recargar(self) -> None:
        """Escanea la carpeta del proyecto y repinta la rejilla."""
        self._escanear()

    def _escanear(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            self._resumen.setText("Sin proyecto seleccionado.")
            self._pintar([])
            return

        resultado = self.contexto.biblioteca.escanear(proyecto)
        self._vigilar(ruta_biblioteca(proyecto))

        documentos = self.contexto.documentos.listar(proyecto.id)
        self._pintar(documentos)
        self._resumen.setText(self._texto_resumen(len(documentos), resultado.nuevos))

        if resultado.hubo_cambios:
            self.contexto.notificar_cambio(self)

    def _texto_resumen(self, total: int, nuevos: int) -> str:
        if total == 0:
            return "Ninguno todavia."
        texto = f"{total} PDF" + ("s" if total != 1 else "")
        if nuevos:
            texto += f"  ·  {nuevos} nuevo" + ("s" if nuevos != 1 else "")
        return texto

    def _pintar(self, documentos: list[Documento]) -> None:
        vaciar(self._rejilla)

        visibles = [d for d in documentos if self._filtro in d.nombre.casefold()]
        if not visibles:
            self._rejilla.addWidget(self._estado_vacio(bool(documentos)), 0, 0, 1, _COLUMNAS)
            return

        # Un solo conteo para toda la rejilla, no uno por tarjeta.
        proyecto = self.contexto.proyecto
        notas = (
            self.contexto.notas.conteo_por_documento(proyecto.id)
            if proyecto is not None
            else {}
        )

        for indice, documento in enumerate(visibles):
            tarjeta = TarjetaDocumento(documento, notas.get(documento.id, 0))
            tarjeta.abrir.connect(self._abrir)
            self._rejilla.addWidget(tarjeta, indice // _COLUMNAS, indice % _COLUMNAS)

    def _estado_vacio(self, hay_documentos: bool) -> QLabel:
        proyecto = self.contexto.proyecto
        if hay_documentos:
            texto = "Ningun PDF coincide con la busqueda."
        elif proyecto is None:
            texto = "Sin proyecto seleccionado."
        else:
            texto = (
                "Aun no hay PDFs en este proyecto.\n\n"
                f"Copia tus archivos a:\n{ruta_biblioteca(proyecto)}\n\n"
                "Apareceran solos, sin importarlos."
            )
        etiqueta = QLabel(texto)
        etiqueta.setObjectName("TextoTenue")
        etiqueta.setWordWrap(True)
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        etiqueta.setMinimumHeight(180)
        return etiqueta

    # -- Acciones -----------------------------------------------------------

    def _al_filtrar(self, texto: str) -> None:
        self._filtro = texto.strip().casefold()
        proyecto = self.contexto.proyecto
        if proyecto is not None:
            self._pintar(self.contexto.documentos.listar(proyecto.id))

    def _abrir(self, documento: object) -> None:
        if isinstance(documento, Documento):
            self.abrir_documento.emit(documento)

    def _anadir_pdfs(self) -> None:
        """Copia PDFs elegidos por el usuario a la carpeta del proyecto.

        Se copian en lugar de enlazarse: la biblioteca debe seguir funcionando
        aunque el original se mueva o se borre.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return

        elegidos, _ = QFileDialog.getOpenFileNames(
            self, "Anadir PDFs a la biblioteca", str(Path.home()), "PDF (*.pdf)"
        )
        if not elegidos:
            return

        carpeta = ruta_biblioteca(proyecto)
        carpeta.mkdir(parents=True, exist_ok=True)
        copiados, omitidos, fallidos = 0, 0, []

        for texto in elegidos:
            origen = Path(texto)
            destino = carpeta / origen.name
            if destino.exists():
                omitidos += 1
                continue
            try:
                shutil.copy2(origen, destino)
                copiados += 1
            except OSError as error:
                _log.warning("No se pudo copiar %s: %s", origen, error)
                fallidos.append(f"{origen.name}: {error.strerror}")

        self._escanear()
        self._informar(copiados, omitidos, fallidos)

    def _informar(self, copiados: int, omitidos: int, fallidos: list[str]) -> None:
        partes = [f"Copiados: {copiados}"]
        if omitidos:
            partes.append(f"Ya estaban en la biblioteca: {omitidos}")
        if fallidos:
            partes.append("No se pudieron copiar:\n  " + "\n  ".join(fallidos))
        icono = QMessageBox.warning if fallidos else QMessageBox.information
        icono(self, "Anadir PDFs", "\n".join(partes))

    def _abrir_carpeta(self) -> None:
        """Abre la carpeta en el explorador de archivos del sistema."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        carpeta = ruta_biblioteca(proyecto)
        carpeta.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(carpeta)
            else:
                subprocess.run(["xdg-open", str(carpeta)], check=False)
        except OSError as error:
            _log.warning("No se pudo abrir %s: %s", carpeta, error)

    # -- Vigilancia de la carpeta ------------------------------------------

    def _vigilar(self, carpeta: Path) -> None:
        """Observa la carpeta y sus subcarpetas para detectar PDFs nuevos."""
        if previas := self._vigilante.directories():
            self._vigilante.removePaths(previas)
        if not carpeta.exists():
            return
        rutas = [str(carpeta)] + [str(p) for p in carpeta.rglob("*") if p.is_dir()]
        self._vigilante.addPaths(rutas)

    def _al_cambiar_carpeta(self, _ruta: str) -> None:
        self._rebote.start()
