"""Ventana principal: una sola ventana, un conmutador de vistas.

No hay ventanas secundarias. La navegacion es la de VS Code: barra lateral fija
a la izquierda y un area de contenido que cambia de vista.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeyEvent, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.modelos import Documento, Proyecto
from mukuwareru.nucleo.servicios import (
    EstadoBarra,
    Familia,
    Resultado,
    ResumenBorrado,
)
from mukuwareru.ui import ajustes_arranque, atajos
from mukuwareru.ui.barra_lateral import BarraLateral
from mukuwareru.ui.dialogos import DialogoProyecto
from mukuwareru.ui.lector import VistaLector
from mukuwareru.ui.mini_pomodoro import MiniPomodoro
from mukuwareru.ui.notificaciones import Notificador
from mukuwareru.ui.paleta import Paleta
from mukuwareru.ui.vistas import SECCIONES, VistaBase
from mukuwareru.ui.vistas.biblioteca import VistaBiblioteca
from mukuwareru.ui.vistas.bienvenida import PanelBienvenida
from mukuwareru.ui.vistas.notas import VistaNotas
from mukuwareru.ui.vistas.panel import VistaPanel
from mukuwareru.ui.vistas.pomodoro import VistaPomodoro
from mukuwareru.ui.vistas.progreso import VistaProgreso
from mukuwareru.utilidades import rutas
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)

# Respaldo cuando la disposicion del usuario no deja ninguna seccion visible.
_SECCION_INICIAL = "panel"

# Margen antes de sacar el reloj flotante al perder el foco. Alt+Tab de paso no
# debe hacerlo aparecer.
_RETARDO_FLOTANTE_MS = 400


class VentanaPrincipal(QMainWindow):
    """Ensambla barra lateral, conmutador de vistas y barra de estado."""

    def __init__(self, contexto: Contexto) -> None:
        super().__init__()
        self.contexto = contexto
        self.setWindowTitle("Mukuwareru")
        self.setMinimumSize(1100, 720)

        self._vistas: dict[str, VistaBase] = {}
        self.mini_pomodoro: MiniPomodoro | None = None
        self.notificador: Notificador | None = None
        self._pomodoro: VistaPomodoro | None = None
        # Estado al que vuelve la barra al desocultarla: colapsada o completa.
        self._barra_previa = EstadoBarra.COMPLETA
        # Seccion que el usuario pidio mientras no habia proyecto: se recupera
        # en cuanto exista uno, en lugar de caer siempre en la inicial.
        self._seccion_pedida = ""
        # A donde vuelve «Volver» del lector: la seccion desde la que se abrio.
        self._origen_lector = "biblioteca"

        self._construir()
        self._montar_paleta()
        # Antes de restaurar la geometria: `restoreGeometry` puede emitir un
        # WindowStateChange, y `changeEvent` necesita la mini ventana ya creada.
        self._montar_pomodoro_flotante()
        self._restaurar_barra_lateral()
        self._restaurar_geometria()

        self.contexto.activar_primero_disponible()
        self.barra_lateral.recargar_proyectos()
        self.ir_a(self._seccion_inicial())

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        central = QWidget()
        fila = QHBoxLayout(central)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)

        self.barra_lateral = BarraLateral(self.contexto)
        self.barra_lateral.seccion_elegida.connect(self.ir_a)
        self.barra_lateral.proyecto_elegido.connect(self._elegir_proyecto)
        self.barra_lateral.nuevo_proyecto.connect(self._crear_proyecto)
        self.barra_lateral.editar_proyecto.connect(self._editar_proyecto)
        self.barra_lateral.mover_proyecto.connect(self._mover_proyecto)
        self.barra_lateral.archivar_proyecto.connect(self._archivar_proyecto)
        self.barra_lateral.eliminar_proyecto.connect(self._eliminar_proyecto)
        self.barra_lateral.personalizar_pedido.connect(lambda: self.ir_a("ajustes"))
        self.barra_lateral.ocultar_pedido.connect(self.ocultar_barra)
        fila.addWidget(self.barra_lateral)

        # Con la barra oculta hace falta una via de vuelta que se vea sin saber
        # el atajo: una franja de 14 px pegada al borde izquierdo.
        self._tirador = QPushButton("›")  # noqa: RUF001 (mismo glifo que la barra)
        self._tirador.setObjectName("TiradorBarra")
        self._tirador.setFixedWidth(14)
        self._tirador.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self._tirador.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tirador.setToolTip("Mostrar la barra lateral (Ctrl+B)")
        self._tirador.setVisible(False)
        self._tirador.clicked.connect(self.alternar_barra)
        fila.addWidget(self._tirador)

        self.contexto.disposicion_cambiada.connect(self._al_cambiar_disposicion)
        self.contexto.proyecto_cambiado.connect(self._al_cambiar_proyecto)

        self.conmutador = QStackedWidget()
        # Todas las secciones se construyen siempre, aunque el usuario haya
        # ocultado alguna: `ir_a("biblioteca")` desde el lector debe funcionar
        # con Biblioteca escondida.
        for seccion in SECCIONES:
            vista = seccion.clase(self.contexto)
            self._vistas[seccion.clave] = vista
            self.conmutador.addWidget(vista)

        # La bienvenida tampoco es una seccion: sustituye al contenido mientras
        # no haya ningun proyecto.
        self.bienvenida = PanelBienvenida()
        self.bienvenida.crear_proyecto.connect(self._crear_proyecto)
        self.conmutador.addWidget(self.bienvenida)

        # El lector ocupa el area de contenido pero no es una seccion de la
        # barra lateral. Se entra desde la Biblioteca, una nota, el Panel o el
        # buscador, y «Volver» regresa a donde se estaba.
        self.lector = VistaLector(self.contexto)
        self.lector.volver.connect(lambda: self.ir_a(self._origen_lector))
        self.lector.anotaciones_cambiadas.connect(
            lambda: self.contexto.notificar_cambio(self.lector, "anotaciones")
        )
        self.lector.abrir_nota.connect(self.abrir_nota)
        self.conmutador.addWidget(self.lector)

        if isinstance(biblioteca := self._vistas.get("biblioteca"), VistaBiblioteca):
            biblioteca.abrir_documento.connect(self.abrir_lector)
        if isinstance(panel := self._vistas.get("panel"), VistaPanel):
            panel.abrir_documento.connect(self.abrir_lector)
        if isinstance(notas := self._vistas.get("notas"), VistaNotas):
            notas.abrir_en_pagina.connect(self.abrir_lector)

        fila.addWidget(self.conmutador, 1)
        self.setCentralWidget(central)

        barra = QStatusBar()
        barra.setObjectName("BarraEstado")
        barra.setSizeGripEnabled(False)
        self._estado = QLabel("Listo")
        barra.addWidget(self._estado)
        barra.addPermanentWidget(QLabel(f"Datos: {rutas.raiz_datos()}"))
        self.setStatusBar(barra)

    # -- Barra lateral -------------------------------------------------------

    def _restaurar_barra_lateral(self) -> None:
        """Devuelve la barra al estado en que se dejo la sesion anterior."""
        self._aplicar_estado_barra(self.contexto.preferencias.estado_barra())

    def _aplicar_estado_barra(self, estado: EstadoBarra) -> None:
        if estado is not EstadoBarra.OCULTA:
            self._barra_previa = estado
        self.barra_lateral.setVisible(estado is not EstadoBarra.OCULTA)
        self._tirador.setVisible(estado is EstadoBarra.OCULTA)
        if estado is not EstadoBarra.OCULTA:
            self.barra_lateral.aplicar_colapso(estado is EstadoBarra.COLAPSADA)
        self.contexto.preferencias.guardar_estado_barra(estado)

    def ocultar_barra(self) -> None:
        """Esconde la barra por completo, recordando como estaba."""
        if not self.barra_lateral.isVisible():
            return
        self._barra_previa = (
            EstadoBarra.COLAPSADA if self.barra_lateral.colapsada else EstadoBarra.COMPLETA
        )
        self._aplicar_estado_barra(EstadoBarra.OCULTA)

    def alternar_barra(self) -> None:
        """Ctrl+B: oculta la barra o la devuelve a como estaba."""
        if self.barra_lateral.isVisible():
            self.ocultar_barra()
        else:
            self._aplicar_estado_barra(self._barra_previa)

    # -- Buscador global -----------------------------------------------------

    def _montar_paleta(self) -> None:
        """Ctrl+K desde cualquier seccion, incluso con el lector abierto."""
        self.paleta = Paleta(self.contexto, self)
        self.paleta.elegido.connect(self._ir_al_resultado)
        # Las combinaciones se declaran en `ui/atajos.py`, que es tambien de
        # donde sale la ayuda de Ajustes.
        atajo = QShortcut(atajos.secuencia("buscar"), self)
        atajo.activated.connect(self.abrir_buscador)
        oculto = QShortcut(atajos.secuencia("barra"), self)
        oculto.activated.connect(self.alternar_barra)
        reloj = QShortcut(atajos.secuencia("pomodoro"), self)
        reloj.activated.connect(self._alternar_pomodoro)
        nota = QShortcut(atajos.secuencia("nota_nueva"), self)
        nota.activated.connect(self._nota_nueva)

    def _alternar_pomodoro(self) -> None:
        """Ctrl+Espacio: el mismo boton que el de la barra y el del flotante."""
        if self.contexto.proyecto is not None and self._pomodoro is not None:
            self._pomodoro.alternar_reloj()

    def _nota_nueva(self) -> None:
        """Ctrl+N: nota nueva desde cualquier seccion, sin pasar antes por Notas."""
        vista = self._vistas.get("notas")
        if self.contexto.proyecto is None or not isinstance(vista, VistaNotas):
            return
        self.ir_a("notas")
        vista.nueva_nota()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (API de Qt)
        """Ctrl+1 … Ctrl+9: la seccion N de la barra, en el orden del usuario."""
        digito = event.key() - Qt.Key.Key_0
        if (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and 1 <= digito <= 9
            and self.contexto.proyecto is not None
        ):
            claves = tuple(seccion.clave for seccion in SECCIONES)
            visibles = self.contexto.preferencias.disposicion_secciones(claves).visibles
            if digito <= len(visibles):
                self.ir_a(visibles[digito - 1])
                event.accept()
                return
        super().keyPressEvent(event)

    def abrir_buscador(self) -> None:
        """Muestra la paleta de busqueda, si hay proyecto sobre el que buscar."""
        if self.contexto.proyecto is None:
            return
        self.paleta.abrir()

    def _ir_al_resultado(self, resultado: object) -> None:
        """Salta al sitio exacto del resultado elegido.

        Toda la navegacion se apoya en lo que ya existe: `ir_a`, `abrir_lector`
        y `abrir_nota`. La paleta no aprende caminos nuevos.
        """
        if not isinstance(resultado, Resultado):
            return

        if resultado.familia is Familia.NOTA:
            self.abrir_nota(resultado.objeto_id)
            return

        if resultado.documento_id is not None:
            documento = self.contexto.documentos.obtener(resultado.documento_id)
            if documento is not None:
                self.abrir_lector(documento, resultado.pagina or 0)
                return

        if resultado.familia in (Familia.MATERIA, Familia.MODULO):
            self._enfocar_en_progreso(resultado)
            return

        destino = {Familia.HITO: "calendario"}.get(resultado.familia, "panel")
        self.ir_a(destino)

    def _enfocar_en_progreso(self, resultado: Resultado) -> None:
        """Abre Progreso con la materia del resultado desplegada y a la vista."""
        self.ir_a("progreso")
        materia_id: int | None = resultado.objeto_id
        if resultado.familia is Familia.MODULO:
            modulo = self.contexto.modulos.obtener(resultado.objeto_id)
            materia_id = modulo.materia_id if modulo is not None else None
        vista = self._vistas.get("progreso")
        if materia_id is not None and isinstance(vista, VistaProgreso):
            vista.enfocar(materia_id)

    # -- Pomodoro fuera de la ventana ---------------------------------------

    def _montar_pomodoro_flotante(self) -> None:
        """Enlaza el reloj con la mini ventana y con los avisos del sistema."""
        self.notificador = Notificador(self)
        self.mini_pomodoro = MiniPomodoro()
        self.mini_pomodoro.restaurar_pedido.connect(self._restaurar_desde_mini)

        # Retardo antes de sacar la mini ventana: pasar por Mukuwareru con
        # Alt+Tab desactiva y reactiva la ventana en decimas de segundo, y sin
        # esta espera el reloj flotante parpadearia en cada paso.
        self._espera_mini = QTimer(self)
        self._espera_mini.setSingleShot(True)
        self._espera_mini.setInterval(_RETARDO_FLOTANTE_MS)
        self._espera_mini.timeout.connect(self._al_expirar_espera)

        vista = self._vistas.get("pomodoro")
        if not isinstance(vista, VistaPomodoro):
            return

        self._pomodoro = vista
        vista.aviso.connect(self.notificador.notificar)
        vista.fase_termino.connect(lambda *_: self._refrescar_mini())
        vista.reloj_avanzo.connect(self._refrescar_mini)
        self.mini_pomodoro.alternar_pedido.connect(vista.alternar_reloj)
        self.mini_pomodoro.detener_pedido.connect(vista.detener_sesion_libre)
        self.barra_lateral.pomodoro_alternado.connect(vista.alternar_reloj)
        self.barra_lateral.pomodoro_detenido.connect(vista.detener_sesion_libre)
        self._refrescar_mini()

    def _refrescar_mini(self) -> None:
        if self._pomodoro is None or self.mini_pomodoro is None:
            return
        self._volcar_reloj()
        self.barra_lateral.mostrar_pomodoro(self._pomodoro.corriendo)
        self._evaluar_flotante()

    def _volcar_reloj(self, *, forzar_flotante: bool = False) -> None:
        """Pinta en los dos relojes compactos lo que se este cronometrando.

        Puede ser el Pomodoro o una sesion de trabajo indefinida; nunca las dos,
        que la vista no lo permite. El reloj compacto de la barra lateral cubre
        el hueco entre "minimizado" y "en primer plano pero en otra seccion",
        que la mini ventana no ve.
        """
        if self._pomodoro is None or self.mini_pomodoro is None:
            return
        # El flotante oculto no se refresca: `_mostrar_mini` lo pone al dia
        # justo antes de ensenarlo.
        flotante = forzar_flotante or self.mini_pomodoro.isVisible()
        if self._pomodoro.sesion_libre_activa:
            crono = self._pomodoro.cronometro
            if flotante:
                self.mini_pomodoro.actualizar_libre(crono.transcurrido_seg, crono.estado)
            self.barra_lateral.actualizar_pomodoro_libre(
                crono.transcurrido_seg, crono.estado
            )
            return
        reloj = self._pomodoro.reloj
        if flotante:
            self.mini_pomodoro.actualizar(reloj.fase, reloj.restante_seg, reloj.estado)
        self.barra_lateral.actualizar_pomodoro(reloj.fase, reloj.restante_seg, reloj.estado)

    def _evaluar_flotante(self) -> None:
        """Decide si el reloj flotante debe estar a la vista.

        La regla es la que pidio el usuario: si el Pomodoro corre y Mukuwareru no
        esta delante, el reloj flota. Se mira ``isActiveWindow`` de la ventana
        principal y **no** el estado de la aplicacion: pulsar «Pausar» en la mini
        ventana activa la aplicacion, y con el estado global la mini se
        esconderia justo en el momento de ir a usarla.
        """
        if self.mini_pomodoro is None or self._pomodoro is None:
            return

        if not (self._pomodoro.corriendo and self._fuera_de_la_vista()):
            self._espera_mini.stop()
            if self.mini_pomodoro.isVisible():
                self.mini_pomodoro.hide()
            return

        if self.mini_pomodoro.isVisible():
            return
        # Minimizar es una decision explicita y no necesita margen de duda;
        # perder el foco, si.
        if self.isMinimized():
            self._mostrar_mini()
        elif not self._espera_mini.isActive():
            self._espera_mini.start()

    def _fuera_de_la_vista(self) -> bool:
        """Si Mukuwareru no esta delante: minimizada o sin el foco."""
        return self.isMinimized() or not self.isActiveWindow()

    def _al_expirar_espera(self) -> None:
        """El foco se perdio de verdad, no de paso: sale el reloj flotante."""
        if self._fuera_de_la_vista():
            self._mostrar_mini()

    def _mostrar_mini(self) -> None:
        """Saca el reloj flotante. No decide si toca: eso es `_evaluar_flotante`."""
        if self.mini_pomodoro is None or self._pomodoro is None:
            return
        if not self._pomodoro.corriendo:
            return
        self._volcar_reloj(forzar_flotante=True)
        self.mini_pomodoro.show()
        self.mini_pomodoro.colocar_por_defecto()

    def _restaurar_desde_mini(self) -> None:
        if self.mini_pomodoro is not None:
            self.mini_pomodoro.hide()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 (API de Qt)
        """Saca la mini ventana al minimizar o al perder el foco, y la retira.

        Qt puede llamar aqui durante la construccion (``restoreGeometry`` emite
        un WindowStateChange), asi que no se puede dar por hecho que la mini
        ventana exista todavia.
        """
        interesa = (QEvent.Type.WindowStateChange, QEvent.Type.ActivationChange)
        if event.type() in interesa and self.mini_pomodoro is not None:
            self._evaluar_flotante()
        super().changeEvent(event)

    # -- Navegacion ---------------------------------------------------------

    def _seccion_inicial(self) -> str:
        """Primera seccion visible segun la disposicion del usuario.

        Arrancar en lo que el usuario puso arriba es justo lo que se espera de
        poder reordenar la barra.
        """
        claves = tuple(seccion.clave for seccion in SECCIONES)
        visibles = self.contexto.preferencias.disposicion_secciones(claves).visibles
        return visibles[0] if visibles else _SECCION_INICIAL

    def _hay_proyecto(self) -> bool:
        """Muestra la bienvenida y devuelve ``False`` si no hay proyecto activo."""
        if self.contexto.proyecto is not None:
            return True
        if self.conmutador.currentWidget() is self.lector:
            self.lector.cerrar()
        self.conmutador.setCurrentWidget(self.bienvenida)
        self.barra_lateral.habilitar_secciones(False)
        return False

    def ir_a(self, clave: str) -> None:
        """Muestra la seccion indicada por su clave."""
        vista = self._vistas.get(clave)
        if vista is None:
            _log.warning("Seccion desconocida: %s", clave)
            return
        self._seccion_pedida = clave
        if not self._hay_proyecto():
            return
        if self.conmutador.currentWidget() is self.lector:
            self.lector.cerrar()
        self.conmutador.setCurrentWidget(vista)
        self.barra_lateral.marcar_seccion(clave)

    def _al_cambiar_proyecto(self, proyecto: object) -> None:
        """Entra o sale del estado vacio segun aparezca o falte el proyecto."""
        if proyecto is None:
            self._hay_proyecto()
            return
        self.barra_lateral.habilitar_secciones(True)
        if self.conmutador.currentWidget() is self.bienvenida:
            self.ir_a(self._seccion_pedida or self._seccion_inicial())

    def _al_cambiar_disposicion(self) -> None:
        """Reconstruye la barra y se queda en una seccion que siga visible."""
        self.barra_lateral.recargar_secciones()
        self.barra_lateral.habilitar_secciones(self.contexto.proyecto is not None)
        actual = self.conmutador.currentWidget()
        for clave, vista in self._vistas.items():
            if vista is actual:
                self.barra_lateral.marcar_seccion(clave)
                break

    def abrir_lector(self, documento: object, pagina: int | None = None) -> None:
        """Abre un PDF en el lector, opcionalmente en una pagina concreta."""
        if not isinstance(documento, Documento) or not self._hay_proyecto():
            return
        abierto = (
            self.lector.ir_a(documento, pagina)
            if pagina is not None
            else self.lector.abrir(documento)
        )
        if abierto:
            actual = self.conmutador.currentWidget()
            if actual is not self.lector:
                self._origen_lector = next(
                    (clave for clave, vista in self._vistas.items() if vista is actual),
                    "biblioteca",
                )
            self.conmutador.setCurrentWidget(self.lector)
            self.barra_lateral.marcar_seccion("biblioteca")

    def abrir_nota(self, nota_id: int) -> None:
        """Va a la seccion Notas y deja abierta esa nota.

        Es el camino de vuelta del lector: se llega a una nota desde el PDF
        igual que se llega al PDF desde una nota.
        """
        vista = self._vistas.get("notas")
        if not isinstance(vista, VistaNotas):
            return
        self.ir_a("notas")
        vista.mostrar_nota(nota_id)

    def vista(self, clave: str) -> VistaBase | None:
        """Vista registrada bajo esa clave, o ``None``. Util para pruebas."""
        return self._vistas.get(clave)

    def _elegir_proyecto(self, proyecto: object) -> None:
        if isinstance(proyecto, Proyecto):
            self.contexto.activar(proyecto)

    # -- Proyectos ----------------------------------------------------------

    def _crear_proyecto(self) -> None:
        dialogo = DialogoProyecto(parent=self)
        if dialogo.exec() != DialogoProyecto.DialogCode.Accepted:
            return
        creado = self.contexto.servicio_proyectos.crear(dialogo.datos())
        self.barra_lateral.recargar_proyectos()
        self.contexto.activar(creado)
        self.contexto.notificar_cambio()
        self._estado.setText(f"Proyecto «{creado.nombre}» creado")

    def _editar_proyecto(self, proyecto: object) -> None:
        if not isinstance(proyecto, Proyecto):
            return
        dialogo = DialogoProyecto(proyecto, parent=self)
        if dialogo.exec() != DialogoProyecto.DialogCode.Accepted:
            return

        datos = dialogo.datos()
        guardado = self.contexto.servicio_proyectos.guardar(proyecto, datos)
        self.barra_lateral.recargar_proyectos()
        # Refrescar y no `activar`: si el id no cambia, `activar` es un no-op y
        # las vistas se quedarian con el nombre viejo.
        self.contexto.refrescar_proyecto_activo()
        self.contexto.notificar_cambio()

        if datos.ruta_biblioteca is None and guardado.ruta_biblioteca is not None:
            QMessageBox.information(
                self,
                "Carpeta no movida",
                f"No se pudo renombrar la carpeta de PDFs, asi que «{guardado.nombre}» "
                f"sigue leyendola de:\n\n{guardado.ruta_biblioteca}\n\n"
                "Tus PDFs y tus anotaciones estan intactos. Puedes mover la carpeta a "
                "mano y actualizar la ruta desde este mismo dialogo.",
            )
        self._estado.setText(f"Proyecto «{guardado.nombre}» actualizado")

    def _mover_proyecto(self, proyecto: object, desplazamiento: int) -> None:
        if not isinstance(proyecto, Proyecto):
            return
        ids = [p.id for p in self.contexto.proyectos.listar()]
        if proyecto.id not in ids:
            return
        origen = ids.index(proyecto.id)
        destino = origen + desplazamiento
        if not 0 <= destino < len(ids):
            return
        ids[origen], ids[destino] = ids[destino], ids[origen]
        self.contexto.servicio_proyectos.reordenar(ids)
        self.barra_lateral.recargar_proyectos()

    def _archivar_proyecto(self, proyecto: object) -> None:
        if not isinstance(proyecto, Proyecto):
            return
        self.contexto.servicio_proyectos.archivar(proyecto)
        self.barra_lateral.recargar_proyectos()
        # Si se archivo el activo hay que soltarlo: seguiria activo un proyecto
        # que ya no aparece en la barra.
        activo = self.contexto.proyecto
        if activo is not None and activo.id == proyecto.id:
            self.contexto.activar(None)
            self.contexto.activar_primero_disponible()
        self.contexto.notificar_cambio()
        self._estado.setText(f"Proyecto «{proyecto.nombre}» archivado")

    def _eliminar_proyecto(self, proyecto: object) -> None:
        if not isinstance(proyecto, Proyecto):
            return
        resumen = self.contexto.servicio_proyectos.resumen_borrado(proyecto)
        if not self._confirmar_borrado(proyecto, resumen):
            return

        self.contexto.servicio_proyectos.eliminar(proyecto.id)
        activo = self.contexto.proyecto
        if activo is not None and activo.id == proyecto.id:
            self.contexto.activar(None)
        self.barra_lateral.recargar_proyectos()
        self.contexto.activar_primero_disponible()
        self.contexto.notificar_cambio()
        self._estado.setText(f"Proyecto «{proyecto.nombre}» eliminado")

    def _confirmar_borrado(self, proyecto: Proyecto, resumen: ResumenBorrado) -> bool:
        """Avisa de lo que se pierde, sin exagerar ni quedarse corto."""
        detalle = ""
        if resumen.hay_algo:
            partes = [
                f"{resumen.materias} materias y {resumen.modulos} modulos",
                f"{resumen.documentos} documentos registrados",
                f"{resumen.sesiones} sesiones de estudio",
                f"{resumen.anotaciones} anotaciones",
            ]
            detalle = "Se borrara tambien:\n  · " + "\n  · ".join(partes) + "\n\n"

        aviso = QMessageBox(self)
        aviso.setIcon(QMessageBox.Icon.Warning)
        aviso.setWindowTitle("Eliminar proyecto")
        aviso.setText(f"¿Eliminar «{proyecto.nombre}»?")
        aviso.setInformativeText(
            detalle
            + "Los archivos PDF del disco NO se borran; siguen en\n"
            + f"{resumen.carpeta}"
        )
        aviso.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        # Cancelar por defecto: el Enter reflejo no debe borrar un proyecto.
        aviso.setDefaultButton(QMessageBox.StandardButton.Cancel)
        aviso.button(QMessageBox.StandardButton.Yes).setText("Eliminar")
        return aviso.exec() == QMessageBox.StandardButton.Yes

    # -- Geometria ----------------------------------------------------------

    def _restaurar_geometria(self) -> None:
        """Recupera el tamano de la ventana y la posicion del reloj flotante."""
        geometria = ajustes_arranque.obtener_valor("geometria")
        if not isinstance(geometria, str) or not self.restoreGeometry(
            QByteArray.fromBase64(geometria.encode())
        ):
            self.resize(1360, 860)

        posicion = ajustes_arranque.obtener_valor("mini_pomodoro")
        if (
            self.mini_pomodoro is not None
            and isinstance(posicion, list)
            and len(posicion) == 2
        ):
            self.mini_pomodoro.restaurar_posicion(int(posicion[0]), int(posicion[1]))

    def _guardar_geometria(self) -> None:
        ajustes_arranque.guardar(
            "geometria", bytes(self.saveGeometry().toBase64()).decode()
        )
        if self.mini_pomodoro is not None:
            posicion = self.mini_pomodoro.posicion_guardada()
            if posicion is not None:
                ajustes_arranque.guardar("mini_pomodoro", list(posicion))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (API de Qt)
        # El pomodoro no sobrevive al cierre: se termina aqui, guardando el
        # tiempo ya trabajado para que no se pierda.
        if self._pomodoro is not None:
            self._pomodoro.finalizar_por_cierre()
        if self.mini_pomodoro is not None:
            self.mini_pomodoro.hide()
        if self.notificador is not None:
            self.notificador.cerrar()

        self._guardar_geometria()
        self.contexto.conexion.close()
        _log.info("Aplicacion cerrada")
        super().closeEvent(event)
