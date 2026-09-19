"""Grafo: prerrequisitos y desbloqueos del proyecto activo.

Es **otra vista del mismo sistema**, no un modulo aparte. Los nodos apuntan a
materias, modulos, hitos y evaluaciones que ya existen; su estado sale del
progreso real, y el doble clic lleva a la seccion donde esa informacion ya vive.

Aqui no se marca nada como completado. Esa decision sigue estando en Progreso,
que es su sitio desde la primera version.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import DestinoNodo
from mukuwareru.nucleo.servicios import CicloError, NodoResuelto
from mukuwareru.ui import iconos
from mukuwareru.ui.grafo import LienzoGrafo, PanelEntidades
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase


class VistaGrafo(VistaBase):
    """Lienzo de dependencias con el panel de entidades sin colocar."""

    titulo = "Grafo"

    # La ventana principal la conecta para llevar al usuario a la seccion que
    # corresponda, igual que hace con `biblioteca.abrir_documento`.
    abrir_entidad = Signal(str, int)     # destino, objeto_id

    def _construir(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
        )
        raiz.setSpacing(tokens.ESPACIO_PEQUENO)
        raiz.addLayout(self._construir_cabecera())

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(tokens.ESPACIO)

        self._panel = PanelEntidades()
        cuerpo.addWidget(self._panel)

        self._lienzo = LienzoGrafo()
        self._lienzo.entidad_soltada.connect(self._al_soltar)
        self._lienzo.nodo_movido.connect(self._al_mover)
        self._lienzo.conexion_creada.connect(self._al_conectar)
        self._lienzo.nodos_borrados.connect(self._al_borrar_nodos)
        self._lienzo.aristas_borradas.connect(self._al_borrar_aristas)
        self._lienzo.nodo_abierto.connect(self._al_abrir)
        self._lienzo.seleccion_cambiada.connect(self._al_seleccionar)
        self._lienzo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._lienzo.customContextMenuRequested.connect(self._menu)
        cuerpo.addWidget(self._lienzo, 1)

        raiz.addLayout(cuerpo, 1)

        self._estado = QLabel()
        self._estado.setObjectName("TextoTenue")
        self._estado.setWordWrap(True)
        raiz.addWidget(self._estado)

    def _construir_cabecera(self) -> QVBoxLayout:
        cabecera = QVBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        fila = QHBoxLayout()
        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        fila.addWidget(titulo)
        fila.addStretch(1)

        encajar = QPushButton("  Encajar")
        encajar.setIcon(iconos.icono("diana", tokens.TEXTO_SUAVE))
        encajar.setToolTip("Encuadra todo el grafo en la ventana")
        encajar.clicked.connect(self._lienzo_encajar)
        fila.addWidget(encajar)

        cien = QPushButton("100 %")
        cien.setToolTip("Vuelve al zoom original")
        cien.clicked.connect(lambda: self._lienzo.restablecer_zoom())
        fila.addWidget(cien)
        cabecera.addLayout(fila)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoSuave")
        cabecera.addWidget(self._resumen)
        return cabecera

    def _lienzo_encajar(self) -> None:
        self._lienzo.encajar()

    # -- Datos --------------------------------------------------------------

    def recargar(self) -> None:
        """Vuelve a resolver el grafo del proyecto activo.

        Se recalcula entero: el estado de los nodos depende del progreso, que
        cambia desde otras vistas. No hay nada cacheado que pueda quedar viejo.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            self._resumen.setText("Sin proyecto seleccionado.")
            self._panel.establecer([])
            return

        grafo = self.contexto.servicio_grafo.cargar(proyecto.id)
        self._lienzo.pintar(grafo)
        self._panel.establecer(self.contexto.servicio_grafo.candidatos(proyecto.id))

        if grafo.vacio:
            self._resumen.setText(
                "Arrastra una materia desde la izquierda para empezar. El nodo "
                "apunta a la materia que ya tienes: no se crea ninguna copia."
            )
        else:
            bloqueados = sum(1 for n in grafo.nodos if n.estado.value == "bloqueado")
            self._resumen.setText(
                f"{len(grafo.nodos)} nodos  ·  {len(grafo.aristas)} prerrequisitos"
                + (f"  ·  {bloqueados} bloqueados" if bloqueados else "")
            )
        self._estado.setText("")

    def _al_cambiar(self) -> None:
        """Repinta esta vista y avisa al resto."""
        self.marcar_sucia()
        self.refrescar_si_hace_falta()
        self.contexto.notificar_cambio(self)

    # -- Acciones del lienzo -------------------------------------------------

    def _al_soltar(self, destino: str, objeto_id: int, x: float, y: float) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        self.contexto.servicio_grafo.agregar(
            proyecto.id, DestinoNodo(destino), objeto_id, x, y
        )
        self._al_cambiar()

    def _al_mover(self, nodo_id: int, x: float, y: float) -> None:
        """Solo persiste la posicion: no hace falta repintar nada."""
        self.contexto.servicio_grafo.mover(nodo_id, x, y)

    def _al_conectar(self, destino: int, origen: int) -> None:
        try:
            self.contexto.servicio_grafo.conectar(destino, origen)
        except CicloError as error:
            # Un ciclo es un gesto que no cabe, no un fallo del usuario: se dice
            # en la linea de estado y se sigue. Un dialogo modal aqui seria un
            # castigo por mover el raton.
            self._estado.setText(str(error))
            return
        self._al_cambiar()

    def _al_borrar_nodos(self, nodos: list[int]) -> None:
        if not confirmar_borrado(self, len(nodos)):
            return
        for nodo_id in nodos:
            self.contexto.servicio_grafo.eliminar(nodo_id)
        self._estado.setText(
            f"{len(nodos)} nodo(s) fuera del grafo. La entidad sigue en su sitio."
        )
        self._al_cambiar()

    def _al_borrar_aristas(self, aristas: list[object]) -> None:
        for par in aristas:
            destino, origen = par  # type: ignore[misc]
            self.contexto.servicio_grafo.desconectar(int(destino), int(origen))
        self._al_cambiar()

    def _al_seleccionar(self, resuelto: object) -> None:
        if not isinstance(resuelto, NodoResuelto):
            self._estado.setText("")
            return
        self._estado.setText(
            f"{resuelto.nombre}  ·  {resuelto.estado.etiqueta}"
            + (
                f"  ·  {resuelto.completados}/{resuelto.total} modulos"
                if resuelto.destino is DestinoNodo.MATERIA and resuelto.total > 1
                else ""
            )
            + "  ·  doble clic para abrir su informacion"
        )

    def _al_abrir(self, nodo_id: int) -> None:
        """Lleva a la seccion donde esa entidad ya vive."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        resuelto = self.contexto.servicio_grafo.cargar(proyecto.id).por_id(nodo_id)
        if resuelto is None:
            return
        self.abrir_entidad.emit(resuelto.destino.value, resuelto.nodo.objeto_id)

    # -- Menu contextual -----------------------------------------------------

    def _menu(self) -> None:
        """Lo que se puede hacer con lo seleccionado."""
        seleccion = self._lienzo.seleccion()
        menu = QMenu(self)

        if len(seleccion) == 1:
            nodo = seleccion[0]
            menu.addAction("Abrir su informacion", lambda: self._al_abrir(nodo.nodo_id))
            menu.addAction(
                "Renombrar en el grafo…", lambda: self._renombrar(nodo.nodo_id)
            )
            self._anadir_menu_o(menu, nodo.nodo_id)
            menu.addSeparator()
            # «Quitar del grafo» y no «Eliminar»: lo segundo sugeriria que se
            # borra la materia, que es justo lo que no pasa.
            menu.addAction(
                "Quitar del grafo", lambda: self._al_borrar_nodos([nodo.nodo_id])
            )
        elif len(seleccion) > 1:
            menu.addAction(
                f"Quitar {len(seleccion)} nodos del grafo",
                lambda: self._al_borrar_nodos([n.nodo_id for n in seleccion]),
            )
        else:
            menu.addAction("Encajar el grafo", self._lienzo_encajar)
            menu.addAction("Zoom al 100 %", self._lienzo.restablecer_zoom)

        menu.exec(self.cursor().pos())

    def _anadir_menu_o(self, menu: QMenu, nodo_id: int) -> None:
        """Submenu para convertir dos prerrequisitos en alternativas.

        Es el unico gesto que hace falta para el O: todo lo demas —Y, varias
        ramas, convergencias— sale de dibujar flechas.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        grafo = self.contexto.servicio_grafo.cargar(proyecto.id)
        entrantes = [a for a in grafo.aristas if a.destino == nodo_id]
        if len(entrantes) < 2:
            return

        submenu = menu.addMenu("Alternar Y / O entre prerrequisitos")
        for primera in entrantes:
            for segunda in entrantes:
                if primera.origen >= segunda.origen:
                    continue
                uno = grafo.por_id(primera.origen)
                otro = grafo.por_id(segunda.origen)
                if uno is None or otro is None:
                    continue
                juntos = primera.grupo == segunda.grupo
                verbo = "Separar" if juntos else "Unir"
                submenu.addAction(
                    f"{verbo}: {uno.nombre} / {otro.nombre}",
                    lambda _=False, a=primera.origen, b=segunda.origen: self._alternar(
                        nodo_id, a, b
                    ),
                )

    def _alternar(self, destino: int, origen_a: int, origen_b: int) -> None:
        if self.contexto.servicio_grafo.alternar_o(destino, origen_a, origen_b):
            self._al_cambiar()

    def _renombrar(self, nodo_id: int) -> None:
        """Alias del nodo dentro del grafo. No renombra la entidad.

        Renombrar la materia de verdad se hace en Progreso: el grafo no puede ser
        una segunda forma de editar el temario sin que se note desde donde.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        resuelto = self.contexto.servicio_grafo.cargar(proyecto.id).por_id(nodo_id)
        if resuelto is None:
            return

        nombre, aceptado = QInputDialog.getText(
            self,
            "Renombrar en el grafo",
            "Nombre para este nodo (vacio para usar el de la entidad):",
            text=resuelto.nodo.etiqueta or "",
        )
        if not aceptado:
            return
        self.contexto.grafo.renombrar_nodo(nodo_id, nombre.strip() or None)
        self._al_cambiar()


def confirmar_borrado(padre: QWidget, cuantos: int) -> bool:
    """Pregunta antes de quitar varios nodos de golpe.

    Uno solo no pregunta: se vuelve a arrastrar en dos segundos. Doce si, porque
    recolocarlos no es gratis.
    """
    if cuantos < 3:
        return True
    respuesta = QMessageBox.question(
        padre,
        "Quitar del grafo",
        f"Se quitaran {cuantos} nodos del lienzo.\n"
        "Las materias, modulos y fechas a las que apuntan no se tocan.",
        QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
        QMessageBox.StandardButton.Cancel,
    )
    return respuesta == QMessageBox.StandardButton.Yes
