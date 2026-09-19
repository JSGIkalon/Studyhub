"""Ajustes: el proyecto activo, la barra lateral y los datos.

Las duraciones del Pomodoro **no** estan aqui: viven en la vista Pomodoro,
porque cada sesion de estudio es distinta y cambiarlas debe costar un clic, no
un viaje a otra pantalla.

La fecha objetivo y la carpeta de PDFs tampoco tienen campos propios: se editan
en ``DialogoProyecto``, el mismo que crea el proyecto. Dos formularios para los
mismos datos es la forma segura de que uno se quede atras.

Cada opcion que no aporta al estudio es una opcion que no existe.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.servicios import DisposicionSecciones, PlanSemanal
from mukuwareru.ui import atajos, iconos
from mukuwareru.ui.dialogos import DialogoProyecto
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import Tarjeta, contenedor
from mukuwareru.utilidades import rutas

# Ajustes no se puede ocultar: seria el unico camino de vuelta. El servicio de
# preferencias lo garantiza; aqui solo se refleja en la interfaz.
_IRRENUNCIABLE = "ajustes"

_DIAS_SEMANA = ("Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom")

# Ancho de la columna de teclas del manual de atajos. Fijo para que las
# combinaciones queden alineadas en una columna y se lean de un vistazo.
_ANCHO_TECLA = 96


class VistaAjustes(VistaBase):
    """Proyecto activo, disposicion de la barra lateral y rutas de datos."""

    titulo = "Ajustes"

    def _construir(self) -> None:
        # Evita que volcar los valores guardados dispare el guardado.
        self._cargando_plan = True

        # Con la tarjeta de atajos la vista ya no cabe entera en una ventana
        # pequena, asi que se desplaza como las demas.
        marco = QVBoxLayout(self)
        marco.setContentsMargins(0, 0, 0, 0)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        marco.addWidget(desplazable)

        lienzo = QWidget()
        raiz = QVBoxLayout(lienzo)
        raiz.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
        )
        raiz.setSpacing(tokens.ESPACIO)
        desplazable.setWidget(lienzo)

        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        raiz.addWidget(titulo)

        raiz.addWidget(self._tarjeta_proyecto())
        raiz.addWidget(self._tarjeta_plan())
        raiz.addWidget(self._tarjeta_barra_lateral())
        raiz.addWidget(self._tarjeta_atajos())
        raiz.addWidget(self._tarjeta_datos())
        raiz.addStretch(1)

    # -- Plan de estudio -----------------------------------------------------

    def _tarjeta_plan(self) -> Tarjeta:
        """Minutos por dia de la semana. Opcional: apagado no molesta a nadie."""
        self._tarjeta_del_plan = Tarjeta("Plan de estudio")

        self._plan_activo = QCheckBox("Usar un plan semanal")
        self._plan_activo.toggled.connect(self._al_cambiar_plan)
        self._tarjeta_del_plan.agregar(self._plan_activo)

        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)
        self._campos_plan: list[QSpinBox] = []
        for indice, nombre in enumerate(_DIAS_SEMANA):
            columna = QVBoxLayout()
            columna.setSpacing(2)
            etiqueta = QLabel(nombre)
            etiqueta.setObjectName("TextoTenue")
            etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
            columna.addWidget(etiqueta)

            campo = QSpinBox()
            campo.setRange(0, 16 * 60)
            campo.setSingleStep(15)
            campo.setSuffix(" m")
            campo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            campo.valueChanged.connect(self._al_cambiar_plan)
            campo.setToolTip(f"Minutos previstos para el {nombre.lower()}")
            columna.addWidget(campo)
            self._campos_plan.append(campo)
            fila.addLayout(columna, 1)
            del indice
        self._tarjeta_del_plan.agregar(contenedor(fila))

        self._resumen_plan = QLabel()
        self._resumen_plan.setObjectName("TextoSuave")
        self._resumen_plan.setWordWrap(True)
        self._tarjeta_del_plan.agregar(self._resumen_plan)

        generar = QPushButton("Generar bloques en el calendario…")
        generar.setCursor(Qt.CursorShape.PointingHandCursor)
        generar.clicked.connect(self._generar_plan)
        self._tarjeta_del_plan.agregar(generar)

        pista = QLabel(
            "El plan no obliga a nada: sirve para calcular el ritmo que necesitas "
            "y, si quieres, para pre-rellenar el calendario."
        )
        pista.setObjectName("TextoTenue")
        pista.setWordWrap(True)
        self._tarjeta_del_plan.agregar(pista)
        return self._tarjeta_del_plan

    def _al_cambiar_plan(self) -> None:
        """Guarda al momento, como la disposicion de la barra."""
        proyecto = self.contexto.proyecto
        if proyecto is None or self._cargando_plan:
            return
        plan = PlanSemanal(
            minutos=tuple(campo.value() for campo in self._campos_plan),
            activo=self._plan_activo.isChecked(),
        )
        self.contexto.plan.guardar(proyecto.id, plan)
        self._pintar_resumen_plan(plan)
        self.contexto.notificar_cambio(self)

    def _pintar_resumen_plan(self, plan: PlanSemanal) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        texto = f"{plan.horas_semana:.1f} h a la semana."
        diagnostico = self.contexto.plan.diagnostico(proyecto.id)
        if diagnostico.hay_fecha:
            texto += (
                f"  Para llegar a «{diagnostico.titulo_hito}» en "
                f"{diagnostico.dias_restantes} dias hacen falta "
                f"{diagnostico.horas_por_semana_necesarias:.1f} h/semana "
                f"({diagnostico.modulos_por_semana:.1f} modulos)."
            )
        self._resumen_plan.setText(texto)

    def _generar_plan(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return

        hoy = date.today()
        proximo = self.contexto.calendario.proxima_fecha_clave(proyecto.id, hoy)
        hasta = proximo.fecha if proximo is not None else hoy + timedelta(days=28)
        if hasta < hoy:
            hasta = hoy + timedelta(days=28)

        prevision = self.contexto.plan.prever(proyecto.id, hoy, hasta)
        if not prevision.bloques:
            QMessageBox.information(
                self,
                "Generar bloques",
                "No hay nada que anadir: o el plan esta a cero, o esos dias ya "
                "tienen bloques.",
            )
            return

        # Vista previa antes de escribir, como el asistente de importacion:
        # llenar el calendario de golpe es dificil de deshacer.
        respuesta = QMessageBox.question(
            self,
            "Generar bloques",
            f"Se crearan {len(prevision.bloques)} bloques hasta el "
            f"{hasta.strftime('%d/%m/%Y')}, con {prevision.minutos // 60} h en total."
            + (f"\n\n{prevision.omitidos} dias ya tenian bloque y se omiten."
               if prevision.omitidos else ""),
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return

        creados = self.contexto.plan.generar(proyecto.id, prevision)
        self.contexto.notificar_cambio(self)
        QMessageBox.information(
            self, "Plan generado", f"{creados} bloques anadidos al calendario."
        )

    # -- Proyecto -----------------------------------------------------------

    def _tarjeta_proyecto(self) -> Tarjeta:
        self._tarjeta_del_proyecto = Tarjeta("Proyecto")

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoSuave")
        self._resumen.setWordWrap(True)
        self._tarjeta_del_proyecto.agregar(self._resumen)

        editar = QPushButton("Editar proyecto…")
        editar.setObjectName("BotonPrimario")
        editar.setCursor(Qt.CursorShape.PointingHandCursor)
        editar.clicked.connect(self._editar_proyecto)
        self._tarjeta_del_proyecto.agregar(editar)

        pista = QLabel(
            "Nombre, icono, color, fecha objetivo y carpeta de PDFs. "
            "Tambien con clic derecho sobre el proyecto en la barra lateral, "
            "donde ademas se archiva, reordena y elimina."
        )
        pista.setObjectName("TextoTenue")
        pista.setWordWrap(True)
        self._tarjeta_del_proyecto.agregar(pista)
        return self._tarjeta_del_proyecto

    def _editar_proyecto(self) -> None:
        """Delega en la ventana principal, que sabe refrescar lo que toca.

        La vista podria guardar por su cuenta, pero renombrar puede avisar de
        una carpeta que no se pudo mover, y ese aviso ya vive alli.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        ventana = self.window()
        editar = getattr(ventana, "_editar_proyecto", None)
        if callable(editar):
            editar(proyecto)
            return

        # Respaldo si esta vista se usa fuera de la ventana principal.
        dialogo = DialogoProyecto(proyecto, parent=self)
        if dialogo.exec() == DialogoProyecto.DialogCode.Accepted:
            self.contexto.servicio_proyectos.guardar(proyecto, dialogo.datos())
            self.contexto.refrescar_proyecto_activo()
            self.contexto.notificar_cambio(self)

    # -- Barra lateral ------------------------------------------------------

    def _tarjeta_barra_lateral(self) -> Tarjeta:
        tarjeta = Tarjeta("Barra lateral")

        self._lista_secciones = QListWidget()
        self._lista_secciones.setObjectName("ListaSecciones")
        # `InternalMove` da el arrastre hecho. Reimplementarlo sobre los
        # QPushButton de la barra costaria cuatro manejadores de raton, un
        # indicador de insercion y perder las reglas del QSS.
        self._lista_secciones.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._lista_secciones.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._lista_secciones.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection
        )
        self._lista_secciones.setMaximumHeight(260)
        self._lista_secciones.model().rowsMoved.connect(self._guardar_disposicion)
        self._lista_secciones.itemChanged.connect(self._al_marcar_seccion)
        tarjeta.agregar(self._lista_secciones)

        pista = QLabel(
            "Arrastra para cambiar el orden y desmarca para ocultar. "
            "La aplicacion abre en la primera seccion de la lista."
        )
        pista.setObjectName("TextoTenue")
        pista.setWordWrap(True)
        tarjeta.agregar(pista)

        restablecer = QPushButton("Restablecer orden")
        restablecer.setCursor(Qt.CursorShape.PointingHandCursor)
        restablecer.clicked.connect(self._restablecer_disposicion)
        tarjeta.agregar(restablecer)
        return tarjeta

    def _cargar_secciones(self) -> None:
        """Vuelca el catalogo en la lista, en el orden vigente."""
        from mukuwareru.ui.vistas import SECCIONES

        catalogo = {seccion.clave: seccion for seccion in SECCIONES}
        disposicion = self.contexto.preferencias.disposicion_secciones(tuple(catalogo))

        # Sin bloquear, cada `setCheckState` disparia `itemChanged` y guardaria
        # la disposicion a medio construir.
        self._lista_secciones.blockSignals(True)
        self._lista_secciones.clear()
        for clave in disposicion.orden:
            seccion = catalogo[clave]
            elemento = QListWidgetItem(seccion.etiqueta)
            elemento.setIcon(iconos.icono(seccion.icono, tokens.TEXTO_SUAVE))
            elemento.setData(Qt.ItemDataRole.UserRole, clave)
            visible = clave not in disposicion.ocultas
            if clave == _IRRENUNCIABLE:
                elemento.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                )
                elemento.setToolTip("Ajustes no se puede ocultar.")
            else:
                elemento.setFlags(elemento.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                elemento.setCheckState(
                    Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
                )
            self._lista_secciones.addItem(elemento)
        self._lista_secciones.blockSignals(False)

    def _al_marcar_seccion(self, _elemento: QListWidgetItem) -> None:
        self._guardar_disposicion()

    def _guardar_disposicion(self, *_argumentos: object) -> None:
        """Guarda al soltar y al marcar, no con un boton.

        Esperar a un «Guardar» seria confuso: la barra lateral se reconstruye a
        la vista, y el cambio ya se ve hecho.
        """
        orden: list[str] = []
        ocultas: set[str] = set()
        for indice in range(self._lista_secciones.count()):
            elemento = self._lista_secciones.item(indice)
            clave = str(elemento.data(Qt.ItemDataRole.UserRole))
            orden.append(clave)
            if (
                clave != _IRRENUNCIABLE
                and elemento.checkState() is Qt.CheckState.Unchecked
            ):
                ocultas.add(clave)

        self.contexto.preferencias.guardar_disposicion_secciones(
            DisposicionSecciones(orden=tuple(orden), ocultas=frozenset(ocultas))
        )
        self.contexto.disposicion_cambiada.emit()

    def _restablecer_disposicion(self) -> None:
        self.contexto.preferencias.restablecer_disposicion_secciones()
        self._cargar_secciones()
        self.contexto.disposicion_cambiada.emit()

    # -- Atajos de teclado ---------------------------------------------------

    def _tarjeta_atajos(self) -> Tarjeta:
        """Manual de atajos, generado desde el catalogo que los declara.

        No es una lista escrita a mano: recorre `ui/atajos.py`, que es de donde
        salen las combinaciones que se enganchan de verdad. Cambiar una tecla
        cambia esta ayuda sola.
        """
        tarjeta = Tarjeta("Atajos de teclado")
        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(tokens.ESPACIO)
        rejilla.setVerticalSpacing(4)
        rejilla.setColumnMinimumWidth(0, _ANCHO_TECLA)

        fila = 0
        for ambito, lista in atajos.por_ambito():
            if not lista:
                continue
            if fila:
                # Un poco de aire entre grupos, sin una linea divisoria mas.
                rejilla.setRowMinimumHeight(fila, tokens.ESPACIO_PEQUENO)
                fila += 1

            cabecera = QLabel(ambito)
            cabecera.setStyleSheet("font-weight: 600;")
            rejilla.addWidget(cabecera, fila, 0, 1, 2)
            fila += 1

            for atajo in lista:
                tecla = QLabel(atajo.texto())
                tecla.setObjectName("Tecla")
                tecla.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rejilla.addWidget(tecla, fila, 0)

                que_hace = QLabel(atajo.descripcion)
                que_hace.setObjectName("TextoSuave")
                que_hace.setWordWrap(True)
                rejilla.addWidget(que_hace, fila, 1)
                fila += 1

        rejilla.setColumnStretch(1, 1)
        tarjeta.agregar(contenedor(rejilla))
        return tarjeta

    # -- Datos --------------------------------------------------------------

    def _tarjeta_datos(self) -> Tarjeta:
        """Informacion util para dar soporte, no configurable."""
        tarjeta = Tarjeta("Datos")
        for etiqueta, valor in (
            ("Base de datos", str(rutas.ruta_base_datos())),
            ("Biblioteca", str(rutas.carpeta_biblioteca())),
            ("Registros", str(rutas.carpeta_registros())),
        ):
            fila = QLabel(f"{etiqueta}: {valor}")
            fila.setObjectName("TextoTenue")
            fila.setWordWrap(True)
            fila.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            tarjeta.agregar(fila)

        aviso = QLabel(
            "Estas carpetas se conservan al actualizar la aplicacion. "
            "Las duraciones del Pomodoro se configuran en su propia vista."
        )
        aviso.setObjectName("TextoTenue")
        aviso.setWordWrap(True)
        tarjeta.agregar(aviso)
        return tarjeta

    # -- Recarga ------------------------------------------------------------

    def recargar(self) -> None:
        """Carga los datos del proyecto activo y la disposicion vigente."""
        self._cargar_secciones()

        proyecto = self.contexto.proyecto
        self._tarjeta_del_proyecto.setEnabled(proyecto is not None)
        self._tarjeta_del_plan.setEnabled(proyecto is not None)
        if proyecto is None:
            self._resumen.setText("Sin proyecto seleccionado.")
            self._resumen_plan.setText("")
            return

        self._cargar_plan(proyecto.id)

        objetivo = (
            proyecto.fecha_objetivo.strftime("%d/%m/%Y")
            if proyecto.fecha_objetivo
            else "sin fecha objetivo"
        )
        carpeta = proyecto.ruta_biblioteca or str(
            rutas.carpeta_biblioteca() / proyecto.nombre
        )
        self._resumen.setText(f"{proyecto.nombre} · {objetivo}\nPDFs en {carpeta}")

    def _cargar_plan(self, proyecto_id: int) -> None:
        """Vuelca el plan guardado sin disparar el guardado automatico."""
        plan = self.contexto.plan.cargar(proyecto_id)
        self._cargando_plan = True
        self._plan_activo.setChecked(plan.activo)
        for campo, minutos in zip(self._campos_plan, plan.minutos, strict=True):
            campo.setValue(minutos)
        self._cargando_plan = False
        self._pintar_resumen_plan(plan)
