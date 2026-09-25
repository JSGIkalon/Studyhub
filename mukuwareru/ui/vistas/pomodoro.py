"""Pomodoro: el recorrido de la sesion, el temporizador y el registro.

El QTimer vive aqui; la forma del recorrido esta en ``Recorrido`` y la cuenta
atras en ``RelojPomodoro``, los dos Python puro. Esta vista solo traduce entre
esos mundos y el timeline.

El elemento principal es el timeline: se ve el trayecto, se sabe donde se esta y
se pasa al bloque siguiente. Todo lo demas —anillo, duraciones por defecto,
temas— esta debajo y en pequeno.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Materia, OrigenSesion
from mukuwareru.nucleo.servicios import (
    Bloque,
    Configuracion,
    Cronometro,
    Estado,
    Fase,
    FaseTerminada,
    Preferencias,
    RelojPomodoro,
)
from mukuwareru.ui import iconos
from mukuwareru.ui.dialogos.etiquetar import DialogoEtiquetar
from mukuwareru.ui.pomodoro import PanelEdicionBloque, Timeline, TiraTemas
from mukuwareru.ui.pomodoro.bloque import color_de, segunda_linea
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import AnilloReloj, Tarjeta, contenedor
from mukuwareru.utilidades import formato
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)

_ANCHO_CAMPO = 130
_DIAMETRO_ANILLO = 132

# Por debajo de un minuto, una sesion interrumpida es ruido en las estadisticas.
_MINIMO_REGISTRABLE_SEG = 60


def _minutos(minimo: int, maximo: int) -> QSpinBox:
    """Campo de minutos con ancho fijo."""
    control = QSpinBox()
    control.setRange(minimo, maximo)
    control.setSuffix(" min")
    control.setMaximumWidth(_ANCHO_CAMPO)
    return control


class VistaPomodoro(VistaBase):
    """Timeline del recorrido, cuenta atras y registro de sesiones."""

    titulo = "Pomodoro"
    dominio = "sesiones"
    ignora = frozenset({"anotaciones", "documentos", "notas", "resultados"})

    # El reloj vive aqui, pero la mini ventana y los avisos del sistema los
    # gestiona VentanaPrincipal: esta vista no sabe que existen.
    reloj_avanzo = Signal()
    fase_termino = Signal(object, object)   # fase terminada, fase siguiente
    aviso = Signal(str, str)                # titulo, mensaje

    def _construir(self) -> None:
        preferencias = self.contexto.preferencias.cargar()
        self._reloj = RelojPomodoro(preferencias.pomodoro)
        self._inicio_fase: datetime | None = None
        self._materias: list[Materia] = []

        # Sesion de trabajo indefinida: cuenta hacia arriba y solo la cierra el
        # usuario. Va con su propio latido para no meter un `if` por segundo en
        # el tic del Pomodoro; las dos no pueden correr a la vez.
        self._cronometro = Cronometro()
        self._inicio_libre: datetime | None = None

        self._latido = QTimer(self)
        self._latido.setInterval(1000)
        self._latido.timeout.connect(self._tic)

        self._latido_libre = QTimer(self)
        self._latido_libre.setInterval(1000)
        self._latido_libre.timeout.connect(self._tic_libre)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
        )
        raiz.setSpacing(tokens.ESPACIO)

        raiz.addWidget(self._cabecera())
        raiz.addWidget(self._timeline_y_temas())

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(tokens.ESPACIO)
        cuerpo.addWidget(self._tarjeta_reloj(), 1)
        cuerpo.addWidget(self._tarjeta_configuracion(), 0)
        raiz.addLayout(cuerpo)
        raiz.addStretch(1)

        self._editor = PanelEdicionBloque(self)
        self._editor.cambiado.connect(self._al_cambiar_bloque)
        self._editor.duplicar_pedido.connect(self._al_duplicar)
        self._editor.eliminar_pedido.connect(self._al_eliminar)

        # Conexion propia y no `recargar`: sin proyecto la vista no se llega a
        # mostrar, asi que la recarga perezosa nunca correria y el boton
        # quedaria habilitado sobre un estado en el que no se puede registrar.
        self.contexto.proyecto_cambiado.connect(lambda _p: self._revisar_proyecto())
        self._reconstruir()
        self._revisar_proyecto()

    # -- Construccion -------------------------------------------------------

    def _cabecera(self) -> QWidget:
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        fila.addWidget(titulo)
        fila.addStretch(1)

        # Sesion indefinida a la izquierda, separada del bloque de botones del
        # Pomodoro: son dos formas de cronometrar y no se mezclan.
        self._boton_libre = QPushButton("  Iniciar trabajo indefinido")
        self._boton_libre.setToolTip(
            "Cronometra una sesion sin duracion fijada. Cuenta en el calendario "
            "igual que un pomodoro, y al detenerla se pregunta el tema."
        )
        self._boton_libre.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_libre.clicked.connect(self._alternar_libre)
        fila.addWidget(self._boton_libre)

        self._boton_libre_detener = QPushButton("Detener")
        self._boton_libre_detener.setToolTip(
            "Cierra la sesion indefinida y registra el tiempo."
        )
        self._boton_libre_detener.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_libre_detener.clicked.connect(self._detener_libre)
        self._boton_libre_detener.setVisible(False)
        fila.addWidget(self._boton_libre_detener)

        fila.addSpacing(tokens.ESPACIO_GRANDE)

        self._boton_principal = QPushButton("  Iniciar")
        self._boton_principal.setObjectName("BotonPrimario")
        self._boton_principal.setMinimumWidth(130)
        self._boton_principal.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boton_principal.clicked.connect(self._alternar)
        fila.addWidget(self._boton_principal)

        reiniciar = QPushButton("Reiniciar")
        reiniciar.setToolTip("Vuelve al principio de este bloque.")
        reiniciar.setCursor(Qt.CursorShape.PointingHandCursor)
        reiniciar.clicked.connect(self._reiniciar)
        fila.addWidget(reiniciar)

        saltar = QPushButton("Saltar")
        saltar.setToolTip("Pasa al bloque siguiente. No cuenta como sesion completada.")
        saltar.setCursor(Qt.CursorShape.PointingHandCursor)
        saltar.clicked.connect(self._saltar)
        fila.addWidget(saltar)

        return contenedor(fila)

    def _timeline_y_temas(self) -> QWidget:
        caja = QVBoxLayout()
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(tokens.ESPACIO_PEQUENO)

        self._timeline = Timeline()
        self._timeline.mover_pedido.connect(self._al_mover)
        self._timeline.tema_soltado.connect(self._al_soltar_tema)
        self._timeline.nuevo_pedido.connect(self._al_nuevo)
        self._timeline.editar_pedido.connect(self._al_editar)
        self._timeline.duplicar_pedido.connect(self._al_duplicar)
        self._timeline.eliminar_pedido.connect(self._al_eliminar)
        self._timeline.ir_pedido.connect(self._al_ir_a)
        self._timeline.duracion_pedida.connect(self._al_pedir_duracion)
        caja.addWidget(self._timeline)

        self._temas = TiraTemas()
        caja.addWidget(self._temas)
        return contenedor(caja)

    def _tarjeta_reloj(self) -> Tarjeta:
        tarjeta = Tarjeta()
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(tokens.ESPACIO_GRANDE)

        self._anillo = AnilloReloj(diametro=_DIAMETRO_ANILLO, grosor=9)
        fila.addWidget(self._anillo, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addStretch(1)

        self._nombre_bloque = QLabel()
        self._nombre_bloque.setStyleSheet(
            f"font-size: {tokens.TAM_TITULO - 4}px; font-weight: 600;"
        )
        textos.addWidget(self._nombre_bloque)

        self._tema_bloque = QLabel()
        self._tema_bloque.setObjectName("TextoSuave")
        textos.addWidget(self._tema_bloque)

        self._posicion = QLabel()
        self._posicion.setObjectName("TextoTenue")
        textos.addWidget(self._posicion)

        self._pie = QLabel()
        self._pie.setObjectName("TextoTenue")
        textos.addWidget(self._pie)
        textos.addStretch(1)

        fila.addLayout(textos, 1)
        tarjeta.agregar(contenedor(fila))
        return tarjeta

    def _tarjeta_configuracion(self) -> Tarjeta:
        """Duraciones por defecto: la semilla del recorrido, no su forma final."""
        tarjeta = Tarjeta("Duraciones por defecto")
        tarjeta.setFixedWidth(330)

        formulario = QFormLayout()
        formulario.setSpacing(tokens.ESPACIO_PEQUENO)

        self._campo_trabajo = _minutos(1, 180)
        self._campo_corto = _minutos(1, 60)
        self._campo_largo = _minutos(1, 120)
        self._campo_ciclo = QSpinBox()
        self._campo_ciclo.setRange(1, 12)
        self._campo_ciclo.setSuffix(" sesiones")
        self._campo_ciclo.setMaximumWidth(_ANCHO_CAMPO)

        formulario.addRow("Trabajo", self._campo_trabajo)
        formulario.addRow("Descanso corto", self._campo_corto)
        formulario.addRow("Descanso largo", self._campo_largo)
        formulario.addRow("Descanso largo cada", self._campo_ciclo)

        self._campo_preguntar = QCheckBox("Preguntar materias al terminar")
        self._campo_preguntar.setToolTip(
            "Un bloque con tema asignado no pregunta: se etiqueta solo."
        )
        # Fila entera y no columna de campo: el texto no cabe en la mitad derecha.
        formulario.addRow(self._campo_preguntar)
        tarjeta.agregar(contenedor(formulario))

        self._aviso_config = QLabel()
        self._aviso_config.setObjectName("TextoTenue")
        self._aviso_config.setWordWrap(True)
        tarjeta.agregar(self._aviso_config)

        regenerar = QPushButton("Regenerar recorrido")
        regenerar.setToolTip(
            "Tira el recorrido actual y lo vuelve a armar con estas duraciones."
        )
        regenerar.setCursor(Qt.CursorShape.PointingHandCursor)
        regenerar.clicked.connect(self._regenerar)
        tarjeta.agregar(regenerar)

        for control in (
            self._campo_trabajo, self._campo_corto, self._campo_largo, self._campo_ciclo
        ):
            control.valueChanged.connect(self._al_editar_configuracion)
        self._campo_preguntar.toggled.connect(self._al_editar_configuracion)
        return tarjeta

    # -- Datos --------------------------------------------------------------

    def recargar(self) -> None:
        """Vuelca las preferencias guardadas en los campos y repinta."""
        preferencias = self.contexto.preferencias.cargar()
        if (
            self._reloj.estado is Estado.DETENIDO
            and preferencias.pomodoro != self._reloj.configuracion
        ):
            self._reloj.aplicar(preferencias.pomodoro)
        self._volcar_configuracion(preferencias)
        self._cargar_materias()
        self._reconstruir()

    def _revisar_proyecto(self) -> None:
        """Sin proyecto no se puede registrar nada, y el reloj no debe arrancar."""
        self._refrescar_botones()
        self._cargar_materias()

    def _refrescar_botones(self) -> None:
        """Habilita cada boton segun lo que se pueda hacer ahora mismo.

        Sin proyecto no se cronometra: el tiempo se tiraria en silencio. Y las
        dos formas de cronometrar se excluyen, porque registrar a la vez un
        pomodoro y una sesion libre contaria dos veces la misma hora.
        """
        hay_proyecto = self.contexto.proyecto is not None
        libre = self._cronometro.activo
        pomodoro_vivo = self._reloj.estado is Estado.CORRIENDO

        self._boton_principal.setEnabled(hay_proyecto and not libre)
        self._boton_principal.setToolTip(
            "Detén la sesion indefinida para volver al Pomodoro." if libre
            else "" if hay_proyecto
            else "Crea un proyecto para que el tiempo quede registrado."
        )

        self._boton_libre.setEnabled(hay_proyecto and (libre or not pomodoro_vivo))
        self._boton_libre.setText(
            "  Pausar" if self._cronometro.corriendo
            else "  Reanudar" if libre
            else "  Iniciar trabajo indefinido"
        )
        self._boton_libre_detener.setVisible(libre)

    def _cargar_materias(self) -> None:
        proyecto = self.contexto.proyecto
        self._materias = (
            self.contexto.materias.listar(proyecto.id) if proyecto is not None else []
        )
        self._temas.establecer(self._materias)
        if self._soltar_temas_ajenos():
            self._reconstruir()

    def _soltar_temas_ajenos(self) -> bool:
        """Quita de los bloques los temas que ya no son de este proyecto.

        El recorrido vive en memoria y sobrevive a un cambio de proyecto, pero los
        temas no: sin esto, terminar un bloque etiquetaria la sesion con la materia
        de **otro** proyecto, o con una que se acaba de borrar, y eso ultimo
        reventaria contra la clave ajena en mitad de un tic.

        Devuelve si hubo que soltar alguno, para repintar solo entonces.
        """
        validas = {materia.id for materia in self._materias}
        soltados = False
        for bloque in self._reloj.recorrido.bloques:
            if bloque.materia_id is None or bloque.materia_id in validas:
                continue
            bloque.materia_id = None
            bloque.materia = ""
            soltados = True
        return soltados

    def _volcar_configuracion(self, preferencias: Preferencias) -> None:
        """Escribe los valores en los campos sin disparar el guardado."""
        campos = (
            (self._campo_trabajo, preferencias.pomodoro.trabajo_min),
            (self._campo_corto, preferencias.pomodoro.descanso_corto_min),
            (self._campo_largo, preferencias.pomodoro.descanso_largo_min),
            (self._campo_ciclo, preferencias.pomodoro.sesiones_por_ciclo),
        )
        for control, valor in campos:
            control.blockSignals(True)
            control.setValue(valor)
            control.blockSignals(False)

        self._campo_preguntar.blockSignals(True)
        self._campo_preguntar.setChecked(preferencias.preguntar_materia)
        self._campo_preguntar.blockSignals(False)

    def _al_editar_configuracion(self) -> None:
        """Guarda los cambios y los aplica en cuanto el reloj lo permita.

        Con el reloj corriendo no se toca el bloque en curso: cambiar la duracion
        a mitad de un pomodoro lo reiniciaria sin avisar. Se aplica al parar. Y si
        el recorrido esta armado a mano, no se pisa: para eso esta «Regenerar».
        """
        nueva = Configuracion(
            trabajo_min=self._campo_trabajo.value(),
            descanso_corto_min=self._campo_corto.value(),
            descanso_largo_min=self._campo_largo.value(),
            sesiones_por_ciclo=self._campo_ciclo.value(),
        )
        self.contexto.preferencias.guardar(
            Preferencias(pomodoro=nueva, preguntar_materia=self._campo_preguntar.isChecked())
        )

        if self._reloj.estado is Estado.DETENIDO:
            self._reloj.aplicar(nueva)
            self._aviso_config.setText(
                "Los bloques que hayas editado a mano conservan su duracion."
                if self._reloj.recorrido.tocado else ""
            )
        else:
            self._aviso_config.setText(
                "Los cambios se aplicaran cuando termines o detengas el bloque actual."
            )
        self._reconstruir()
        self.contexto.notificar_cambio(self)

    def _regenerar(self) -> None:
        """Vuelve al ciclo que describen las duraciones por defecto."""
        if self._reloj.recorrido.tocado:
            respuesta = QMessageBox.question(
                self,
                "Regenerar el recorrido",
                "Se descartan los bloques que hayas anadido, movido o editado, y "
                "el recorrido vuelve a empezar.",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                return

        self._latido.stop()
        self._reloj.reiniciar_ciclo()
        self._inicio_fase = None
        self._aviso_config.setText("")
        self._reconstruir()

    # -- Pintado ------------------------------------------------------------

    def _reconstruir(self) -> None:
        """Rehace el timeline. Solo cuando cambia la forma del recorrido."""
        self._timeline.reconstruir(self._reloj)
        self._pintar()

    def _pintar(self) -> None:
        # El anillo muestra lo que se este cronometrando de verdad. Dejarlo en la
        # cuenta atras del pomodoro mientras corre una sesion indefinida seria
        # ensenar un reloj parado al lado de uno que anda.
        if self._cronometro.activo:
            self._pintar_libre()
        else:
            self._pintar_bloque()

        self._boton_principal.setText(
            "  Pausar" if self._reloj.estado is Estado.CORRIENDO else "  Iniciar"
        )
        self._boton_principal.setIcon(iconos.icono("reloj", "#FFFFFF"))
        self._boton_libre.setIcon(iconos.icono("reloj", tokens.TEXTO))
        self._refrescar_botones()

        self._timeline.actualizar_estado(self._reloj)
        self.reloj_avanzo.emit()

    def _pintar_bloque(self) -> None:
        """La tarjeta del reloj mostrando el bloque del recorrido."""
        bloque = self._reloj.bloque
        color = color_de(bloque)
        self._anillo.establecer(
            self._reloj.restante_seg, self._reloj.progreso, bloque.tipo.etiqueta, color
        )

        self._nombre_bloque.setText(bloque.etiqueta)
        self._nombre_bloque.setStyleSheet(
            f"font-size: {tokens.TAM_TITULO - 4}px; font-weight: 600; color: {color};"
        )
        self._tema_bloque.setText(segunda_linea(bloque))

        recorrido = self._reloj.recorrido
        self._posicion.setText(
            f"Bloque {recorrido.indice + 1} de {recorrido.total}  ·  "
            f"{formato.horas(self._reloj.restante_total_seg)} por delante"
        )
        self._pie.setText(
            f"{self._reloj.completadas} pomodoros completados en esta sesion de trabajo"
        )

    def _pintar_libre(self) -> None:
        """La misma tarjeta, contando hacia arriba y sin final a la vista."""
        # Sin duracion prevista no hay progreso que dibujar: el anillo se queda
        # en su pista y lo que cuenta es el numero del centro.
        self._anillo.establecer(
            self._cronometro.transcurrido_seg, 0.0, "Indefinido", tokens.ACENTO
        )

        self._nombre_bloque.setText("Trabajo indefinido")
        self._nombre_bloque.setStyleSheet(
            f"font-size: {tokens.TAM_TITULO - 4}px; font-weight: 600; "
            f"color: {tokens.ACENTO};"
        )
        self._tema_bloque.setText(
            "En marcha" if self._cronometro.corriendo else "En pausa"
        )
        self._posicion.setText(
            "Sin duracion fijada  ·  el recorrido espera donde lo dejaste"
        )
        self._pie.setText("Al detener se registra el tiempo y se pregunta el tema.")

    # -- Edicion del recorrido ----------------------------------------------

    def _al_mover(self, origen: int, hueco: int) -> None:
        if not self._reloj.movible(origen):
            self._avisar_bloqueado(origen)
            return
        if self._reloj.recorrido.mover(origen, hueco) < 0:
            return
        self._reloj.recolocar()
        self._reconstruir()

    def _al_nuevo(self, hueco: int) -> None:
        """Bloque nuevo, al final o en el hueco donde se pidio."""
        recorrido = self._reloj.recorrido
        # Alterna con el bloque de delante: detras de un trabajo apetece un
        # descanso. Sin nada delante, se empieza trabajando.
        if hueco < 0:
            previo = recorrido.bloques[-1]
        elif hueco == 0:
            previo = None
        else:
            previo = recorrido.bloques[min(hueco, recorrido.total) - 1]
        tipo = Fase.TRABAJO if previo is None or not previo.es_trabajo else Fase.DESCANSO_CORTO
        recorrido.nuevo(tipo, en=None if hueco < 0 else hueco)
        self._reconstruir()

    def _al_soltar_tema(self, materia_id: int, nombre: str, hueco: int) -> None:
        """Un tema arrastrado al timeline se convierte en un bloque de trabajo."""
        recorrido = self._reloj.recorrido
        bloque = recorrido.nuevo(Fase.TRABAJO, en=None if hueco < 0 else hueco)
        bloque.nombre = nombre
        bloque.materia_id = materia_id
        bloque.materia = nombre
        color = next(
            (m.color for i, m in enumerate(self._materias) if m.id == materia_id),
            None,
        )
        indice = next(
            (i for i, m in enumerate(self._materias) if m.id == materia_id), 0
        )
        bloque.color = color or tokens.color_serie(indice)
        bloque.editado = True
        self._reconstruir()

    def _al_editar(self, indice: int) -> None:
        recorrido = self._reloj.recorrido
        if not self._reloj.editable(indice):
            self._avisar_pasado()
            return
        ancla = self._timeline.tarjeta(indice)
        if ancla is None:
            return
        self._editor.abrir(
            recorrido.bloques[indice],
            indice,
            self._materias,
            ancla,
            se_puede_borrar=self._reloj.movible(indice) and recorrido.total > 1,
        )

    def _al_cambiar_bloque(self, indice: int, bloque: object) -> None:
        if not isinstance(bloque, Bloque):
            return
        self._reloj.reemplazar_bloque(indice, bloque)
        self._reconstruir()

    def _al_duplicar(self, indice: int) -> None:
        if not self._reloj.movible(indice):
            self._avisar_bloqueado(indice)
            return
        self._reloj.recorrido.duplicar(indice)
        self._reconstruir()

    def _al_eliminar(self, indice: int) -> None:
        if not self._reloj.movible(indice):
            self._avisar_bloqueado(indice)
            return
        if self._reloj.recorrido.eliminar(indice):
            self._reloj.recolocar()
            self._reconstruir()

    def _al_ir_a(self, indice: int) -> None:
        """Empezar por otro bloque, sin contar como hechos los de en medio."""
        if self._reloj.estado is Estado.CORRIENDO:
            self._avisar_bloqueado(self._reloj.recorrido.indice)
            return
        self._latido.stop()
        self._reloj.ir_a(indice)
        self._inicio_fase = None
        self._reconstruir()

    def _al_pedir_duracion(self, indice: int, minutos: int) -> None:
        """Rueda del raton sobre una tarjeta: ±5 min sin abrir el editor."""
        if not self._reloj.editable(indice):
            return
        self._reloj.ajustar_duracion(indice, minutos)
        self._pintar()

    def _avisar_bloqueado(self, indice: int) -> None:
        """Explica por que ese bloque no se deja tocar. Son dos razones distintas."""
        if self._reloj.recorrido.recorrido_de(indice):
            self._avisar_pasado()
            return
        self.aviso.emit(
            "Ese bloque esta en marcha",
            "Detén el reloj con Reiniciar para reordenar el bloque en curso.",
        )

    def _avisar_pasado(self) -> None:
        """Lo ya recorrido no se edita: cambiarlo falsearia lo registrado."""
        self.aviso.emit(
            "Ese bloque ya paso",
            "Los bloques completados no se editan: su tiempo ya esta registrado.",
        )

    # -- Control desde fuera ------------------------------------------------

    @property
    def reloj(self) -> RelojPomodoro:
        """Reloj en curso, para que la mini ventana lo muestre."""
        return self._reloj

    @property
    def cronometro(self) -> Cronometro:
        """Sesion indefinida en curso, para que la mini ventana la muestre."""
        return self._cronometro

    @property
    def sesion_libre_activa(self) -> bool:
        """Si hay una sesion de trabajo indefinida abierta, aunque este en pausa."""
        return self._cronometro.activo

    @property
    def corriendo(self) -> bool:
        """Si hay algo cronometrandose, y por tanto el reloj flotante debe salir.

        Una sesion indefinida cuenta tambien en pausa: no termina sola, asi que
        esconder su reloj dejaria «Detener» fuera de alcance con la ventana
        minimizada, que es justo cuando se usa.
        """
        return self._reloj.estado is Estado.CORRIENDO or self._cronometro.activo

    def alternar_reloj(self) -> None:
        """Inicia o pausa desde fuera de la vista (mini ventana, barra lateral).

        Con una sesion indefinida abierta el boton de fuera es el suyo: es lo
        que se esta viendo en el reloj flotante.
        """
        if self._cronometro.activo:
            self._alternar_libre()
        else:
            self._alternar()

    def detener_sesion_libre(self) -> None:
        """Cierra la sesion indefinida desde fuera de la vista."""
        if self._cronometro.activo:
            self._detener_libre()

    def finalizar_por_cierre(self) -> None:
        """Termina el pomodoro al cerrar la aplicacion.

        El reloj no sobrevive al cierre: no hay estado que restaurar al volver a
        abrir. Pero tirar el tiempo ya trabajado seria peor que no cronometrarlo,
        asi que una fase de trabajo con al menos un minuto se guarda como sesion
        **no completada**. La columna ``completada`` existe justo para esto: el
        tiempo cuenta en las estadisticas y el pomodoro no cuenta como logrado.
        """
        self._latido.stop()
        self._latido_libre.stop()

        # La sesion indefinida se cierra igual: nunca iba a terminar sola, asi
        # que al cerrar la aplicacion no hay nada que esperar. Sin dialogo de
        # temas, porque no puede abrirse uno mientras la ventana se va.
        transcurrido_libre = self._cronometro.detener()
        if transcurrido_libre >= _MINIMO_REGISTRABLE_SEG:
            self._guardar_sesion(
                Fase.TRABAJO,
                transcurrido_libre,
                completada=False,
                inicio=self._inicio_libre,
            )
            _log.info(
                "Sesion indefinida interrumpida al cerrar: %s",
                formato.horas(transcurrido_libre),
            )
        self._inicio_libre = None

        transcurrido = self._reloj.transcurrido_seg
        if self._reloj.fase is Fase.TRABAJO and transcurrido >= _MINIMO_REGISTRABLE_SEG:
            self._guardar_sesion(Fase.TRABAJO, transcurrido, completada=False)
            _log.info("Pomodoro interrumpido al cerrar: %s", formato.horas(transcurrido))

        self._reloj.reiniciar()
        self._inicio_fase = None

    # -- Control ------------------------------------------------------------

    def _alternar(self) -> None:
        # Sin proyecto activo `_registrar` no puede guardar nada y el tiempo se
        # tiraria en silencio. El boton ya sale deshabilitado, pero la mini
        # ventana tambien llama aqui, asi que la guardia va en el camino comun.
        if self.contexto.proyecto is None and self._reloj.estado is not Estado.CORRIENDO:
            return
        # Con una sesion indefinida abierta el pomodoro no arranca: las dos
        # registrarian la misma hora.
        if self._cronometro.activo and self._reloj.estado is not Estado.CORRIENDO:
            return
        if self._reloj.estado is not Estado.CORRIENDO and self._inicio_fase is None:
            self._inicio_fase = datetime.now().astimezone()
        self._reloj.alternar()
        if self._reloj.estado is Estado.CORRIENDO:
            self._latido.start()
        else:
            self._latido.stop()
        self._pintar()

    def _reiniciar(self) -> None:
        self._latido.stop()
        self._reloj.reiniciar()
        self._inicio_fase = None
        self._aplicar_pendiente()
        self._pintar()

    def _saltar(self) -> None:
        self._latido.stop()
        self._reloj.saltar()
        self._inicio_fase = None
        self._aplicar_pendiente()
        self._reconstruir()

    # -- Sesion de trabajo indefinida ---------------------------------------

    def _alternar_libre(self) -> None:
        """Abre, pausa o reanuda la sesion indefinida."""
        if self.contexto.proyecto is None:
            return
        if not self._cronometro.activo:
            if self._reloj.estado is Estado.CORRIENDO:
                self.aviso.emit(
                    "El Pomodoro esta en marcha",
                    "Pausa el pomodoro antes de abrir una sesion indefinida: "
                    "las dos contarian la misma hora dos veces.",
                )
                return
            self._inicio_libre = datetime.now().astimezone()

        self._cronometro.alternar()
        if self._cronometro.corriendo:
            self._latido_libre.start()
        else:
            self._latido_libre.stop()
        self._pintar()

    def _detener_libre(self) -> None:
        """Cierra la sesion indefinida, la registra y pregunta el tema."""
        self._latido_libre.stop()
        transcurrido = self._cronometro.detener()
        inicio, self._inicio_libre = self._inicio_libre, None
        # Se repinta antes de preguntar: el dialogo de temas es modal y dejaria
        # el anillo congelado en el ultimo segundo de una sesion ya cerrada.
        self._pintar()
        self._registrar_libre(transcurrido, inicio)

    def _registrar_libre(self, transcurrido: int, inicio: datetime | None) -> None:
        """Guarda la sesion indefinida como tiempo de trabajo completado."""
        if transcurrido < _MINIMO_REGISTRABLE_SEG:
            if transcurrido > 0:
                self.aviso.emit(
                    "Sesion demasiado corta",
                    "Por debajo de un minuto no se registra nada.",
                )
            return

        sesion_id = self._guardar_sesion(
            Fase.TRABAJO, transcurrido, completada=True, inicio=inicio
        )
        if sesion_id is None:
            return

        _log.info("Sesion indefinida registrada: %s", formato.horas(transcurrido))
        self.aviso.emit(
            f"Sesion registrada · {formato.horas(transcurrido)}",
            "El tiempo ya cuenta en el calendario y en las estadisticas.",
        )
        self._preguntar_materias(sesion_id, transcurrido)
        self.contexto.notificar_cambio(self)

    def _tic_libre(self) -> None:
        self._cronometro.avanzar(1)
        self._pintar()

    def _tic(self) -> None:
        terminada = self._reloj.avanzar(1)
        if terminada is not None:
            self._latido.stop()
            self._registrar(terminada)
            self._inicio_fase = None
            self._aplicar_pendiente()
            # El recorrido puede haberse alargado al pasar de bloque.
            self._reconstruir()
            return
        self._pintar()

    def _aplicar_pendiente(self) -> None:
        """Aplica la configuracion editada mientras el reloj estaba corriendo."""
        guardada = self.contexto.preferencias.cargar().pomodoro
        if guardada != self._reloj.configuracion:
            self._reloj.aplicar(guardada)
            # Se avisa solo cuando el cambio surte efecto de verdad, no en cada
            # pulsacion del spinbox: eso seria una lluvia de notificaciones.
            self.aviso.emit(
                "Nueva configuracion aplicada",
                f"Trabajo {guardada.trabajo_min} min · descansos "
                f"{guardada.descanso_corto_min}/{guardada.descanso_largo_min} min.",
            )
        self._aviso_config.setText("")

    # -- Persistencia -------------------------------------------------------

    def _guardar_sesion(
        self,
        fase: Fase,
        duracion_seg: int,
        *,
        completada: bool,
        inicio: datetime | None = None,
    ) -> int | None:
        """Persiste una sesion y devuelve su id, o ``None`` sin proyecto activo.

        ``inicio`` lo pasa la sesion indefinida, que lleva el suyo propio; el
        Pomodoro se apoya en el de la fase en curso.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return None

        fin = datetime.now().astimezone()
        inicio = inicio or self._inicio_fase or (fin - timedelta(seconds=duracion_seg))
        sesion = self.contexto.sesiones.crear(
            proyecto.id,
            tipo=fase.a_tipo_sesion(),
            origen=OrigenSesion.POMODORO,
            inicio=inicio,
            fin=fin,
            duracion_seg=duracion_seg,
            completada=completada,
        )
        return sesion.id

    def _registrar(self, terminada: FaseTerminada) -> None:
        """Guarda la fase completada y, si procede, pregunta las materias."""
        sesion_id = self._guardar_sesion(
            terminada.fase, terminada.duracion_seg, completada=True
        )
        if sesion_id is None:
            return

        _log.info(
            "Sesion registrada: %s de %s", terminada.fase.etiqueta,
            formato.horas(terminada.duracion_seg),
        )
        self._avisar_de_la_fase(terminada)
        self.fase_termino.emit(terminada.fase, self._reloj.fase)

        if terminada.fase is Fase.TRABAJO:
            self._etiquetar(sesion_id, terminada)
        self.contexto.notificar_cambio(self)

    def _etiquetar(self, sesion_id: int, terminada: FaseTerminada) -> None:
        """Asigna las materias de la sesion.

        Si el bloque llevaba un tema, no hay nada que preguntar: el usuario ya lo
        dijo al armar el recorrido, y volver a preguntarlo seria un dialogo de
        mas cada veinticinco minutos.
        """
        bloque = terminada.bloque
        if bloque is not None and bloque.materia_id is not None:
            self.contexto.sesiones.etiquetar(sesion_id, [bloque.materia_id])
            return
        self._preguntar_materias(sesion_id, terminada.duracion_seg)

    def _avisar_de_la_fase(self, terminada: FaseTerminada) -> None:
        """Notificacion del sistema al terminar una fase."""
        siguiente = self._reloj.bloque
        minutos = siguiente.duracion_min
        if terminada.fase is Fase.TRABAJO:
            titulo = f"Pomodoro completado · {formato.horas(terminada.duracion_seg)}"
            cuerpo = f"Toca {siguiente.tipo.etiqueta.lower()} de {minutos} min."
        else:
            titulo = f"{terminada.fase.etiqueta} terminado"
            cuerpo = f"Vuelta al trabajo: {siguiente.etiqueta}, {minutos} min."
        self.aviso.emit(titulo, f"{cuerpo} Pulsa Iniciar cuando estes listo.")

    def _preguntar_materias(self, sesion_id: int, duracion_seg: int) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None or not self.contexto.preferencias.cargar().preguntar_materia:
            return

        dialogo = DialogoEtiquetar(
            self.contexto.materias.listar(proyecto.id), duracion_seg, self
        )
        aceptado = dialogo.exec()

        if dialogo.no_volver_a_preguntar:
            previas = self.contexto.preferencias.cargar()
            self.contexto.preferencias.guardar(
                Preferencias(pomodoro=previas.pomodoro, preguntar_materia=False)
            )
        if aceptado and (elegidas := dialogo.materias_elegidas):
            self.contexto.sesiones.etiquetar(sesion_id, elegidas)
