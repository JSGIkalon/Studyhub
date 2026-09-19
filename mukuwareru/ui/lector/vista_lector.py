"""Lector: la pantalla de estudio.

Reune la barra de herramientas, el panel lateral y el lienzo de paginas, y se
encarga de recordar donde se quedo la lectura y de crear anotaciones sobre el
texto seleccionado.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QModelIndex, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QShortcut
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.modelos import Anotacion, Documento, TipoAnotacion
from mukuwareru.nucleo.servicios import ruta_biblioteca
from mukuwareru.ui import ajustes_arranque, atajos, iconos
from mukuwareru.ui.dialogos.nota import DialogoNota
from mukuwareru.ui.lector.panel_lateral import PanelLateral
from mukuwareru.ui.lector.vista_paginas import ZOOM_MAXIMO, ZOOM_MINIMO, Resaltado, VistaPaginas
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets import contenedor
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)
_INTERVALO_GUARDADO_MS = 5000
_COLOR_RESALTADO = tokens.AVISO
_COLOR_HALLAZGO = tokens.INFO


class VistaLector(QWidget):
    """Visor de PDF pensado para estudiar."""

    volver = Signal()
    anotaciones_cambiadas = Signal()
    abrir_nota = Signal(int)  # id de una nota suelta, para saltar a la vista Notas

    def __init__(self, contexto: Contexto, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.contexto = contexto
        self.documento: Documento | None = None
        self._pdf = QPdfDocument(self)
        self._anotaciones: list[Anotacion] = []

        # Guardar en cada scroll escribiria en disco decenas de veces por
        # segundo; un temporizador perezoso basta para no perder la posicion.
        self._guardado = QTimer(self)
        self._guardado.setInterval(_INTERVALO_GUARDADO_MS)
        self._guardado.timeout.connect(self.guardar_posicion)

        self._construir()
        self._atajos()

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._barra())

        self._divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor = self._divisor
        divisor.setChildrenCollapsible(True)

        self._panel = PanelLateral()
        self._panel.setMinimumWidth(180)
        self._panel.pagina_pedida.connect(self._ir_a_pagina)
        self._panel.resultados_cambiados.connect(self._pintar_hallazgos)
        self._panel.notas.editar_pedido.connect(self._editar_anotacion)
        self._panel.notas.eliminar_pedido.connect(self._eliminar_anotacion)
        self._panel.notas.nota_suelta_pedida.connect(self._nota_en_cuaderno)
        self._panel.notas.vincular_pedido.connect(self._vincular_nota)
        self._panel.notas.desvincular_pedido.connect(self._desvincular_nota)
        self._panel.nota_pedida.connect(self.abrir_nota.emit)
        divisor.addWidget(self._panel)

        self._paginas = VistaPaginas()
        self._paginas.pagina_cambiada.connect(self._al_cambiar_pagina)
        self._paginas.zoom_cambiado.connect(self._al_cambiar_zoom)
        self._paginas.menu_pedido.connect(self._menu_contextual)
        divisor.addWidget(self._paginas)

        divisor.setStretchFactor(0, 0)
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([240, 900])
        # El reparto es del usuario y sobrevive al cierre: mover el divisor y
        # encontrarlo movido al volver es la mitad de que sirva para algo.
        self._restaurar_divisor()
        divisor.splitterMoved.connect(lambda *_: self._guardar_divisor())
        raiz.addWidget(divisor, 1)

    def _barra(self) -> QWidget:
        fila = QHBoxLayout()
        fila.setContentsMargins(
            tokens.ESPACIO, tokens.ESPACIO_PEQUENO, tokens.ESPACIO, tokens.ESPACIO_PEQUENO
        )
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        atras = QPushButton("  Biblioteca")
        atras.setIcon(iconos.icono("documento", tokens.TEXTO_SUAVE))
        atras.setCursor(Qt.CursorShape.PointingHandCursor)
        atras.clicked.connect(self._al_volver)
        fila.addWidget(atras)

        self._titulo = QLabel()
        self._titulo.setStyleSheet("font-weight: 600;")
        fila.addWidget(self._titulo, 1)

        self._selector = QSpinBox()
        self._selector.setMinimum(1)
        self._selector.setFixedWidth(72)
        self._selector.valueChanged.connect(lambda valor: self._ir_a_pagina(valor - 1))
        fila.addWidget(self._selector)

        self._total = QLabel("de 0")
        self._total.setObjectName("TextoTenue")
        fila.addWidget(self._total)

        for texto, accion, ayuda in (
            ("-", self._paginas_alejar, "Alejar (Ctrl+-)"),
            ("+", self._paginas_acercar, "Acercar (Ctrl++)"),
        ):
            boton = QPushButton(texto)
            boton.setFixedWidth(34)
            boton.setToolTip(ayuda)
            boton.clicked.connect(accion)
            fila.addWidget(boton)

        self._zoom = QPushButton("100 %")
        self._zoom.setObjectName("TextoTenue")
        self._zoom.setFlat(True)
        self._zoom.setFixedWidth(52)
        self._zoom.setCursor(Qt.CursorShape.PointingHandCursor)
        self._zoom.setToolTip("Escribir un porcentaje de zoom exacto")
        self._zoom.clicked.connect(self._pedir_zoom)
        fila.addWidget(self._zoom)

        ancho = QPushButton("Ancho")
        ancho.setToolTip("Ajustar al ancho de la pagina")
        ancho.clicked.connect(lambda: self._paginas.ajustar_ancho())
        fila.addWidget(ancho)

        pagina = QPushButton("Pagina")
        pagina.setToolTip("Ajustar la pagina completa")
        pagina.clicked.connect(lambda: self._paginas.ajustar_pagina())
        fila.addWidget(pagina)

        buscar = QPushButton("Buscar")
        buscar.setToolTip("Buscar en el documento (Ctrl+F)")
        buscar.clicked.connect(lambda: self._panel.enfocar_busqueda())
        fila.addWidget(buscar)

        notas = QPushButton("Notas")
        notas.setToolTip("Reparte la pantalla al 50/50 con las notas de este PDF")
        notas.clicked.connect(self._repartir_notas)
        fila.addWidget(notas)

        barra = contenedor(fila)
        barra.setStyleSheet(f"border-bottom: 1px solid {tokens.BORDE_SUTIL};")
        return barra

    def _atajos(self) -> None:
        """Engancha las teclas del lector. Las combinaciones viven en `ui/atajos.py`."""
        for clave, accion in (
            ("buscar_pdf", lambda: self._panel.enfocar_busqueda()),
            ("acercar", self._paginas_acercar),
            ("alejar", self._paginas_alejar),
            ("ajustar", lambda: self._paginas.ajustar_ancho()),
            # Ctrl+M creaba una nota anclada al PDF. Ahora lo que se escribe va a
            # un cuaderno, asi que el atajo apunta ahi.
            ("nota", self._nota_en_cuaderno),
            ("copiar", self._copiar),
            ("volver", self._al_volver),
        ):
            QShortcut(atajos.secuencia(clave), self, activated=accion)

    def _traer_notas(self) -> None:
        """Trae la pestana de notas al frente **sin tocar el reparto**.

        Antes esto repartia la pantalla al 50/50, y lo llamaba todo: abrir un
        PDF, crear una nota, crear un resaltado. El resultado era que cualquier
        anotacion deshacia el reparto que el usuario acababa de elegir.
        """
        self._panel.mostrar_notas()

    def _repartir_notas(self) -> None:
        """50/50 entre panel y PDF. Solo desde el boton «Notas» de la barra."""
        self._panel.mostrar_notas()
        ancho = max(self.width(), self._divisor.width())
        self._divisor.setSizes([ancho // 2, ancho - ancho // 2])

    def _restaurar_divisor(self) -> None:
        """Recupera el reparto panel/PDF de la sesion anterior."""
        guardado = ajustes_arranque.obtener_valor("lector_divisor")
        if isinstance(guardado, str):
            self._divisor.restoreState(QByteArray.fromBase64(guardado.encode()))

    def _guardar_divisor(self) -> None:
        ajustes_arranque.guardar(
            "lector_divisor",
            bytes(self._divisor.saveState().toBase64().data()).decode(),
        )

    def _paginas_acercar(self) -> None:
        self._paginas.acercar()

    def _paginas_alejar(self) -> None:
        self._paginas.alejar()

    def _pedir_zoom(self) -> None:
        """Deja escribir un porcentaje de zoom exacto en vez de ir paso a paso."""
        actual = round(self._paginas.zoom * 100)
        valor, aceptado = QInputDialog.getInt(
            self,
            "Zoom",
            "Porcentaje de zoom:",
            actual,
            round(ZOOM_MINIMO * 100),
            round(ZOOM_MAXIMO * 100),
            5,
        )
        if aceptado:
            self._paginas.establecer_zoom(valor / 100)

    # -- Apertura y cierre --------------------------------------------------

    def abrir(self, documento: Documento) -> bool:
        """Carga un PDF y restaura la posicion de lectura anterior."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return False

        ruta = ruta_biblioteca(proyecto) / documento.ruta_relativa
        if not ruta.exists():
            QMessageBox.warning(
                self, "Archivo no encontrado",
                f"No se encuentra:\n{ruta}\n\nActualiza la biblioteca.",
            )
            return False

        error = self._pdf.load(str(ruta))
        if error is not QPdfDocument.Error.None_:
            QMessageBox.critical(self, "No se pudo abrir el PDF", f"{ruta.name}\n\n{error}")
            _log.warning("Fallo al abrir %s: %s", ruta, error)
            return False

        self.documento = documento
        self._titulo.setText(documento.nombre)
        self._paginas.establecer_documento(self._pdf)
        self._panel.establecer_documento(self._pdf)

        total = self._pdf.pageCount()
        self._selector.setMaximum(max(1, total))
        self._total.setText(f"de {total}")
        if documento.paginas != total:
            self.contexto.documentos.establecer_paginas(documento.id, total)

        self._restaurar_posicion(documento)
        self._cargar_anotaciones()
        self.contexto.documentos.marcar_abierto(documento.id)
        self._guardado.start()
        self._traer_notas()
        _log.info("Abierto %s (%d paginas)", documento.nombre, total)
        return True

    def _restaurar_posicion(self, documento: Documento) -> None:
        """Devuelve zoom y pagina a como estaban la ultima vez."""
        if documento.zoom > 0 and abs(documento.zoom - 1.0) > 1e-6:
            self._paginas.establecer_zoom(documento.zoom)
        else:
            self._paginas.ajustar_ancho()
        self._paginas.ir_a_pagina(documento.pagina_actual, documento.scroll_y)
        self._al_cambiar_pagina(documento.pagina_actual)

    def guardar_posicion(self) -> None:
        """Persiste pagina, zoom y desplazamiento del documento abierto."""
        if self.documento is None:
            return
        self.contexto.documentos.guardar_posicion(
            self.documento.id,
            pagina=self._paginas.pagina_actual,
            zoom=self._paginas.zoom,
            scroll_y=self._paginas.desplazamiento_en_pagina(),
        )

    def cerrar(self) -> None:
        """Guarda la posicion y suelta el documento."""
        self._guardado.stop()
        self.guardar_posicion()
        self.documento = None

    def _al_volver(self) -> None:
        self.cerrar()
        self.volver.emit()

    # -- Sincronizacion de la interfaz --------------------------------------

    def _ir_a_pagina(self, indice: int) -> None:
        self._paginas.ir_a_pagina(indice)

    def _al_cambiar_pagina(self, indice: int) -> None:
        self._selector.blockSignals(True)
        self._selector.setValue(indice + 1)
        self._selector.blockSignals(False)
        self._panel.marcar_pagina(indice)

    def _al_cambiar_zoom(self, zoom: float) -> None:
        self._zoom.setText(f"{round(zoom * 100)} %")

    def _pintar_hallazgos(self, modelo: object) -> None:
        """Resalta en el lienzo las coincidencias de la busqueda."""
        if not isinstance(modelo, QPdfSearchModel):
            self._paginas.establecer_hallazgos([])
            return

        hallazgos: list[Resaltado] = []
        for fila in range(modelo.rowCount(QModelIndex())):
            enlace = modelo.resultAtIndex(fila)
            if not enlace.isValid():
                continue
            hallazgos.extend(
                Resaltado(enlace.page(), rect, _COLOR_HALLAZGO)
                for rect in enlace.rectangles()
            )
        self._paginas.establecer_hallazgos(hallazgos)

    # -- Anotaciones --------------------------------------------------------

    def _cargar_anotaciones(self) -> None:
        if self.documento is None:
            return
        self._anotaciones = self.contexto.anotaciones.listar(self.documento.id)
        self._paginas.establecer_resaltados(
            [
                Resaltado(a.pagina, QRectF(*rect), a.color)
                for a in self._anotaciones
                for rect in a.rects
                if a.tipo is TipoAnotacion.RESALTADO
            ]
        )
        # Sin filtrar por pagina: la lista es del documento entero y se ordena
        # por pagina, para que se vea todo lo escrito sobre el PDF de una vez.
        self._panel.notas.establecer(
            self._anotaciones,
            self.contexto.servicio_notas.para_documento(self.documento.id),
            self.documento.id,
        )

    def _editar_anotacion(self, anotacion: object) -> None:
        """Edita el comentario sin salir del lector ni perder la pagina."""
        if not isinstance(anotacion, Anotacion):
            return
        dialogo = DialogoNota("Comentario", anotacion.comentario or "", self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        self.contexto.anotaciones.actualizar_comentario(anotacion.id, dialogo.comentario())
        self._cargar_anotaciones()
        self.anotaciones_cambiadas.emit()

    def _eliminar_anotacion(self, anotacion: object) -> None:
        if not isinstance(anotacion, Anotacion):
            return
        respuesta = QMessageBox.question(
            self,
            "Eliminar anotacion",
            "Esta accion no se puede deshacer.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self.contexto.anotaciones.eliminar(anotacion.id)
            self._cargar_anotaciones()
            self.anotaciones_cambiadas.emit()

    def _menu_contextual(self, posicion: QPoint) -> None:
        """Menu sobre la seleccion: destacar, llevar a un cuaderno o copiar.

        Ya no se crean notas ni marcadores anclados al PDF: todo lo que se
        escribe vive en un cuaderno. El resaltado se queda porque no es escribir,
        es marcar la pagina, y sin el una nota diria «pagina 44» sin nada que ver
        al volver alli.
        """
        if self.documento is None:
            return

        menu = QMenu(self)
        pagina = self._paginas.pagina_actual + 1

        if self._paginas.texto_seleccionado:
            menu.addAction("Destacar", lambda: self._crear(TipoAnotacion.RESALTADO))
            menu.addAction("Llevar a un cuaderno…", self._llevar_a_cuaderno)
            menu.addSeparator()
            menu.addAction("Copiar", self._copiar)
        else:
            menu.addAction(
                f"Nota de cuaderno en la pagina {pagina}…", self._nota_en_cuaderno
            )
            menu.addAction("Relacionar una nota…", self._vincular_nota)
        menu.exec(self._paginas.viewport().mapToGlobal(posicion))

    # -- Notas de cuaderno desde el PDF --------------------------------------

    def _nota_en_cuaderno(self) -> None:
        """Nota suelta nueva, ya ligada al PDF y a la pagina que se esta leyendo.

        Se escribe aqui mismo y **no se sale del documento**: saltar a la vista
        Notas cerraria el lector y perderia la pagina, que es justo lo que hace
        util anotar desde dentro. Para editarla a fondo, doble clic en la lista.
        """
        proyecto = self.contexto.proyecto
        if self.documento is None or proyecto is None:
            return

        pagina = self._paginas.pagina_actual
        dialogo = DialogoNota(f"Nota de cuaderno · pagina {pagina + 1}", "", self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        self.contexto.servicio_notas.crear_para_documento(
            proyecto.id, self.documento.id, pagina, cuerpo=dialogo.comentario() or ""
        )
        self._cargar_anotaciones()
        self._traer_notas()
        self.anotaciones_cambiadas.emit()

    def _vincular_nota(self) -> None:
        """Liga una nota que ya existe con la pagina que se esta leyendo."""
        proyecto = self.contexto.proyecto
        if self.documento is None or proyecto is None:
            return

        pagina = self._paginas.pagina_actual
        candidatas = self.contexto.servicio_notas.buscar(proyecto.id)
        ya_ligadas = {
            listada.nota.id
            for listada in self.contexto.servicio_notas.para_documento(
                self.documento.id, pagina
            )
        }
        opciones = [
            (listada.ruta(self.contexto.servicio_notas.titulo_visible(listada.nota)),
             listada.nota.id)
            for listada in candidatas
            if listada.nota.id not in ya_ligadas
        ]
        if not opciones:
            QMessageBox.information(
                self,
                "Relacionar una nota",
                "No hay ninguna nota que no este ya ligada a esta pagina. "
                "Usa «Nota en cuaderno» para crear una nueva.",
            )
            return

        elegida, aceptado = QInputDialog.getItem(
            self,
            "Relacionar una nota",
            f"Ligar con la pagina {pagina + 1}:",
            [etiqueta for etiqueta, _id in opciones],
            0,
            False,
        )
        if not aceptado:
            return
        for etiqueta, identificador in opciones:
            if etiqueta == elegida:
                self.contexto.notas.vincular_documento(
                    identificador, self.documento.id, pagina=pagina
                )
                break
        self._cargar_anotaciones()
        self.anotaciones_cambiadas.emit()

    def _desvincular_nota(self, nota_id: int) -> None:
        """Quita la relacion de una nota con este PDF. La nota no se toca."""
        if self.documento is None:
            return
        for vinculo in self.contexto.notas.vinculos_de(nota_id):
            if vinculo.documento_id == self.documento.id:
                self.contexto.notas.desvincular(vinculo.id)
        self._cargar_anotaciones()
        self.anotaciones_cambiadas.emit()

    def _llevar_a_cuaderno(self) -> None:
        """Crea una nota suelta con la seleccion, ya ligada a este PDF y pagina.

        Se apoya en un resaltado real para que el texto quede tambien marcado en
        la pagina: si no, la nota diria «pagina 44» y no habria nada que ver al
        volver alli.
        """
        proyecto = self.contexto.proyecto
        if self.documento is None or proyecto is None:
            return
        if not self._paginas.texto_seleccionado:
            return

        resaltado = self._crear(TipoAnotacion.RESALTADO)
        if resaltado is None:
            return
        nota = self.contexto.servicio_notas.desde_anotacion(proyecto.id, resaltado)
        self.anotaciones_cambiadas.emit()
        self.abrir_nota.emit(nota.id)

    def _crear(
        self, tipo: TipoAnotacion, *, con_seleccion: bool = True
    ) -> Anotacion | None:
        """Guarda un resaltado a partir de la seleccion actual y lo devuelve.

        Devuelve la anotacion, y no ``None``, porque quien la crea puede
        necesitarla despues: `self._anotaciones` se reordena por pagina al
        recargar, asi que buscar «la ultima» ahi daria otra cualquiera.

        Solo se llama ya con ``RESALTADO``. El parametro ``tipo`` se conserva
        porque las anotaciones antiguas de otros tipos se siguen leyendo y
        editando: lo que desaparece es el camino para crear nuevas.
        """
        if self.documento is None:
            return None

        comentario: str | None = None
        if con_seleccion and self._paginas.pagina_seleccion >= 0:
            pagina = self._paginas.pagina_seleccion
            rects = [
                (r.x(), r.y(), r.width(), r.height()) for r in self._paginas.rects_seleccion()
            ]
            texto = self._paginas.texto_seleccionado
        else:
            pagina, rects, texto = self._paginas.pagina_actual, [], None

        creada = self.contexto.anotaciones.crear(
            self.documento.id,
            tipo=tipo,
            pagina=pagina,
            rects=rects,
            texto_seleccionado=texto,
            comentario=comentario,
            color=_COLOR_RESALTADO if tipo is TipoAnotacion.RESALTADO else tokens.ACENTO,
        )
        self._paginas.limpiar_seleccion()
        self._cargar_anotaciones()
        # Se trae la pestana para que lo recien creado se vea: sin esa
        # confirmacion no hay forma de saber si el clic hizo algo. Lo que ya no
        # se hace es repartir el espacio, que era pisar la eleccion del usuario.
        self._traer_notas()
        self.anotaciones_cambiadas.emit()
        return creada

    def _copiar(self) -> None:
        if texto := self._paginas.texto_seleccionado:
            QGuiApplication.clipboard().setText(texto)

    # -- Navegacion desde fuera ---------------------------------------------

    def ir_a(self, documento: Documento, pagina: int) -> bool:
        """Abre un documento directamente en una pagina concreta."""
        distinto = self.documento is None or self.documento.id != documento.id
        if distinto and not self.abrir(documento):
            return False
        self._ir_a_pagina(pagina)
        return True
