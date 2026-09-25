"""Barra lateral: seleccion de proyecto y navegacion entre secciones.

Ni los proyectos ni las secciones estan escritos a mano. Los proyectos salen de
la base de datos y las secciones del catalogo ``SECCIONES`` cruzado con la
disposicion que el usuario haya guardado, asi que las dos listas se reconstruyen
con ``recargar_proyectos()`` y ``recargar_secciones()``.

Esta clase no escribe nada: emite senales y deja que la ventana principal
decida. Renombrar un proyecto puede mover una carpeta del disco, y eso es cosa
de ``ServicioProyectos``, no de una barra de botones.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.modelos import Hito, Proyecto
from mukuwareru.nucleo.servicios import Estado, Fase
from mukuwareru.ui import iconos
from mukuwareru.ui.pomodoro.reloj_compacto import PiezasReloj
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas import SECCIONES
from mukuwareru.ui.widgets import contenedor
from mukuwareru.utilidades import formato


class BarraLateral(QWidget):
    """Columna izquierda fija: proyectos arriba, secciones debajo.

    No conoce las vistas: emite ``seccion_elegida`` con la clave y deja que la
    ventana principal decida.
    """

    seccion_elegida = Signal(str)
    proyecto_elegido = Signal(object)   # Proyecto
    nuevo_proyecto = Signal()
    editar_proyecto = Signal(object)    # Proyecto
    mover_proyecto = Signal(object, int)  # Proyecto, desplazamiento (-1 / +1)
    archivar_proyecto = Signal(object)  # Proyecto
    eliminar_proyecto = Signal(object)  # Proyecto
    personalizar_pedido = Signal()
    pomodoro_alternado = Signal()
    pomodoro_detenido = Signal()
    ocultar_pedido = Signal()

    def __init__(self, contexto: Contexto, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BarraLateral")
        self.setFixedWidth(tokens.ANCHO_LATERAL)
        self.contexto = contexto

        self._botones_proyecto: dict[int, QPushButton] = {}
        self._botones_seccion: dict[str, QPushButton] = {}
        self._grupo_proyectos = QButtonGroup(self)
        self._grupo_proyectos.setExclusive(True)
        self._grupo_secciones = QButtonGroup(self)
        self._grupo_secciones.setExclusive(True)
        self._colapsada = False
        self._pomodoro_corriendo = False

        self._construir()
        contexto.proyecto_cambiado.connect(self._al_cambiar_proyecto)
        # Crear un hito mas cercano desde el Calendario tiene que mover la
        # cuenta atras sin esperar a cambiar de proyecto.
        contexto.datos_cambiados.connect(self._al_cambiar_datos)

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(12, 16, 12, 12)
        raiz.setSpacing(tokens.ESPACIO_PEQUENO)

        raiz.addWidget(self._cabecera())
        raiz.addSpacing(tokens.ESPACIO)

        self._etiqueta_proyectos = _etiqueta_seccion("PROYECTOS")
        raiz.addWidget(self._etiqueta_proyectos)
        self._caja_proyectos = QVBoxLayout()
        self._caja_proyectos.setSpacing(2)
        raiz.addLayout(self._caja_proyectos)

        self._boton_nuevo = QPushButton()
        self._boton_nuevo.setObjectName("BotonNuevoProyecto")
        self._boton_nuevo.setIcon(iconos.icono("mas", tokens.TEXTO_TENUE))
        self._boton_nuevo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_nuevo.clicked.connect(self.nuevo_proyecto.emit)
        self._aplicar_texto(self._boton_nuevo, "  Nuevo proyecto")
        raiz.addWidget(self._boton_nuevo)

        raiz.addSpacing(tokens.ESPACIO)
        self._separador = _separador()
        raiz.addWidget(self._separador)
        raiz.addSpacing(tokens.ESPACIO_PEQUENO)

        self._caja_secciones = QVBoxLayout()
        self._caja_secciones.setSpacing(2)
        raiz.addLayout(self._caja_secciones)
        self.recargar_secciones()

        raiz.addStretch(1)
        self._mini_pomodoro = _MiniPomodoroBarra()
        self._mini_pomodoro.alternar_pedido.connect(self.pomodoro_alternado.emit)
        self._mini_pomodoro.detener_pedido.connect(self.pomodoro_detenido.emit)
        # Clic en el reloj: a la seccion Pomodoro, como el doble clic del flotante.
        self._mini_pomodoro.ir_pedido.connect(lambda: self.seccion_elegida.emit("pomodoro"))
        raiz.addWidget(self._mini_pomodoro)
        raiz.addSpacing(tokens.ESPACIO_PEQUENO)
        self._tarjeta_examen = _TarjetaExamen()
        raiz.addWidget(self._tarjeta_examen)

    def _cabecera(self) -> QWidget:
        fila = QHBoxLayout()
        fila.setContentsMargins(2, 0, 0, 0)
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(0)

        titulo = QLabel("Mukuwareru")
        titulo.setObjectName("TituloApp")
        textos.addWidget(titulo)

        self._subtitulo = QLabel("Sin proyecto")
        self._subtitulo.setObjectName("SubtituloApp")
        textos.addWidget(self._subtitulo)

        self._caja_titulos = contenedor(textos)
        fila.addWidget(self._caja_titulos, 1)

        # Los chevrones son tipograficos a proposito: "<" y ">" se ven como
        # signos de comparacion en el boton, no como una flecha.
        self._boton_colapsar = QPushButton("‹")  # noqa: RUF001
        self._boton_colapsar.setObjectName("BotonColapsar")
        self._boton_colapsar.setFixedSize(22, 22)
        self._boton_colapsar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_colapsar.setToolTip("Contraer la barra lateral")
        self._boton_colapsar.clicked.connect(self.alternar_colapso)
        fila.addWidget(self._boton_colapsar)

        self._boton_ocultar = QPushButton("×")  # noqa: RUF001 (aspa, no una equis)
        self._boton_ocultar.setObjectName("BotonColapsar")
        self._boton_ocultar.setFixedSize(22, 22)
        self._boton_ocultar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_ocultar.setToolTip("Ocultar la barra lateral (Ctrl+B)")
        self._boton_ocultar.clicked.connect(self.ocultar_pedido.emit)
        fila.addWidget(self._boton_ocultar)

        return contenedor(fila)

    # -- Colapso --------------------------------------------------------------

    def _aplicar_texto(self, boton: QPushButton, texto_completo: str) -> None:
        """Guarda el texto completo del boton y lo muestra u oculta segun el colapso."""
        boton.setProperty("texto_completo", texto_completo)
        if self._colapsada:
            boton.setText("")
            boton.setToolTip(texto_completo.strip())
        else:
            boton.setText(texto_completo)
            boton.setToolTip("")

    def alternar_colapso(self) -> None:
        """Contrae la barra a solo iconos, o la devuelve a su ancho completo."""
        self.aplicar_colapso(not self._colapsada)

    def aplicar_colapso(self, colapsada: bool) -> None:
        """Deja la barra colapsada o completa. Idempotente, para restaurar estado."""
        self._colapsada = colapsada
        self.setFixedWidth(
            tokens.ANCHO_LATERAL_COLAPSADA if self._colapsada else tokens.ANCHO_LATERAL
        )
        self._boton_colapsar.setText("›" if self._colapsada else "‹")  # noqa: RUF001
        self._boton_colapsar.setToolTip(
            "Expandir la barra lateral" if self._colapsada else "Contraer la barra lateral"
        )
        self._caja_titulos.setVisible(not self._colapsada)
        self._etiqueta_proyectos.setVisible(not self._colapsada)
        self._separador.setVisible(not self._colapsada)
        # Colapsada no queda sitio para dos botones de 22 px con el chevron.
        self._boton_ocultar.setVisible(not self._colapsada)

        for boton in (*self._botones_proyecto.values(), *self._botones_seccion.values()):
            self._aplicar_texto(boton, boton.property("texto_completo") or "")
        self._aplicar_texto(self._boton_nuevo, "  Nuevo proyecto")

        self.refrescar_cuenta_atras()
        self._mini_pomodoro.setVisible(self._pomodoro_corriendo and not self._colapsada)

    @property
    def colapsada(self) -> bool:
        """Si la barra esta reducida a iconos."""
        return self._colapsada

    # -- Proyectos ----------------------------------------------------------

    def recargar_proyectos(self) -> None:
        """Reconstruye la lista de proyectos desde la base de datos."""
        _vaciar(self._caja_proyectos, self._grupo_proyectos)
        self._botones_proyecto.clear()

        proyectos = self.contexto.proyectos.listar()
        for posicion, proyecto in enumerate(proyectos):
            boton = QPushButton()
            boton.setObjectName("ElementoNav")
            boton.setCheckable(True)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setIcon(iconos.icono(proyecto.icono, proyecto.color))
            self._aplicar_texto(boton, f"  {proyecto.nombre}")
            boton.clicked.connect(
                lambda _marcado=False, p=proyecto: self.proyecto_elegido.emit(p)
            )
            boton.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            boton.customContextMenuRequested.connect(
                lambda punto, p=proyecto, i=posicion, b=boton: self._menu_proyecto(
                    p, i, len(proyectos), b, punto
                )
            )
            self._grupo_proyectos.addButton(boton)
            self._caja_proyectos.addWidget(boton)
            self._botones_proyecto[proyecto.id] = boton

        self._al_cambiar_proyecto(self.contexto.proyecto)

    def _menu_proyecto(
        self,
        proyecto: Proyecto,
        posicion: int,
        total: int,
        boton: QPushButton,
        punto: QPoint,
    ) -> None:
        """Menu contextual de un proyecto. Solo emite; no toca la base."""
        menu = QMenu(self)
        editar = QAction("Editar…", menu)
        editar.triggered.connect(lambda: self.editar_proyecto.emit(proyecto))
        menu.addAction(editar)

        menu.addSeparator()
        subir = QAction("Subir", menu)
        subir.setEnabled(posicion > 0)
        subir.triggered.connect(lambda: self.mover_proyecto.emit(proyecto, -1))
        menu.addAction(subir)

        bajar = QAction("Bajar", menu)
        bajar.setEnabled(posicion < total - 1)
        bajar.triggered.connect(lambda: self.mover_proyecto.emit(proyecto, 1))
        menu.addAction(bajar)

        menu.addSeparator()
        archivar = QAction("Archivar", menu)
        archivar.triggered.connect(lambda: self.archivar_proyecto.emit(proyecto))
        menu.addAction(archivar)

        eliminar = QAction("Eliminar…", menu)
        eliminar.triggered.connect(lambda: self.eliminar_proyecto.emit(proyecto))
        menu.addAction(eliminar)

        menu.exec(boton.mapToGlobal(punto))

    # -- Secciones ----------------------------------------------------------

    def recargar_secciones(self) -> None:
        """Reconstruye los botones de seccion segun la disposicion guardada."""
        _vaciar(self._caja_secciones, self._grupo_secciones)
        self._botones_seccion.clear()

        catalogo = {seccion.clave: seccion for seccion in SECCIONES}
        disposicion = self.contexto.preferencias.disposicion_secciones(tuple(catalogo))
        for clave in disposicion.visibles:
            seccion = catalogo[clave]
            boton = QPushButton()
            boton.setObjectName("ElementoNav")
            boton.setCheckable(True)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setIcon(iconos.icono(seccion.icono, tokens.TEXTO_SUAVE))
            self._aplicar_texto(boton, f"  {seccion.etiqueta}")
            boton.clicked.connect(
                lambda _marcado=False, c=seccion.clave: self.seccion_elegida.emit(c)
            )
            boton.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            boton.customContextMenuRequested.connect(
                lambda punto, b=boton: self._menu_secciones(b, punto)
            )
            self._grupo_secciones.addButton(boton)
            self._caja_secciones.addWidget(boton)
            self._botones_seccion[seccion.clave] = boton

    def _menu_secciones(self, boton: QPushButton, punto: QPoint) -> None:
        """El punto por el que se descubre que la barra se puede reordenar."""
        menu = QMenu(self)
        accion = QAction("Personalizar barra lateral…", menu)
        accion.triggered.connect(self.personalizar_pedido.emit)
        menu.addAction(accion)
        menu.exec(boton.mapToGlobal(punto))

    def marcar_seccion(self, clave: str) -> None:
        """Marca visualmente la seccion activa sin reemitir la senal.

        Si la seccion esta oculta no hay boton que marcar, y hay que desmarcar
        todo: dejar marcado el anterior indicaria una seccion que no es la que
        se esta viendo. Ocurre al entrar al lector con Biblioteca oculta.
        """
        boton = self._botones_seccion.get(clave)
        if boton is not None:
            boton.setChecked(True)
            return

        # `QButtonGroup` exclusivo no deja desmarcar el marcado; se relaja el
        # grupo lo justo para hacerlo.
        if (marcado := self._grupo_secciones.checkedButton()) is not None:
            self._grupo_secciones.setExclusive(False)
            marcado.setChecked(False)
            self._grupo_secciones.setExclusive(True)

    def habilitar_secciones(self, activas: bool) -> None:
        """Apaga la navegacion cuando no hay proyecto.

        Los botones de proyecto y «Nuevo proyecto» siguen vivos: son la unica
        salida del estado vacio.
        """
        for boton in self._botones_seccion.values():
            boton.setEnabled(activas)

    # -- Estado -------------------------------------------------------------

    def _al_cambiar_proyecto(self, proyecto: object) -> None:
        activo = proyecto if isinstance(proyecto, Proyecto) else None
        self._subtitulo.setText(activo.nombre if activo else "Sin proyecto")
        if activo is not None and (boton := self._botones_proyecto.get(activo.id)):
            boton.setChecked(True)
        self.refrescar_cuenta_atras()

    def _al_cambiar_datos(self, _origen: object, dominio: object) -> None:
        # La cuenta atras solo depende de los hitos.
        if dominio in (None, "calendario"):
            self.refrescar_cuenta_atras()

    def refrescar_cuenta_atras(self) -> None:
        """Actualiza la tarjeta con el hito sin completar mas cercano.

        No se lee ``proyecto.fecha_objetivo`` directamente: con varios hitos, lo
        util es la fecha que viene primero, y anadir un simulacro dentro de dos
        semanas debe cambiar el contador.
        """
        activo = self.contexto.proyecto
        if activo is None or self._colapsada:
            self._tarjeta_examen.mostrar(None)
            return
        self._tarjeta_examen.mostrar(
            self.contexto.calendario.proxima_fecha_clave(activo.id)
        )

    # -- Pomodoro flotante en la barra ---------------------------------------

    def actualizar_pomodoro(self, fase: Fase, restante_seg: int, estado: Estado) -> None:
        """Refresca el reloj compacto de la barra, visible con la app en primer plano."""
        self._mini_pomodoro.actualizar(fase, restante_seg, estado)

    def actualizar_pomodoro_libre(self, transcurrido_seg: int, estado: Estado) -> None:
        """Lo mismo para una sesion de trabajo indefinida, que cuenta hacia arriba."""
        self._mini_pomodoro.actualizar_libre(transcurrido_seg, estado)

    def mostrar_pomodoro(self, visible: bool) -> None:
        """Muestra u oculta el reloj compacto segun si el Pomodoro esta corriendo."""
        self._pomodoro_corriendo = visible
        self._mini_pomodoro.setVisible(visible and not self._colapsada)


class _TarjetaExamen(QFrame):
    """Cuenta atras hasta la proxima fecha clave del proyecto activo."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("TarjetaExamen")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(12, 12, 12, 12)
        caja.setSpacing(2)

        self._titulo = QLabel()
        self._titulo.setObjectName("ExamenTitulo")
        self._titulo.setWordWrap(True)
        caja.addWidget(self._titulo)

        self._fecha = QLabel()
        self._fecha.setObjectName("ExamenFecha")
        caja.addWidget(self._fecha)

        self._dias = QLabel()
        self._dias.setObjectName("ExamenDias")
        caja.addWidget(self._dias)

    def mostrar(self, hito: Hito | None) -> None:
        """Actualiza la tarjeta, ocultandola si no hay ninguna fecha por delante."""
        if hito is None:
            self.setVisible(False)
            return

        restantes = hito.dias_restantes(date.today())
        self._titulo.setText(hito.titulo)
        self._fecha.setText(formato.fecha_corta(hito.fecha))
        if restantes > 1:
            self._dias.setText(f"{restantes} dias")
        elif restantes == 1:
            self._dias.setText("Manana")
        elif restantes == 0:
            self._dias.setText("Es hoy")
        else:
            self._dias.setText("Finalizado")
        self.setVisible(True)


