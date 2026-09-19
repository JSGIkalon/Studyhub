"""Progreso: marcar modulos y editar el temario.

El progreso es manual y esta desacoplado del Pomodoro: se marca lo estudiado,
no lo cronometrado.

El temario se edita **aqui dentro**, modulo a modulo: renombrar, mover, borrar y
anadir debajo. El curriculo del CFA se renumera cada ano —un modulo cambia de
nombre, o se parte en tres— y hasta ahora la unica salida era reimportar el
Excel o entrar a mano en el SQLite.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.modelos import Materia, Modulo, Prioridad
from mukuwareru.nucleo.servicios import CargaMateria, ResumenProgreso
from mukuwareru.ui import iconos
from mukuwareru.ui.dialogos.carga import DialogoCarga, color_de_prioridad
from mukuwareru.ui.dialogos.color_materia import DialogoColorMateria
from mukuwareru.ui.dialogos.importar import DialogoImportar
from mukuwareru.ui.dialogos.pesos import DialogoPesos
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import BarraMateria, Tarjeta, contenedor


class VistaProgreso(VistaBase):
    """Materias plegables con una casilla por modulo."""

    titulo = "Progreso"

    def _construir(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        raiz.addWidget(desplazable)

        lienzo = QWidget()
        self._columna = QVBoxLayout(lienzo)
        self._columna.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
        )
        self._columna.setSpacing(tokens.ESPACIO)
        desplazable.setWidget(lienzo)

        self._columna.addLayout(self._construir_cabecera())

        self._caja_materias = QVBoxLayout()
        self._caja_materias.setSpacing(tokens.ESPACIO_PEQUENO)
        self._columna.addLayout(self._caja_materias)
        self._columna.addStretch(1)

        # Que materias estaban desplegadas. Cada edicion de un modulo reconstruye
        # la vista entera, y sin esto la seccion se cerraria en las narices del
        # usuario despues de cada renombrado.
        self._desplegadas: set[int] = set()

        # Secciones vivas por materia, para que `enfocar` pueda llegar a una sin
        # recorrer el arbol de widgets.
        self._secciones: dict[int, SeccionMateria] = {}
        self._pendiente_de_enfocar: int | None = None

    def _construir_cabecera(self) -> QVBoxLayout:
        cabecera = QVBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        fila = QHBoxLayout()
        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        fila.addWidget(titulo)
        fila.addStretch(1)

        importar = QPushButton("  Importar desde Excel")
        importar.setIcon(iconos.icono("documento", tokens.TEXTO_SUAVE))
        importar.clicked.connect(self._importar)
        fila.addWidget(importar)

        pesos = QPushButton("  Pesos")
        pesos.setIcon(iconos.icono("grafico", tokens.TEXTO_SUAVE))
        pesos.setToolTip(
            "Cuanto pesa cada asignatura en el avance del proyecto. "
            "Sin pesos, todos los modulos valen igual."
        )
        pesos.clicked.connect(self._editar_pesos)
        fila.addWidget(pesos)

        nueva = QPushButton("  Nueva materia")
        nueva.setIcon(iconos.icono("mas", tokens.TEXTO_SUAVE))
        nueva.clicked.connect(self._nueva_materia)
        fila.addWidget(nueva)
        cabecera.addLayout(fila)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoSuave")
        cabecera.addWidget(self._resumen)
        return cabecera

    # -- Datos --------------------------------------------------------------

    def recargar(self) -> None:
        """Reconstruye la lista de materias del proyecto activo."""
        while (elemento := self._caja_materias.takeAt(0)) is not None:
            if (widget := elemento.widget()) is not None:
                widget.deleteLater()

        proyecto = self.contexto.proyecto
        if proyecto is None:
            self._resumen.setText("Sin proyecto seleccionado.")
            return

        avance = self.contexto.progreso.resumen(proyecto.id)
        self._escribir_resumen(avance)

        if not avance.materias:
            vacio = QLabel(
                "Importa tu Excel o crea la primera materia para empezar a "
                "llevar el progreso."
            )
            vacio.setObjectName("TextoTenue")
            vacio.setWordWrap(True)
            self._caja_materias.addWidget(vacio)
            return

        materias = self.contexto.materias.listar(proyecto.id)
        cargas = {c.materia_id: c for c in self.contexto.carga.resumen(proyecto.id)}
        ultima = len(materias) - 1
        self._secciones = {}
        for indice, materia in enumerate(materias):
            progreso = next(
                (m for m in avance.materias if m.materia_id == materia.id), None
            )
            seccion = SeccionMateria(
                self.contexto,
                materia,
                completados=progreso.completados if progreso else 0,
                total=progreso.total if progreso else 0,
                color=tokens.color_o_serie(materia.color, indice),
                carga=cargas.get(materia.id),
                desplegada=materia.id in self._desplegadas,
                cuota=(
                    avance.cuota(progreso)
                    if avance.hay_pesos and progreso is not None
                    else None
                ),
                posicion=indice,
                ultima=ultima,
            )
            seccion.cambiada.connect(self._al_cambiar)
            seccion.marcado.connect(self._al_marcar)
            seccion.plegado_cambiado.connect(self._recordar_plegado)
            self._caja_materias.addWidget(seccion)
            self._secciones[materia.id] = seccion

        # El grafo puede pedir que se enfoque una materia justo despues de
        # navegar hasta aqui, cuando la vista todavia estaba sucia.
        if self._pendiente_de_enfocar is not None:
            objetivo, self._pendiente_de_enfocar = self._pendiente_de_enfocar, None
            self.enfocar(objetivo)

    def enfocar(self, materia_id: int) -> None:
        """Despliega una materia y la trae a la vista.

        Es el punto de entrada desde el grafo: hacer doble clic en un nodo lleva
        a la informacion que ya existe, en lugar de repetirla dentro del lienzo.
        """
        seccion = self._secciones.get(materia_id)
        if seccion is None:
            # La vista aun no se ha recargado con este proyecto; se anota para
            # atenderlo en cuanto termine `recargar`.
            self._pendiente_de_enfocar = materia_id
            self.marcar_sucia()
            self.refrescar_si_hace_falta()
            return
        self._desplegadas.add(materia_id)
        seccion.desplegar()
        seccion.setFocus()
        if (desplazable := self.findChild(QScrollArea)) is not None:
            desplazable.ensureWidgetVisible(seccion)

    def _escribir_resumen(self, avance: ResumenProgreso) -> None:
        """La linea de cifras de la cabecera. La comparten recargar y marcar."""
        if not avance.total:
            self._resumen.setText("Este proyecto aun no tiene temario.")
            return
        texto = (
            f"{avance.completados} de {avance.total} modulos completados "
            f"({avance.porcentaje} %)"
        )
        if avance.hay_pesos:
            texto += f"  ·  ponderado por asignatura: {avance.porcentaje_ponderado} %"
        self._resumen.setText(texto)

    def _recordar_plegado(self, materia_id: int, desplegada: bool) -> None:
        """Anota si la materia queda abierta, para restaurarla tras recargar."""
        if desplegada:
            self._desplegadas.add(materia_id)
        else:
            self._desplegadas.discard(materia_id)

    def _al_cambiar(self) -> None:
        """Refresca esta vista entera y avisa al resto. Para cambios de estructura.

        Reconstruir es lo correcto cuando se anade, renombra, mueve o borra: la
        lista de secciones deja de ser valida. **No** para marcar una casilla:
        eso pasa por `_al_marcar`.
        """
        self.marcar_sucia()
        self.refrescar_si_hace_falta()
        self.contexto.notificar_cambio(self)

    def _al_marcar(self) -> None:
        """Actualiza las cifras sin reconstruir la vista.

        Marcar un modulo pasaba por `_al_cambiar`, asi que cada casilla
        reconstruia la vista entera: marcar los nueve modulos de un tema eran
        nueve reconstrucciones, con su perdida de scroll y de foco. Aqui solo se
        reescriben el resumen de arriba y la barra de la seccion que lo pidio.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return

        avance = self.contexto.progreso.resumen(proyecto.id)
        self._escribir_resumen(avance)

        emisora = self.sender()
        if isinstance(emisora, SeccionMateria):
            progreso = next(
                (m for m in avance.materias if m.materia_id == emisora.materia.id), None
            )
            if progreso is not None:
                emisora.refrescar_barra(
                    progreso.completados,
                    progreso.total,
                    avance.cuota(progreso) if avance.hay_pesos else None,
                )

        # El Panel ensena el mismo avance, asi que si tiene que enterarse. A esta
        # vista no se la marca sucia: acaba de actualizarse a mano.
        self.contexto.notificar_cambio(self)

    # -- Acciones -----------------------------------------------------------

    def _nueva_materia(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        nombre, aceptado = QInputDialog.getText(self, "Nueva materia", "Nombre:")
        if not aceptado or not (nombre := nombre.strip()):
            return
        if self.contexto.materias.obtener_por_nombre(proyecto.id, nombre) is not None:
            QMessageBox.information(self, "Nueva materia", f"«{nombre}» ya existe.")
            return
        orden = len(self.contexto.materias.listar(proyecto.id))
        self.contexto.materias.crear(proyecto.id, nombre, orden=orden)
        self._al_cambiar()

    def _importar(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        if DialogoImportar(self.contexto, proyecto, self).exec():
            self._al_cambiar()

    def _editar_pesos(self) -> None:
        """Reparte el peso de cada asignatura. Es lo unico que pondera el avance."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return

        materias = self.contexto.materias.listar(proyecto.id)
        if not materias:
            QMessageBox.information(
                self,
                "Peso de las asignaturas",
                "Crea alguna materia antes de repartir los pesos.",
            )
            return

        avance = self.contexto.progreso.resumen(proyecto.id)
        dialogo = DialogoPesos(
            materias,
            {m.materia_id: m.total for m in avance.materias},
            propuesta_cfa=self.contexto.progreso.pesos_cfa(proyecto.id),
            parent=self,
        )
        if dialogo.exec():
            self.contexto.progreso.fijar_pesos(proyecto.id, dialogo.pesos())
            self._al_cambiar()


class SeccionMateria(Tarjeta):
    """Una materia plegable con sus modulos."""

    # `cambiada` reconstruye la vista entera: es para lo estructural. `marcado`
    # solo actualiza cifras, que es lo que hace falta al pulsar una casilla.
    cambiada = Signal()
    marcado = Signal()
    plegado_cambiado = Signal(int, bool)   # materia_id, desplegada

    def __init__(
        self,
        contexto: Contexto,
        materia: Materia,
        *,
        completados: int,
        total: int,
        color: str,
        carga: CargaMateria | None = None,
        desplegada: bool = False,
        cuota: float | None = None,
        posicion: int = 0,
        ultima: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.contexto = contexto
        self.materia = materia
        self._carga = carga
        self._desplegada = False
        self._posicion = posicion
        self._ultima = ultima
        self._color = color
        self.contenido.setSpacing(tokens.ESPACIO_PEQUENO)
        self._construir(completados, total, color, cuota)
        if desplegada:
            self._alternar(avisar=False)

    def _construir(
        self, completados: int, total: int, color: str, cuota: float | None
    ) -> None:
        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        self._plegar = QPushButton("▸")
        self._plegar.setObjectName("ElementoNav")
        self._plegar.setFixedWidth(24)
        self._plegar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plegar.clicked.connect(self._alternar)
        fila.addWidget(self._plegar)

        self._fila_barra = fila
        self._barra = BarraMateria(
            self.materia.nombre, completados, total, color, cuota=cuota
        )
        fila.addWidget(self._barra, 1)

        # Anadir un modulo era la accion mas frecuente de la vista y estaba
        # escondida dentro del menu ⋯. Aqui tiene su propio boton.
        anadir = QPushButton("+")
        anadir.setObjectName("ElementoNav")
        anadir.setFixedWidth(28)
        anadir.setCursor(Qt.CursorShape.PointingHandCursor)
        anadir.setToolTip(f"Anadir un modulo a «{self.materia.nombre}»")
        anadir.clicked.connect(self._anadir_modulo)
        fila.addWidget(anadir)

        opciones = QPushButton("⋯")
        opciones.setObjectName("ElementoNav")
        opciones.setFixedWidth(28)
        opciones.setCursor(Qt.CursorShape.PointingHandCursor)
        opciones.clicked.connect(self._menu)
        fila.addWidget(opciones)
        self.contenido.addWidget(contenedor(fila))

        if (linea := self._linea_de_carga()) is not None:
            self.contenido.addWidget(linea)

        self._caja_modulos = QVBoxLayout()
        self._caja_modulos.setContentsMargins(32, 0, 0, 0)
        self._caja_modulos.setSpacing(0)
        self._contenedor_modulos = contenedor(self._caja_modulos)
        self._contenedor_modulos.setVisible(False)
        self.contenido.addWidget(self._contenedor_modulos)

    def _linea_de_carga(self) -> QLabel | None:
        """Horas, prioridad y fecha limite, si se han declarado.

        Solo aparece cuando hay algo que contar. Una linea que dice «sin horas,
        prioridad media, sin fecha» en las diez asignaturas es ruido.
        """
        carga = self._carga
        if carga is None:
            return None

        trozos: list[str] = []
        if carga.estimada or carga.sobrescrita:
            restantes = carga.horas_restantes
            if carga.horas_estimadas:
                trozos.append(
                    f"{carga.horas_dedicadas:.0f} / {carga.horas_estimadas:.0f} h"
                )
            trozos.append(
                f"quedan {restantes:.0f} h" + (" (a mano)" if carga.sobrescrita else "")
            )
        if carga.prioridad is not Prioridad.MEDIA:
            trozos.append(f"prioridad {carga.prioridad.etiqueta.lower()}")
        if carga.fecha_limite is not None:
            trozos.append(f"limite {carga.fecha_limite.strftime('%d/%m/%Y')}")

        if not trozos:
            return None

        etiqueta = QLabel("  ·  ".join(trozos))
        etiqueta.setObjectName("TextoTenue")
        etiqueta.setContentsMargins(32, 0, 0, 0)
        if carga.prioridad in (Prioridad.ALTA, Prioridad.CRITICA):
            etiqueta.setStyleSheet(f"color: {color_de_prioridad(carga.prioridad)};")
        return etiqueta

    def desplegar(self) -> None:
        """Abre la seccion si estaba plegada. Lo usa `VistaProgreso.enfocar`."""
        if not self._desplegada:
            self._alternar(avisar=False)

    def _editar_carga(self) -> None:
        """Horas, prioridad y fecha limite de esta asignatura."""
        carga = self._carga
        if carga is None:
            return
        dialogo = DialogoCarga(carga, self)
        if not dialogo.exec():
            return
        datos = dialogo.datos()
        self.contexto.carga.fijar(
            self.materia.id,
            horas_estimadas=datos.horas_estimadas,
            horas_restantes_manual=datos.horas_restantes_manual,
            prioridad=datos.prioridad,
            fecha_limite=datos.fecha_limite,
        )
        # Estructural: el Panel y el grafo leen estos mismos datos.
        self.cambiada.emit()

    def _alternar(self, *, avisar: bool = True) -> None:
        self._desplegada = not self._desplegada
        self._plegar.setText("▾" if self._desplegada else "▸")
        if self._desplegada and self._caja_modulos.count() == 0:
            self._cargar_modulos()
        self._contenedor_modulos.setVisible(self._desplegada)
        if avisar:
            self.plegado_cambiado.emit(self.materia.id, self._desplegada)

    def _cargar_modulos(self) -> None:
        modulos = self.contexto.modulos.listar(self.materia.id)
        if not modulos:
            vacio = QLabel("Sin modulos. Anade el primero con el boton +")
            vacio.setObjectName("TextoTenue")
            self._caja_modulos.addWidget(vacio)
            return

        ultimo = len(modulos) - 1
        for posicion, modulo in enumerate(modulos):
            casilla = QCheckBox(modulo.nombre)
            casilla.setChecked(modulo.completado)
            casilla.setCursor(Qt.CursorShape.PointingHandCursor)
            casilla.setToolTip(
                f"{posicion + 1} de {len(modulos)}  ·  clic derecho para editarlo"
            )
            casilla.toggled.connect(
                lambda marcado, identificador=modulo.id: self._marcar(identificador, marcado)
            )
            casilla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            casilla.customContextMenuRequested.connect(
                lambda _punto, m=modulo, p=posicion, u=ultimo: self._menu_modulo(m, p, u)
            )
            self._caja_modulos.addWidget(casilla)

    def _marcar(self, modulo_id: int, completado: bool) -> None:
        self.contexto.progreso.marcar(modulo_id, completado)
        self.marcado.emit()

    def refrescar_barra(
        self, completados: int, total: int, cuota: float | None
    ) -> None:
        """Repinta la barra con las cifras nuevas, sin tocar las casillas.

        `BarraMateria` se pinta entera en un `paintEvent` a partir de valores
        fijados en el constructor, asi que se sustituye en vez de mutarla: es una
        fila, no vale la pena darle setters.
        """
        nueva = BarraMateria(
            self.materia.nombre, completados, total, self._color, cuota=cuota
        )
        self._fila_barra.replaceWidget(self._barra, nueva)
        self._barra.deleteLater()
        self._barra = nueva

    # -- Edicion de un modulo ------------------------------------------------

    def _menu_modulo(self, modulo: Modulo, posicion: int, ultimo: int) -> None:
        """Menu de un modulo suelto: el temario se corrige desde aqui."""
        menu = QMenu(self)
        menu.addAction("Renombrar…", lambda: self._renombrar_modulo(modulo))
        menu.addAction("Anadir modulo debajo…", lambda: self._insertar_tras(modulo))
        menu.addSeparator()

        subir = menu.addAction("Subir", lambda: self._mover_modulo(modulo, -1))
        subir.setEnabled(posicion > 0)
        bajar = menu.addAction("Bajar", lambda: self._mover_modulo(modulo, 1))
        bajar.setEnabled(posicion < ultimo)

        hermanas = [
            m
            for m in self.contexto.materias.listar(self.materia.proyecto_id)
            if m.id != self.materia.id
        ]
        if hermanas:
            destino = menu.addMenu("Mover a otra materia")
            for otra in hermanas:
                destino.addAction(
                    otra.nombre, lambda _=False, d=otra: self._mover_a_materia(modulo, d)
                )

        menu.addSeparator()
        menu.addAction("Eliminar…", lambda: self._eliminar_modulo(modulo))
        menu.exec(self.cursor().pos())

    def _mover_a_materia(self, modulo: Modulo, destino: Materia) -> None:
        """Traslada el modulo conservando su estado. Ver `mover_a_materia`."""
        if self.contexto.modulos.mover_a_materia(modulo.id, destino.id):
            self.cambiada.emit()
            return
        QMessageBox.information(
            self,
            "Mover modulo",
            f"«{destino.nombre}» ya tiene un modulo llamado «{modulo.nombre}».\n"
            "Renombra uno de los dos antes de moverlo.",
        )

    def _renombrar_modulo(self, modulo: Modulo) -> None:
        nombre, aceptado = QInputDialog.getText(
            self, "Renombrar modulo", "Nombre:", text=modulo.nombre
        )
        if not aceptado or not (nombre := nombre.strip()) or nombre == modulo.nombre:
            return
        self.contexto.modulos.renombrar(modulo.id, nombre)
        self.cambiada.emit()

    def _insertar_tras(self, modulo: Modulo) -> None:
        """Crea un modulo justo debajo. Es como se parte un LM en varios."""
        nombre, aceptado = QInputDialog.getText(
            self, "Nuevo modulo", f"Nombre del modulo que va tras «{modulo.nombre}»:"
        )
        if not aceptado or not (nombre := nombre.strip()):
            return
        self.contexto.modulos.insertar_tras(modulo.id, nombre)
        self.cambiada.emit()

    def _mover_modulo(self, modulo: Modulo, desplazamiento: int) -> None:
        if self.contexto.modulos.mover(modulo.id, desplazamiento):
            self.cambiada.emit()

    def _eliminar_modulo(self, modulo: Modulo) -> None:
        aviso = (
            "Esta marcado como completado, asi que el porcentaje del tema bajara.\n"
            if modulo.completado
            else ""
        )
        respuesta = QMessageBox.question(
            self,
            "Eliminar modulo",
            f"Se eliminara «{modulo.nombre}».\n{aviso}"
            "Esta accion no se puede deshacer.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self.contexto.modulos.eliminar(modulo.id)
            self.cambiada.emit()

    # -- Menu ---------------------------------------------------------------

    def _menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Anadir modulo", self._anadir_modulo)
        menu.addAction("Renombrar materia", self._renombrar)
        menu.addAction("Color…", self._elegir_color)
        carga = menu.addAction("Horas, prioridad y fecha limite…", self._editar_carga)
        carga.setEnabled(self._carga is not None)
        menu.addSeparator()

        subir = menu.addAction("Subir", lambda: self._mover_materia(-1))
        subir.setEnabled(self._posicion > 0)
        bajar = menu.addAction("Bajar", lambda: self._mover_materia(1))
        bajar.setEnabled(self._posicion < self._ultima)
        menu.addSeparator()

        menu.addAction("Marcar todos los modulos", lambda: self._marcar_todos(True))
        menu.addAction("Desmarcar todos…", lambda: self._marcar_todos(False))
        menu.addSeparator()

        menu.addAction("Eliminar materia", self._eliminar)
        menu.exec(self.cursor().pos())

    def _mover_materia(self, desplazamiento: int) -> None:
        if self.contexto.materias.mover(self.materia.id, desplazamiento):
            self.cambiada.emit()

    def _elegir_color(self) -> None:
        dialogo = DialogoColorMateria(self.materia, self)
        if dialogo.exec():
            self.contexto.materias.fijar_color(self.materia.id, dialogo.color())
            # Estructural a proposito: el Panel pinta las mismas barras.
            self.cambiada.emit()

    def _marcar_todos(self, completado: bool) -> None:
        """Marca o desmarca la materia entera de una vez.

        Desmarcar pregunta porque destruye progreso —y la fecha en que se
        logro—; marcar no, porque se deshace pulsando la casilla.
        """
        if not completado:
            respuesta = QMessageBox.question(
                self,
                "Desmarcar la materia",
                f"Se desmarcaran todos los modulos de «{self.materia.nombre}» y se "
                "perdera la fecha en que los completaste.",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                return

        if self.contexto.progreso.marcar_materia(self.materia.id, completado):
            # Reconstruye: hay que repintar todas las casillas, no solo la barra.
            self.cambiada.emit()

    def _anadir_modulo(self) -> None:
        nombre, aceptado = QInputDialog.getText(self, "Nuevo modulo", "Nombre:")
        if not aceptado or not (nombre := nombre.strip()):
            return
        orden = len(self.contexto.modulos.listar(self.materia.id))
        self.contexto.modulos.crear(self.materia.id, nombre, orden=orden)
        self.cambiada.emit()

    def _renombrar(self) -> None:
        nombre, aceptado = QInputDialog.getText(
            self, "Renombrar materia", "Nombre:", text=self.materia.nombre
        )
        if not aceptado or not (nombre := nombre.strip()):
            return
        self.contexto.materias.renombrar(self.materia.id, nombre)
        self.cambiada.emit()

    def _eliminar(self) -> None:
        cuantos = len(self.contexto.modulos.listar(self.materia.id))
        respuesta = QMessageBox.question(
            self,
            "Eliminar materia",
            f"Se eliminara «{self.materia.nombre}» y sus {cuantos} modulos.\n"
            "Esta accion no se puede deshacer.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self.contexto.materias.eliminar(self.materia.id)
            self.cambiada.emit()
