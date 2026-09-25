"""Notas: cuadernos, secciones y notas sueltas del proyecto.

El arbol de la izquierda son cuadernos reales con sus secciones —nada de un
cuaderno virtual con los marcadores y resaltados del PDF: eso vive en el
lector, no aqui—.

Tres columnas: arbol, lista y editor. La derecha termina en «Relacionado con»,
que es donde una nota se liga a una materia, un modulo o un PDF concreto. Ese
panel es el interlinkado: sin el, esto seria un bloc de notas.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Nota, TipoAnotacion
from mukuwareru.nucleo.repositorios import NotaListada
from mukuwareru.ui import iconos
from mukuwareru.ui.dialogos.nota import _EditorConImagenes, es_enriquecido
from mukuwareru.ui.dialogos.vincular import DialogoVincular
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import contenedor, vaciar
from mukuwareru.utilidades.texto import primera_linea

_ETIQUETAS_ANOTACION = {
    TipoAnotacion.MARCADOR: ("Marcador", tokens.ACENTO),
    TipoAnotacion.NOTA: ("Nota", tokens.INFO),
    TipoAnotacion.RESALTADO: ("Resaltado", tokens.AVISO),
}

# Guardado perezoso, como el del lector: escribir en cada pulsacion machacaria
# la base de datos, y esperar a un boton pierde texto.
_RETARDO_GUARDADO_MS = 1500

_TODAS = "todas"
_CUADERNO = "cuaderno"
_SECCION = "seccion"


class VistaNotas(VistaBase):
    """Cuadernos y notas sueltas del proyecto."""

    titulo = "Notas"
    dominio = "notas"
    ignora = frozenset({"calendario", "resultados", "sesiones"})
    abrir_en_pagina = Signal(object, int)  # Documento, pagina

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        self._nota_abierta: Nota | None = None
        self._sucio = False
        self._filtro = ""
        self._etiqueta_id: int | None = None
        self._seleccion: tuple[str, Any] = (_TODAS, None)

        self._guardado = QTimer(self)
        self._guardado.setSingleShot(True)
        self._guardado.setInterval(_RETARDO_GUARDADO_MS)
        self._guardado.timeout.connect(self.guardar_pendiente)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE, tokens.ESPACIO
        )
        raiz.setSpacing(tokens.ESPACIO_PEQUENO)
        raiz.addLayout(self._cabecera())

        division = QSplitter(Qt.Orientation.Horizontal)
        division.addWidget(self._panel_arbol())
        division.addWidget(self._panel_lista())
        division.addWidget(self._panel_editor())
        division.setStretchFactor(0, 0)
        division.setStretchFactor(1, 0)
        division.setStretchFactor(2, 1)
        division.setSizes([220, 300, 520])
        raiz.addWidget(division, 1)

    def _cabecera(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        fila.addWidget(titulo)
        fila.addStretch(1)

        self._combo_etiqueta = QComboBox()
        self._combo_etiqueta.setFixedWidth(160)
        self._combo_etiqueta.currentIndexChanged.connect(self._al_cambiar_etiqueta)
        fila.addWidget(self._combo_etiqueta)

        self._buscador = QLineEdit()
        self._buscador.setPlaceholderText("Buscar en las notas…")
        self._buscador.setClearButtonEnabled(True)
        self._buscador.setFixedWidth(240)
        self._buscador.textChanged.connect(self._al_buscar)
        fila.addWidget(self._buscador)

        nueva = QPushButton("  Nota nueva")
        nueva.setObjectName("BotonPrimario")
        nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        nueva.setIcon(iconos.icono("mas", tokens.TEXTO))
        nueva.clicked.connect(self.nueva_nota)
        fila.addWidget(nueva)
        return fila

    def _panel_arbol(self) -> QWidget:
        self._arbol = QTreeWidget()
        self._arbol.setHeaderHidden(True)
        self._arbol.setMinimumWidth(180)
        self._arbol.currentItemChanged.connect(self._al_elegir_nodo)
        self._arbol.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._arbol.customContextMenuRequested.connect(self._menu_arbol)

        nuevo = QPushButton("  Cuaderno nuevo")
        nuevo.setCursor(Qt.CursorShape.PointingHandCursor)
        nuevo.setIcon(iconos.icono("mas", tokens.TEXTO_TENUE))
        nuevo.clicked.connect(self._nuevo_cuaderno)

        columna = QVBoxLayout()
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(tokens.ESPACIO_PEQUENO)
        columna.addWidget(self._arbol, 1)
        columna.addWidget(nuevo)
        return contenedor(columna)

    def _panel_lista(self) -> QWidget:
        self._lista = QListWidget()
        self._lista.setMinimumWidth(240)
        self._lista.setWordWrap(True)
        self._lista.currentItemChanged.connect(self._al_elegir_elemento)
        self._lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._lista.customContextMenuRequested.connect(self._menu_lista)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoTenue")

        columna = QVBoxLayout()
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(tokens.ESPACIO_PEQUENO)
        columna.addWidget(self._lista, 1)
        columna.addWidget(self._resumen)
        return contenedor(columna)

    def _panel_editor(self) -> QWidget:
        self._titulo_nota = QLineEdit()
        self._titulo_nota.setPlaceholderText("Titulo (se deduce solo si lo dejas vacio)")
        self._titulo_nota.textEdited.connect(self._al_editar)

        self._editor = _EditorConImagenes()
        self._editor.setAcceptRichText(True)
        self._editor.setPlaceholderText(
            "Escribe aqui. Puedes pegar imagenes con Ctrl+V."
        )
        self._editor.textChanged.connect(self._al_editar)

        enlazar = QPushButton("  Relacionar con…")
        enlazar.setCursor(Qt.CursorShape.PointingHandCursor)
        enlazar.setIcon(iconos.icono("mas", tokens.TEXTO_TENUE))
        enlazar.clicked.connect(self._menu_enlazar)
        self._boton_enlazar = enlazar

        cabecera_enlaces = QHBoxLayout()
        titulo_enlaces = QLabel("Relacionado con")
        titulo_enlaces.setProperty("fuerte", True)
        cabecera_enlaces.addWidget(titulo_enlaces)
        cabecera_enlaces.addStretch(1)
        cabecera_enlaces.addWidget(enlazar)

        self._caja_enlaces = QVBoxLayout()
        self._caja_enlaces.setSpacing(2)

        columna = QVBoxLayout()
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(tokens.ESPACIO_PEQUENO)
        columna.addWidget(self._titulo_nota)
        columna.addWidget(self._editor, 1)
        columna.addLayout(cabecera_enlaces)
        columna.addLayout(self._caja_enlaces)
        self._panel_derecho = contenedor(columna)
        return self._panel_derecho

    # -- Recarga ------------------------------------------------------------

    def recargar(self) -> None:
        """Reconstruye el arbol, la lista y el editor del proyecto activo."""
        self.guardar_pendiente()
        proyecto = self.contexto.proyecto
        self._arbol.clear()
        if proyecto is None:
            self._lista.clear()
            self._resumen.setText("Sin proyecto seleccionado.")
            self._mostrar_editor(False)
            return

        self._cargar_etiquetas(proyecto.id)
        self._cargar_arbol(proyecto.id)
        self._cargar_lista()

    def _cargar_etiquetas(self, proyecto_id: int) -> None:
        anterior = self._etiqueta_id
        self._combo_etiqueta.blockSignals(True)
        self._combo_etiqueta.clear()
        self._combo_etiqueta.addItem("Todas las etiquetas", None)
        cuentas = self.contexto.etiquetas.conteo(proyecto_id)
        for etiqueta in self.contexto.etiquetas.listar(proyecto_id):
            self._combo_etiqueta.addItem(
                f"{etiqueta.nombre} ({cuentas.get(etiqueta.id, 0)})", etiqueta.id
            )
        indice = self._combo_etiqueta.findData(anterior)
        self._combo_etiqueta.setCurrentIndex(max(0, indice))
        self._etiqueta_id = self._combo_etiqueta.currentData()
        self._combo_etiqueta.blockSignals(False)

    def _cargar_arbol(self, proyecto_id: int) -> None:
        self._arbol.blockSignals(True)
        self._arbol.clear()

        total = self.contexto.notas.contar(proyecto_id)
        todas = QTreeWidgetItem([f"Todas las notas ({total})"])
        todas.setData(0, Qt.ItemDataRole.UserRole, (_TODAS, None))
        todas.setIcon(0, iconos.icono("nota", tokens.TEXTO_SUAVE))
        self._arbol.addTopLevelItem(todas)

        for nodo in self.contexto.servicio_notas.arbol(proyecto_id):
            raiz = QTreeWidgetItem([f"{nodo.cuaderno.nombre} ({nodo.total})"])
            raiz.setData(0, Qt.ItemDataRole.UserRole, (_CUADERNO, nodo.cuaderno.id))
            raiz.setIcon(0, iconos.icono("libro", nodo.cuaderno.color or tokens.TEXTO_SUAVE))
            for seccion, cuenta in nodo.secciones:
                hijo = QTreeWidgetItem([f"{seccion.nombre} ({cuenta})"])
                hijo.setData(0, Qt.ItemDataRole.UserRole, (_SECCION, seccion.id))
                raiz.addChild(hijo)
            self._arbol.addTopLevelItem(raiz)
            raiz.setExpanded(True)

        self._restaurar_seleccion()
        self._arbol.blockSignals(False)

    def _restaurar_seleccion(self) -> None:
        """Vuelve al nodo que estaba elegido; si desaparecio, a «Todas»."""
        for indice in range(self._arbol.topLevelItemCount()):
            elemento = self._arbol.topLevelItem(indice)
            if self._buscar_nodo(elemento):
                return
        self._arbol.setCurrentItem(self._arbol.topLevelItem(0))
        self._seleccion = (_TODAS, None)

    def _buscar_nodo(self, elemento: QTreeWidgetItem) -> bool:
        if elemento.data(0, Qt.ItemDataRole.UserRole) == self._seleccion:
            self._arbol.setCurrentItem(elemento)
            return True
        return any(
            self._buscar_nodo(elemento.child(i)) for i in range(elemento.childCount())
        )

    def _cargar_lista(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return

        self._lista.blockSignals(True)
        self._lista.clear()
        clase, valor = self._seleccion
        self._llenar_con_notas(proyecto.id, clase, valor)

        self._lista.blockSignals(False)
        if self._lista.count():
            self._lista.setCurrentRow(0)
        else:
            self._mostrar_editor(False)

    def _llenar_con_notas(self, proyecto_id: int, clase: str, valor: Any) -> None:
        encontradas = self.contexto.servicio_notas.buscar(
            proyecto_id,
            self._filtro,
            cuaderno_id=valor if clase == _CUADERNO else None,
            seccion_id=valor if clase == _SECCION else None,
            etiqueta_id=self._etiqueta_id,
        )
        for listada in encontradas:
            self._lista.addItem(_elemento_de_nota(listada))
        self._resumen.setText(
            f"{len(encontradas)} notas" if encontradas else "Nada por aqui todavia."
        )

    # -- Seleccion ----------------------------------------------------------

    def _al_elegir_nodo(
        self, actual: QTreeWidgetItem | None, _previo: QTreeWidgetItem | None
    ) -> None:
        if actual is None:
            return
        self.guardar_pendiente()
        self._seleccion = actual.data(0, Qt.ItemDataRole.UserRole)
        self._cargar_lista()

    def _al_elegir_elemento(
        self, actual: QListWidgetItem | None, _previo: QListWidgetItem | None
    ) -> None:
        self.guardar_pendiente()
        if actual is None:
            self._mostrar_editor(False)
            return
        self._abrir_nota(int(actual.data(Qt.ItemDataRole.UserRole)))

    def _abrir_nota(self, nota_id: int) -> None:
        nota = self.contexto.notas.obtener(nota_id)
        if nota is None:
            self._mostrar_editor(False)
            return

        self._nota_abierta = nota
        self._titulo_nota.blockSignals(True)
        self._editor.blockSignals(True)
        self._titulo_nota.setText(nota.titulo)
        if es_enriquecido(nota.cuerpo):
            self._editor.setHtml(nota.cuerpo)
        else:
            self._editor.setPlainText(nota.cuerpo)
        self._titulo_nota.blockSignals(False)
        self._editor.blockSignals(False)
        self._sucio = False

        self._mostrar_editor(True)
        self._pintar_enlaces()

    def _mostrar_editor(self, con_nota: bool) -> None:
        self._titulo_nota.setVisible(con_nota)
        self._editor.setVisible(con_nota)
        self._boton_enlazar.setEnabled(con_nota)
        if not con_nota:
            self._nota_abierta = None
            self._vaciar_enlaces()

    # -- Guardado -----------------------------------------------------------

    def _al_editar(self) -> None:
        if self._nota_abierta is None:
            return
        self._sucio = True
        self._guardado.start()

    def guardar_pendiente(self) -> None:
        """Vuelca al disco la nota en curso, si cambio algo.

        Se llama al cambiar de nota, al cambiar de nodo, al recargar y al salir
        de la vista: cualquier camino por el que el texto podria perderse.
        """
        self._guardado.stop()
        if not self._sucio or self._nota_abierta is None:
            return

        cuerpo = self._editor.toHtml() if "<img" in self._editor.toHtml() else (
            self._editor.toPlainText()
        )
        guardada = self.contexto.servicio_notas.guardar(
            self._nota_abierta.id, titulo=self._titulo_nota.text(), cuerpo=cuerpo
        )
        self._sucio = False
        if guardada is not None:
            self._nota_abierta = guardada
            # El titulo puede haberse deducido del cuerpo: que se vea.
            if self._titulo_nota.text() != guardada.titulo:
                self._titulo_nota.blockSignals(True)
                self._titulo_nota.setText(guardada.titulo)
                self._titulo_nota.blockSignals(False)
            self._refrescar_titulo_en_lista(guardada)
        self.contexto.notificar_cambio(self)

    def _refrescar_titulo_en_lista(self, nota: Nota) -> None:
        """Actualiza el elemento de la lista sin reconstruirla entera.

        Reconstruirla moveria la seleccion y el foco mientras se escribe.
        """
        elemento = self._lista.currentItem()
        if elemento is not None and elemento.data(Qt.ItemDataRole.UserRole) == nota.id:
            elemento.setText(
                f"{self.contexto.servicio_notas.titulo_visible(nota)}\n"
                f"{primera_linea(nota.cuerpo_plano, 60)}"
            )

    def hideEvent(self, event: object) -> None:  # noqa: N802 (API de Qt)
        self.guardar_pendiente()
        super().hideEvent(event)  # type: ignore[arg-type]

    # -- Acciones sobre notas ------------------------------------------------

    def nueva_nota(self) -> None:
        """Crea una nota en la seccion elegida (o la de por defecto) y la abre."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        self.guardar_pendiente()

        clase, valor = self._seleccion
        if clase == _SECCION:
            nota = self.contexto.notas.crear(int(valor))
        else:
            # Sin seccion elegida cae en la de por defecto: una nota rapida no
            # debe obligar a decidir donde va.
            nota = self.contexto.servicio_notas.crear_rapida(proyecto.id)

        self.contexto.notificar_cambio(self)
        self.recargar()
        self._elegir_en_lista(nota.id)
        self._titulo_nota.setFocus()

    def mostrar_nota(self, nota_id: int) -> None:
        """Deja abierta una nota concreta. La usa el lector al saltar aqui.

        Se cae a «Todas las notas» porque la nota puede estar en un cuaderno
        distinto del que estuviera elegido, y entonces no apareceria en la lista.
        """
        self._seleccion = (_TODAS, None)
        self._filtro = ""
        self._buscador.blockSignals(True)
        self._buscador.clear()
        self._buscador.blockSignals(False)
        self.recargar()
        self._elegir_en_lista(nota_id)

    def _elegir_en_lista(self, nota_id: int) -> None:
        for fila in range(self._lista.count()):
            elemento = self._lista.item(fila)
            if elemento.data(Qt.ItemDataRole.UserRole) == nota_id:
                self._lista.setCurrentRow(fila)
                return

    def _menu_lista(self) -> None:
        elemento = self._lista.currentItem()
        if elemento is None:
            return
        menu = QMenu(self)
        menu.addAction("Etiquetas…", self._editar_etiquetas)
        menu.addAction("Mover a…", self._mover_nota)
        menu.addSeparator()
        menu.addAction("Eliminar nota", self._eliminar_nota)
        menu.exec(self.cursor().pos())

    def _eliminar_nota(self) -> None:
        if self._nota_abierta is None:
            return
        titulo = self.contexto.servicio_notas.titulo_visible(self._nota_abierta)
        if not _confirmar(self, "Eliminar nota", f"¿Eliminar «{titulo}»?"):
            return
        self._sucio = False
        self.contexto.notas.eliminar(self._nota_abierta.id)
        self._nota_abierta = None
        self.contexto.notificar_cambio(self)
        self.recargar()

    def _mover_nota(self) -> None:
        proyecto = self.contexto.proyecto
        if self._nota_abierta is None or proyecto is None:
            return
        destinos = [
            (f"{nodo.cuaderno.nombre} · {seccion.nombre}", seccion.id)
            for nodo in self.contexto.servicio_notas.arbol(proyecto.id)
            for seccion, _cuenta in nodo.secciones
        ]
        elegido = _elegir(self, "Mover nota", "Llevar a la seccion:", destinos)
        if elegido is None:
            return
        self.guardar_pendiente()
        self.contexto.notas.mover(self._nota_abierta.id, int(elegido))
        self.contexto.notificar_cambio(self)
        self.recargar()

    def _editar_etiquetas(self) -> None:
        proyecto = self.contexto.proyecto
        if self._nota_abierta is None or proyecto is None:
            return
        actuales = self.contexto.etiquetas.listar(proyecto.id)
        por_id = {e.id: e.nombre for e in actuales}
        texto = ", ".join(por_id[i] for i in self._nota_abierta.etiquetas if i in por_id)

        nuevo, aceptado = QInputDialog.getText(
            self,
            "Etiquetas",
            "Separadas por comas. Las que no existan se crean solas.",
            text=texto,
        )
        if not aceptado:
            return

        nombres = [t.strip() for t in nuevo.split(",") if t.strip()]
        ids = [
            self.contexto.etiquetas.obtener_o_crear(proyecto.id, nombre).id
            for nombre in nombres
        ]
        self.contexto.notas.etiquetar(self._nota_abierta.id, ids)
        self.contexto.notificar_cambio(self)
        self.recargar()

    # -- Relacionado con -----------------------------------------------------

    def _vaciar_enlaces(self) -> None:
        vaciar(self._caja_enlaces)

    def _pintar_enlaces(self) -> None:
        """Pinta los vinculos de la nota abierta como filas con boton de quitar."""
        self._vaciar_enlaces()
        if self._nota_abierta is None:
            aviso = QLabel("Las anotaciones ya estan ligadas a su PDF y su pagina.")
            aviso.setObjectName("TextoTenue")
            aviso.setWordWrap(True)
            self._caja_enlaces.addWidget(aviso)
            return

        contexto = self.contexto.servicio_notas.contexto(self._nota_abierta.id)
        if contexto.vacio:
            aviso = QLabel(
                "Sin relacionar. Ligala a una materia, a un modulo o al PDF y a la "
                "pagina de la que habla."
            )
            aviso.setObjectName("TextoTenue")
            aviso.setWordWrap(True)
            self._caja_enlaces.addWidget(aviso)
            return

        vinculos = {v.objeto_id: v for v in self._nota_abierta.vinculos}
        for materia in contexto.materias:
            self._fila_enlace("Materia", materia.nombre, vinculos.get(materia.id))
        for modulo, padre in contexto.modulos:
            self._fila_enlace("Modulo", f"{padre} · {modulo.nombre}", vinculos.get(modulo.id))
        for documento, pagina in contexto.documentos:
            destino = documento.nombre + (
                f" · pagina {pagina + 1}" if pagina is not None else " · documento entero"
            )
            self._fila_enlace(
                "PDF", destino, vinculos.get(documento.id), documento, pagina
            )
        for anotacion, nombre in contexto.anotaciones:
            etiqueta, _color = _ETIQUETAS_ANOTACION[anotacion.tipo]
            self._fila_enlace(
                etiqueta,
                f"{nombre} · pagina {anotacion.pagina + 1}",
                vinculos.get(anotacion.id),
            )

    def _fila_enlace(
        self,
        clase: str,
        texto: str,
        vinculo: object,
        documento: object = None,
        pagina: int | None = None,
    ) -> None:
        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        insignia = QLabel(clase)
        insignia.setObjectName("TextoTenue")
        insignia.setFixedWidth(64)
        fila.addWidget(insignia)

        if documento is not None:
            enlace = QPushButton(texto)
            enlace.setFlat(True)
            enlace.setCursor(Qt.CursorShape.PointingHandCursor)
            enlace.setStyleSheet(f"text-align: left; color: {tokens.INFO};")
            enlace.clicked.connect(
                lambda _m=False, d=documento, p=pagina: self.abrir_en_pagina.emit(d, p or 0)
            )
            fila.addWidget(enlace, 1)
        else:
            etiqueta = QLabel(texto)
            etiqueta.setWordWrap(True)
            fila.addWidget(etiqueta, 1)

        quitar = QPushButton("Quitar")
        quitar.setFixedWidth(64)
        quitar.setToolTip("Quitar la relacion. Ni la nota ni el destino se borran.")
        quitar.setCursor(Qt.CursorShape.PointingHandCursor)
        identificador = getattr(vinculo, "id", None)
        quitar.setEnabled(identificador is not None)
        quitar.clicked.connect(lambda _m=False, i=identificador: self._desvincular(i))
        fila.addWidget(quitar)

        self._caja_enlaces.addWidget(contenedor(fila))

    def _desvincular(self, vinculo_id: int | None) -> None:
        if vinculo_id is None or self._nota_abierta is None:
            return
        self.contexto.notas.desvincular(vinculo_id)
        self._abrir_nota(self._nota_abierta.id)
        self.contexto.notificar_cambio(self)

    def _menu_enlazar(self) -> None:
        """Un solo dialogo para los tres destinos, con la materia filtrando.

        Antes eran tres acciones separadas y la de modulo listaba los 75 del
        proyecto en plano, con lo que era facil ligar una nota de Ethics a un
        modulo de Corporate Issuers sin notarlo.
        """
        proyecto = self.contexto.proyecto
        if self._nota_abierta is None or proyecto is None:
            return

        materias, modulos, documentos = (
            self.contexto.servicio_notas.catalogo_para_vincular(proyecto.id)
        )
        dialogo = DialogoVincular(
            materias,
            modulos,
            documentos,
            materia_sugerida=self._materia_de_la_nota(),
            parent=self,
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        destino = dialogo.destino()
        if destino is None:
            return

        self.contexto.servicio_notas.vincular(
            self._nota_abierta.id, destino.clase, destino.objeto_id, destino.pagina
        )
        self._abrir_nota(self._nota_abierta.id)
        self.contexto.notificar_cambio(self)

    def _materia_de_la_nota(self) -> int | None:
        """Materia con la que ya esta relacionada la nota, si hay alguna.

        Se ofrece como valor inicial del filtro: lo normal es seguir ligando la
        nota a cosas de la misma materia.
        """
        if self._nota_abierta is None:
            return None
        for vinculo in self._nota_abierta.vinculos:
            if vinculo.materia_id is not None:
                return vinculo.materia_id
        for vinculo in self._nota_abierta.vinculos:
            if vinculo.modulo_id is None:
                continue
            modulo = self.contexto.modulos.obtener(vinculo.modulo_id)
            if modulo is not None:
                return modulo.materia_id
        return None

    # -- Arbol ---------------------------------------------------------------

    def _nuevo_cuaderno(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        nombre, aceptado = QInputDialog.getText(self, "Cuaderno nuevo", "Nombre:")
        if not aceptado or not nombre.strip():
            return
        cuaderno = self.contexto.cuadernos.crear(proyecto.id, nombre.strip())
        # Un cuaderno sin secciones no puede contener nada: nace con la suya.
        self.contexto.cuadernos.crear_seccion(cuaderno.id, "General")
        self.contexto.notificar_cambio(self)
        self.recargar()

    def _menu_arbol(self) -> None:
        elemento = self._arbol.currentItem()
        if elemento is None:
            return
        clase, valor = elemento.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)

        if clase == _CUADERNO:
            menu.addAction("Seccion nueva…", lambda: self._nueva_seccion(int(valor)))
            menu.addAction("Renombrar…", lambda: self._renombrar_cuaderno(int(valor)))
            menu.addSeparator()
            menu.addAction("Eliminar cuaderno", lambda: self._eliminar_cuaderno(int(valor)))
        elif clase == _SECCION:
            menu.addAction("Renombrar…", lambda: self._renombrar_seccion(int(valor)))
            menu.addSeparator()
            menu.addAction("Eliminar seccion", lambda: self._eliminar_seccion(int(valor)))
        else:
            return
        menu.exec(self.cursor().pos())

    def _nueva_seccion(self, cuaderno_id: int) -> None:
        nombre, aceptado = QInputDialog.getText(self, "Seccion nueva", "Nombre:")
        if aceptado and nombre.strip():
            self.contexto.cuadernos.crear_seccion(cuaderno_id, nombre.strip())
            self.contexto.notificar_cambio(self)
            self.recargar()

    def _renombrar_cuaderno(self, cuaderno_id: int) -> None:
        cuaderno = self.contexto.cuadernos.obtener(cuaderno_id)
        if cuaderno is None:
            return
        nombre, aceptado = QInputDialog.getText(
            self, "Renombrar cuaderno", "Nombre:", text=cuaderno.nombre
        )
        if aceptado and nombre.strip():
            self.contexto.cuadernos.renombrar(cuaderno_id, nombre.strip())
            self.contexto.notificar_cambio(self)
            self.recargar()

    def _renombrar_seccion(self, seccion_id: int) -> None:
        seccion = self.contexto.cuadernos.obtener_seccion(seccion_id)
        if seccion is None:
            return
        nombre, aceptado = QInputDialog.getText(
            self, "Renombrar seccion", "Nombre:", text=seccion.nombre
        )
        if aceptado and nombre.strip():
            self.contexto.cuadernos.renombrar_seccion(seccion_id, nombre.strip())
            self.contexto.notificar_cambio(self)
            self.recargar()

    def _eliminar_cuaderno(self, cuaderno_id: int) -> None:
        cuaderno = self.contexto.cuadernos.obtener(cuaderno_id)
        if cuaderno is None:
            return
        if not _confirmar(
            self,
            "Eliminar cuaderno",
            f"¿Eliminar «{cuaderno.nombre}» con todas sus secciones y sus notas?",
        ):
            return
        self.contexto.cuadernos.eliminar(cuaderno_id)
        self._seleccion = (_TODAS, None)
        self.contexto.notificar_cambio(self)
        self.recargar()

    def _eliminar_seccion(self, seccion_id: int) -> None:
        seccion = self.contexto.cuadernos.obtener_seccion(seccion_id)
        if seccion is None:
            return
        if self.contexto.cuadernos.contar_secciones(seccion.cuaderno_id) <= 1:
            QMessageBox.information(
                self,
                "Ultima seccion",
                "Un cuaderno necesita al menos una seccion. "
                "Elimina el cuaderno entero si es lo que quieres.",
            )
            return
        if not _confirmar(
            self,
            "Eliminar seccion",
            f"¿Eliminar «{seccion.nombre}» con todas sus notas?",
        ):
            return
        self.contexto.cuadernos.eliminar_seccion(seccion_id)
        self._seleccion = (_TODAS, None)
        self.contexto.notificar_cambio(self)
        self.recargar()

    # -- Filtros -------------------------------------------------------------

    def _al_buscar(self, texto: str) -> None:
        self._filtro = texto.strip()
        self._cargar_lista()

    def _al_cambiar_etiqueta(self, _indice: int) -> None:
        self._etiqueta_id = self._combo_etiqueta.currentData()
        self._cargar_lista()


def _elemento_de_nota(listada: NotaListada) -> QListWidgetItem:
    """Una nota con su ruta completa: cuaderno, seccion, titulo y con que se liga.

    La ruta va en la propia fila y no en un tooltip: saber donde vive una nota y
    de que habla es justo lo que uno busca al recorrer la lista, y tener que
    abrirlas una a una para averiguarlo es lo que hacia falta arreglar.
    """
    nota = listada.nota
    titulo = nota.titulo.strip() or primera_linea(nota.cuerpo_plano) or "Nota sin titulo"
    elemento = QListWidgetItem(
        f"{listada.ruta(titulo)}\n{primera_linea(nota.cuerpo_plano, 70)}"
    )
    elemento.setData(Qt.ItemDataRole.UserRole, nota.id)
    if listada.destinos:
        elemento.setToolTip("Relacionada con: " + ", ".join(listada.destinos))
    else:
        elemento.setToolTip("Sin relacionar todavia.")
    return elemento


def _confirmar(padre: QWidget, titulo: str, mensaje: str) -> bool:
    """Pregunta con Cancelar por defecto. Borrar no debe salir de un Enter."""
    respuesta = QMessageBox.question(
        padre,
        titulo,
        mensaje,
        QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
        QMessageBox.StandardButton.Cancel,
    )
    return respuesta == QMessageBox.StandardButton.Yes


def _elegir(
    padre: QWidget, titulo: str, mensaje: str, opciones: list[tuple[str, int]]
) -> int | None:
    """Pide elegir de una lista y devuelve el id, o ``None`` si se cancela."""
    if not opciones:
        QMessageBox.information(padre, titulo, "No hay nada entre lo que elegir todavia.")
        return None
    etiquetas = [etiqueta for etiqueta, _id in opciones]
    elegida, aceptado = QInputDialog.getItem(padre, titulo, mensaje, etiquetas, 0, False)
    if not aceptado:
        return None
    for etiqueta, identificador in opciones:
        if etiqueta == elegida:
            return identificador
    return None