class _MiniPomodoroBarra(QFrame):
    """Reloj compacto de la barra lateral: visible mientras el Pomodoro corre.

    Cubre el hueco que deja la mini ventana flotante, que solo aparece con la
    aplicacion minimizada. Cambiar de seccion no minimiza la ventana, y aun asi
    hay que seguir viendo cuanto queda. Ofrece las mismas acciones que el
    flotante: pausar, detener una sesion indefinida y volver a Pomodoro.
    """

    alternar_pedido = Signal()
    detener_pedido = Signal()
    ir_pedido = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MiniPomodoroBarra")
        self.setVisible(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Ir a Pomodoro")
        self._piezas = PiezasReloj()

        caja = QVBoxLayout(self)
        caja.setContentsMargins(12, 10, 12, 10)
        caja.setSpacing(2)

        cabecera = QHBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        cabecera.addWidget(self._piezas.fase, 1)

        for boton, senal in (
            (self._piezas.alternar, self.alternar_pedido),
            (self._piezas.detener, self.detener_pedido),
        ):
            boton.setObjectName("MiniBarraBoton")
            boton.setFixedHeight(20)
            boton.clicked.connect(senal.emit)
        cabecera.addWidget(self._piezas.alternar)
        caja.addLayout(cabecera)

        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)
        fila.addWidget(self._piezas.tiempo, 1)
        fila.addWidget(self._piezas.detener, 0, Qt.AlignmentFlag.AlignVCenter)
        caja.addLayout(fila)

    def actualizar(self, fase: Fase, restante_seg: int, estado: Estado) -> None:
        self._piezas.actualizar(fase, restante_seg, estado)

    def actualizar_libre(self, transcurrido_seg: int, estado: Estado) -> None:
        """Sesion de trabajo indefinida: cuenta hacia arriba.

        Sin esto la barra seguiria ensenando la cuenta atras parada del bloque
        que espera, que no es lo que se esta cronometrando.
        """
        self._piezas.actualizar_libre(transcurrido_seg, estado)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        """Un clic fuera de los botones lleva a la seccion Pomodoro."""
        if event.button() is Qt.MouseButton.LeftButton:
            self.ir_pedido.emit()
        super().mouseReleaseEvent(event)


def _vaciar(caja: QVBoxLayout, grupo: QButtonGroup) -> None:
    """Retira y destruye los botones de una caja, sacandolos antes del grupo."""
    while (elemento := caja.takeAt(0)) is not None:
        if (widget := elemento.widget()) is not None:
            if isinstance(widget, QPushButton):
                grupo.removeButton(widget)
            widget.deleteLater()


def _etiqueta_seccion(texto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setObjectName("EtiquetaSeccion")
    return etiqueta


def _separador() -> QFrame:
    linea = QFrame()
    linea.setFrameShape(QFrame.Shape.HLine)
    linea.setFixedHeight(1)
    return linea
