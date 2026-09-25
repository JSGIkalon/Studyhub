"""Calendario: lo estudiado, lo planeado y la distancia entre las dos cosas.

La rejilla del mes se pinta con **una sola** llamada a ``ServicioCalendario.mes``
—tres consultas de rango y el reparto en memoria—, nunca con una consulta por
celda.

Las sesiones aparecen solas: son una proyeccion de la tabla ``sesion``, no algo
que haya que apuntar aqui. Lo unico que se crea en esta vista es lo que todavia
no ha pasado: hitos y bloques de estudio.
"""

from __future__ import annotations

from calendar import Calendar
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import BloquePlan, Hito
from mukuwareru.nucleo.servicios import DiaCalendario
from mukuwareru.ui.dialogos.planificar import DialogoBloque, DialogoHito
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import Tarjeta, contenedor, vaciar
from mukuwareru.utilidades import formato

_DIAS = ("Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom")
_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

# Por encima de estas horas en un dia la celda va a plena intensidad. Cuatro
# horas de estudio es un dia bueno; escalar hasta el maximo historico haria que
# un dia excepcional apagase todos los demas.
_HORAS_PLENAS = 4.0

# Cuanto tinte lleva la celda de un dia con plan ya juzgado. Suficiente para
# leer el verde o el rojo de un vistazo sin tapar el texto de la celda.
_TINTE_VEREDICTO = 0.45


class VistaCalendario(VistaBase):
    """Rejilla del mes, detalle del dia y planificacion."""

    titulo = "Calendario"
    dominio = "calendario"
    ignora = frozenset({"anotaciones", "documentos", "notas"})

    # -- Construccion -------------------------------------------------------

    def _construir(self) -> None:
        hoy = date.today()
        self._mes = date(hoy.year, hoy.month, 1)
        self._elegido = hoy
        self._dias: dict[str, DiaCalendario] = {}
        self._celdas: dict[str, _Celda] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE, tokens.ESPACIO
        )
        raiz.setSpacing(tokens.ESPACIO_PEQUENO)
        raiz.addLayout(self._cabecera())

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(tokens.ESPACIO)
        cuerpo.addWidget(self._panel_mes(), 3)
        cuerpo.addWidget(self._panel_dia(), 2)
        raiz.addLayout(cuerpo, 1)

    def _cabecera(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        fila.addWidget(titulo)

        self._etiqueta_mes = QLabel()
        self._etiqueta_mes.setProperty("fuerte", True)
        fila.addSpacing(tokens.ESPACIO)
        fila.addWidget(self._etiqueta_mes)

        anterior = QPushButton("<")
        anterior.setFixedWidth(32)
        anterior.setCursor(Qt.CursorShape.PointingHandCursor)
        anterior.clicked.connect(lambda: self._cambiar_mes(-1))
        fila.addWidget(anterior)

        siguiente = QPushButton(">")
        siguiente.setFixedWidth(32)
        siguiente.setCursor(Qt.CursorShape.PointingHandCursor)
        siguiente.clicked.connect(lambda: self._cambiar_mes(1))
        fila.addWidget(siguiente)

        hoy = QPushButton("Hoy")
        hoy.setCursor(Qt.CursorShape.PointingHandCursor)
        hoy.clicked.connect(self._ir_a_hoy)
        fila.addWidget(hoy)

        fila.addStretch(1)

        self._adherencia = QLabel()
        self._adherencia.setObjectName("TextoSuave")
        fila.addWidget(self._adherencia)
        return fila

    def _panel_mes(self) -> QWidget:
        columna = QVBoxLayout()
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        encabezados = QHBoxLayout()
        encabezados.setSpacing(4)
        for nombre in _DIAS:
            etiqueta = QLabel(nombre)
            etiqueta.setObjectName("TextoTenue")
            etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
            encabezados.addWidget(etiqueta, 1)
        columna.addLayout(encabezados)

        self._rejilla = QGridLayout()
        self._rejilla.setSpacing(4)
        columna.addLayout(self._rejilla, 1)

        leyenda = QLabel(
            "Los dias con plan van en verde si se alcanzo el tiempo previsto y "
            "en rojo si no. Sin plan, el tono mide las horas estudiadas; la "
            "estrella marca una fecha clave."
        )
        leyenda.setObjectName("TextoTenue")
        leyenda.setWordWrap(True)
        columna.addWidget(leyenda)
        return contenedor(columna)

    def _panel_dia(self) -> QWidget:
        columna = QVBoxLayout()
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(tokens.ESPACIO_PEQUENO)

        fila = QHBoxLayout()
        self._titulo_dia = QLabel()
        self._titulo_dia.setProperty("fuerte", True)
        fila.addWidget(self._titulo_dia)
        fila.addStretch(1)

        planificar = QPushButton("Planificar…")
        planificar.setObjectName("BotonPrimario")
        planificar.setCursor(Qt.CursorShape.PointingHandCursor)
        planificar.clicked.connect(self._nuevo_bloque)
        fila.addWidget(planificar)

        fecha_clave = QPushButton("Fecha clave…")
        fecha_clave.setCursor(Qt.CursorShape.PointingHandCursor)
        fecha_clave.clicked.connect(self._nuevo_hito)
        fila.addWidget(fecha_clave)
        columna.addLayout(fila)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lienzo = QWidget()
        self._caja_dia = QVBoxLayout(lienzo)
        self._caja_dia.setContentsMargins(0, 0, 0, 0)
        self._caja_dia.setSpacing(tokens.ESPACIO_PEQUENO)
        self._caja_dia.addStretch(1)
        desplazable.setWidget(lienzo)
        columna.addWidget(desplazable, 1)
        return contenedor(columna)

    # -- Recarga ------------------------------------------------------------

    def recargar(self) -> None:
        """Vuelve a componer el mes visible y el detalle del dia elegido."""
        self._etiqueta_mes.setText(f"{_MESES[self._mes.month - 1]} de {self._mes.year}")
        proyecto = self.contexto.proyecto

        if proyecto is None:
            self._dias = {}
            self._pintar_mes()
            self._adherencia.setText("Sin proyecto seleccionado.")
            self._pintar_dia()
            return

        dias = self.contexto.calendario.mes(proyecto.id, self._mes.year, self._mes.month)
        self._dias = {dia.fecha.isoformat(): dia for dia in dias}
        self._pintar_mes()
        self._pintar_adherencia(dias)
        self._pintar_dia()

    def _pintar_adherencia(self, dias: list[DiaCalendario]) -> None:
        planeados = sum(len(dia.bloques) for dia in dias)
        estudiado = sum(dia.segundos_estudiados for dia in dias)
        if not planeados:
            self._adherencia.setText(f"{formato.horas(estudiado)} este mes")
            return
        cumplidos = sum(dia.bloques_cumplidos for dia in dias)
        self._adherencia.setText(
            f"{formato.horas(estudiado)} este mes  ·  "
            f"{cumplidos} de {planeados} bloques cumplidos"
        )

    def _pintar_mes(self) -> None:
        vaciar(self._rejilla)
        self._celdas.clear()

        hoy = date.today()
        # `Calendar(0)` empieza en lunes, coherente con el `weekday()` que ya usa
        # el servicio de estadisticas para la semana.
        semanas = Calendar(0).monthdatescalendar(self._mes.year, self._mes.month)
        for numero, semana in enumerate(semanas):
            for columna, fecha in enumerate(semana):
                dia = self._dias.get(fecha.isoformat())
                celda = _Celda(
                    fecha,
                    dia,
                    del_mes=fecha.month == self._mes.month,
                    es_hoy=fecha == hoy,
                )
                celda.elegido.connect(self._elegir_dia)
                celda.planificar.connect(self._planificar_en)
                self._rejilla.addWidget(celda, numero, columna)
                self._celdas[fecha.isoformat()] = celda
        self._marcar_elegido()

    def _marcar_elegido(self) -> None:
        for clave, celda in self._celdas.items():
            celda.marcar(clave == self._elegido.isoformat())

    def _pintar_dia(self) -> None:
        vaciar(self._caja_dia, conservar=1)

        self._titulo_dia.setText(formato.fecha_larga(self._elegido))
        dia = self._dias.get(self._elegido.isoformat())
        if dia is None or dia.vacio:
            vacio = QLabel(
                "Nada este dia.\n\nPlanifica un bloque de estudio o marca una "
                "fecha clave con los botones de arriba."
            )
            vacio.setObjectName("TextoTenue")
            vacio.setWordWrap(True)
            self._caja_dia.insertWidget(0, vacio)
            return

        indice = 0
        for hito in dia.hitos:
            tarjeta = _TarjetaHito(hito)
            tarjeta.editar.connect(self._editar_hito)
            tarjeta.eliminar.connect(self._eliminar_hito)
            tarjeta.completar.connect(self._completar_hito)
            self._caja_dia.insertWidget(indice, tarjeta)
            indice += 1

        for bloque in dia.bloques:
            tarjeta = _TarjetaBloque(
                bloque, dia.cumplimientos.get(bloque.id), self._nombres_materias()
            )
            tarjeta.editar.connect(self._editar_bloque)
            tarjeta.eliminar.connect(self._eliminar_bloque)
            self._caja_dia.insertWidget(indice, tarjeta)
            indice += 1

        if dia.segundos_estudiados:
            real = Tarjeta("Estudiado de verdad")
            resumen = QLabel(
                f"{formato.horas(dia.segundos_estudiados)} en "
                f"{len(dia.sesiones)} sesiones  ·  {dia.pomodoros} pomodoros"
            )
            resumen.setObjectName("TextoSuave")
            real.agregar(resumen)
            for sesion in dia.sesiones:
                fila = QLabel(
                    f"{sesion.inicio:%H:%M}  ·  {formato.horas(sesion.duracion_seg)}"
                    + ("" if sesion.completada else "  (interrumpida)")
                )
                fila.setObjectName("TextoTenue")
                real.agregar(fila)
            self._caja_dia.insertWidget(indice, real)

    def _nombres_materias(self) -> dict[int, str]:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return {}
        return {m.id: m.nombre for m in self.contexto.materias.listar(proyecto.id)}

    # -- Navegacion ---------------------------------------------------------

    def _cambiar_mes(self, desplazamiento: int) -> None:
        mes = self._mes.month + desplazamiento
        ano = self._mes.year + (mes - 1) // 12
        self._mes = date(ano, (mes - 1) % 12 + 1, 1)
        self.recargar()

    def _ir_a_hoy(self) -> None:
        hoy = date.today()
        self._mes = date(hoy.year, hoy.month, 1)
        self._elegido = hoy
        self.recargar()

    def _elegir_dia(self, fecha: object) -> None:
        if not isinstance(fecha, date):
            return
        self._elegido = fecha
        if fecha.month != self._mes.month or fecha.year != self._mes.year:
            self._mes = date(fecha.year, fecha.month, 1)
            self.recargar()
            return
        self._marcar_elegido()
        self._pintar_dia()

    def _planificar_en(self, fecha: object) -> None:
        """Doble clic en una celda: planificar directamente ese dia."""
        if isinstance(fecha, date):
            self._elegir_dia(fecha)
            self._nuevo_bloque()

    # -- Escritura ----------------------------------------------------------

    def _nuevo_bloque(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        dialogo = DialogoBloque(
            self._elegido, self.contexto.materias.listar(proyecto.id), parent=self
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dialogo.datos()
        self.contexto.bloques.crear(
            proyecto.id,
            datos.fecha,
            duracion_min=datos.duracion_min,
            hora_inicio=datos.hora_inicio,
            titulo=datos.titulo,
            materias=datos.materias,
        )
        self._tras_escribir(datos.fecha)

    def _editar_bloque(self, bloque: object) -> None:
        proyecto = self.contexto.proyecto
        if not isinstance(bloque, BloquePlan) or proyecto is None:
            return
        dialogo = DialogoBloque(
            bloque.fecha, self.contexto.materias.listar(proyecto.id), bloque, parent=self
        )
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dialogo.datos()
        bloque.fecha = datos.fecha
        bloque.hora_inicio = datos.hora_inicio
        bloque.duracion_min = datos.duracion_min
        bloque.titulo = datos.titulo
        self.contexto.bloques.actualizar(bloque)
        self.contexto.bloques.etiquetar(bloque.id, datos.materias)
        self._tras_escribir(datos.fecha)

    def _eliminar_bloque(self, bloque: object) -> None:
        if not isinstance(bloque, BloquePlan):
            return
        self.contexto.bloques.eliminar(bloque.id)
        self._tras_escribir(bloque.fecha)

    def _nuevo_hito(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        dialogo = DialogoHito(self._elegido, parent=self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dialogo.datos()
        self.contexto.hitos.crear(
            proyecto.id,
            datos.titulo,
            datos.fecha,
            tipo=datos.tipo,
            hora=datos.hora,
            nota=datos.nota,
        )
        self._tras_escribir(datos.fecha)

    def _editar_hito(self, hito: object) -> None:
        if not isinstance(hito, Hito):
            return
        dialogo = DialogoHito(hito.fecha, hito, parent=self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dialogo.datos()
        hito.titulo = datos.titulo
        hito.fecha = datos.fecha
        hito.tipo = datos.tipo
        hito.hora = datos.hora
        hito.nota = datos.nota
        self.contexto.hitos.actualizar(hito)

        # El hito principal espeja `proyecto.fecha_objetivo`: si se mueve desde
        # aqui, la columna tiene que seguirle o la barra lateral mentiria.
        proyecto = self.contexto.proyecto
        if hito.principal and proyecto is not None:
            proyecto.fecha_objetivo = datos.fecha
            self.contexto.proyectos.actualizar(proyecto)
            self.contexto.refrescar_proyecto_activo()
        self._tras_escribir(datos.fecha)

    def _eliminar_hito(self, hito: object) -> None:
        if not isinstance(hito, Hito):
            return
        respuesta = QMessageBox.question(
            self,
            "Eliminar fecha",
            f"¿Eliminar «{hito.titulo}»?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return

        self.contexto.hitos.eliminar(hito.id)
        proyecto = self.contexto.proyecto
        if hito.principal and proyecto is not None:
            proyecto.fecha_objetivo = None
            self.contexto.proyectos.actualizar(proyecto)
            self.contexto.refrescar_proyecto_activo()
        self._tras_escribir(hito.fecha)

    def _completar_hito(self, hito: object) -> None:
        if not isinstance(hito, Hito):
            return
        self.contexto.hitos.marcar_completado(hito.id, not hito.completado)
        self._tras_escribir(hito.fecha)

    def _tras_escribir(self, fecha: date) -> None:
        """Recarga la vista y avisa al resto: la cuenta atras puede haber cambiado."""
        if fecha.month != self._mes.month or fecha.year != self._mes.year:
            self._mes = date(fecha.year, fecha.month, 1)
        self._elegido = fecha
        self.recargar()
        self.contexto.notificar_cambio(self)


class _Celda(QFrame):
    """Un dia de la rejilla del mes."""

    elegido = Signal(object)      # date
    planificar = Signal(object)   # date

    def __init__(
        self,
        fecha: date,
        dia: DiaCalendario | None,
        *,
        del_mes: bool,
        es_hoy: bool,
    ) -> None:
        super().__init__()
        self.fecha = fecha
        self._dia = dia
        self._del_mes = del_mes
        self._es_hoy = es_hoy
        self._elegida = False

        self.setMinimumHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda: self.planificar.emit(self.fecha)
        )
        self._construir()
        self._aplicar_estilo()

    def _construir(self) -> None:
        caja = QVBoxLayout(self)
        caja.setContentsMargins(6, 4, 6, 4)
        caja.setSpacing(1)

        cabecera = QHBoxLayout()
        cabecera.setSpacing(2)
        numero = QLabel(str(self.fecha.day))
        if self._es_hoy:
            numero.setStyleSheet("font-weight: 700;")
        elif not self._del_mes:
            numero.setObjectName("TextoTenue")
        cabecera.addWidget(numero)
        cabecera.addStretch(1)

        if self._dia and self._dia.hitos:
            estrella = QLabel("★")
            estrella.setStyleSheet(f"color: {tokens.AVISO};")
            estrella.setToolTip("\n".join(h.titulo for h in self._dia.hitos))
            cabecera.addWidget(estrella)
        caja.addLayout(cabecera)

        if self._dia and self._dia.segundos_estudiados:
            horas = QLabel(formato.horas(self._dia.segundos_estudiados))
            horas.setStyleSheet(
                f"color: {tokens.EXITO}; font-size: {tokens.TAM_PEQUENO}px;"
            )
            caja.addWidget(horas)

        if self._dia and self._dia.bloques:
            plan = QLabel(f"plan {self._dia.minutos_planeados} min")
            plan.setObjectName("TextoTenue")
            plan.setStyleSheet(f"font-size: {tokens.TAM_PEQUENO}px;")
            # El tono de la celda sale de estas dos cifras, no del recuento de
            # bloques: el tooltip tiene que ensenar lo mismo que se pinta.
            plan.setToolTip(
                f"{formato.horas(self._dia.segundos_estudiados)} de "
                f"{formato.horas(self._dia.minutos_planeados * 60)} previstos"
                f"  ·  {self._dia.bloques_cumplidos} de "
                f"{len(self._dia.bloques)} bloques cumplidos"
            )
            caja.addWidget(plan)
        caja.addStretch(1)

    def _aplicar_estilo(self) -> None:
        segundos = self._dia.segundos_estudiados if self._dia else 0
        veredicto = self._veredicto()

        if not self._del_mes:
            fondo = tokens.FONDO
        elif veredicto is not None:
            # Con plan, el dia se juzga: verde si el tiempo estudiado alcanza o
            # supera lo planeado, rojo si se queda corto. Un tono fijo, no el
            # degradado: aqui lo que importa es el si o el no.
            fondo = _mezclar(tokens.SUPERFICIE, veredicto, _TINTE_VEREDICTO)
        else:
            intensidad = min(1.0, segundos / (_HORAS_PLENAS * 3600))
            fondo = _mezclar(tokens.SUPERFICIE, tokens.EXITO, intensidad * 0.55)

        if self._elegida:
            borde = f"2px solid {tokens.ACENTO}"
        elif self._es_hoy:
            borde = f"2px solid {tokens.TEXTO_SUAVE}"
        elif veredicto is not None:
            borde = f"1px dashed {veredicto}"
        elif self._dia and self._dia.bloques:
            borde = f"1px dashed {tokens.INFO}"
        else:
            borde = f"1px solid {tokens.BORDE_SUTIL}"

        self.setStyleSheet(
            f"QFrame {{ background-color: {fondo}; border: {borde};"
            f" border-radius: {tokens.RADIO_PEQUENO}px; }}"
        )

    def _veredicto(self) -> str | None:
        """Verde si el dia alcanzo su plan, rojo si no. ``None`` si no se juzga.

        Solo se juzgan los dias con plan. Un dia futuro que aun no ha alcanzado
        su plan no se pinta de rojo —todavia le queda tiempo—, pero si ya lo
        supero se lleva el verde desde ese momento.
        """
        if self._dia is None or not self._dia.bloques:
            return None
        planeados = self._dia.minutos_planeados * 60
        if not planeados:
            return None
        if self._dia.segundos_estudiados >= planeados:
            return tokens.EXITO
        return tokens.ACENTO if self.fecha <= date.today() else None

    def marcar(self, elegida: bool) -> None:
        """Resalta la celda como la elegida."""
        if elegida == self._elegida:
            return
        self._elegida = elegida
        self._aplicar_estilo()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        self.elegido.emit(self.fecha)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        self.planificar.emit(self.fecha)
        super().mouseDoubleClickEvent(event)


class _TarjetaHito(Tarjeta):
    """Una fecha clave del dia elegido."""

    editar = Signal(object)
    eliminar = Signal(object)
    completar = Signal(object)

    def __init__(self, hito: Hito) -> None:
        super().__init__()
        self.hito = hito
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        insignia = QLabel(f"★ {hito.tipo.etiqueta}")
        insignia.setStyleSheet(f"color: {tokens.AVISO}; font-weight: 600;")
        fila.addWidget(insignia)

        titulo = QLabel(hito.titulo + ("  ·  hecho" if hito.completado else ""))
        titulo.setWordWrap(True)
        if hito.completado:
            titulo.setObjectName("TextoTenue")
        fila.addWidget(titulo, 1)

        if hito.hora:
            hora = QLabel(hito.hora)
            hora.setObjectName("TextoTenue")
            fila.addWidget(hora)
        self.contenido.addWidget(contenedor(fila))

        if hito.nota:
            nota = QLabel(hito.nota)
            nota.setObjectName("TextoSuave")
            nota.setWordWrap(True)
            self.contenido.addWidget(nota)

        if hito.principal:
            aviso = QLabel("Es la fecha objetivo del proyecto.")
            aviso.setObjectName("TextoTenue")
            self.contenido.addWidget(aviso)

    def _menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Editar…", lambda: self.editar.emit(self.hito))
        menu.addAction(
            "Marcar pendiente" if self.hito.completado else "Marcar cumplida",
            lambda: self.completar.emit(self.hito),
        )
        menu.addSeparator()
        menu.addAction("Eliminar", lambda: self.eliminar.emit(self.hito))
        menu.exec(self.cursor().pos())


class _TarjetaBloque(Tarjeta):
    """Un bloque planeado, con lo que de verdad se estudio en su franja."""

    editar = Signal(object)
    eliminar = Signal(object)

    def __init__(
        self, bloque: BloquePlan, cumplimiento: object, materias: dict[int, str]
    ) -> None:
        super().__init__()
        self.bloque = bloque
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

        franja = bloque.hora_inicio or "sin hora"
        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        cuando = QLabel(f"{franja}  ·  {bloque.duracion_min} min")
        cuando.setProperty("fuerte", True)
        fila.addWidget(cuando)
        fila.addWidget(QLabel(bloque.titulo), 1)

        porcentaje = getattr(cumplimiento, "porcentaje", 0)
        cumplido = getattr(cumplimiento, "cumplido", False)
        marca = QLabel(f"{porcentaje} %")
        marca.setStyleSheet(
            f"color: {tokens.EXITO if cumplido else tokens.TEXTO_TENUE};"
            " font-weight: 600;"
        )
        # Se ensena el porcentaje y no un aprobado/suspenso: cuando dos bloques
        # comparten el dia hay que poder ver de donde sale el reparto.
        marca.setToolTip(
            f"{formato.horas(getattr(cumplimiento, 'real_seg', 0))} de "
            f"{formato.horas(bloque.duracion_seg)} previstos"
        )
        fila.addWidget(marca)
        self.contenido.addWidget(contenedor(fila))

        if bloque.materias:
            nombres = ", ".join(
                materias.get(i, "?") for i in bloque.materias
            )
            etiqueta = QLabel(nombres)
            etiqueta.setObjectName("TextoTenue")
            etiqueta.setWordWrap(True)
            self.contenido.addWidget(etiqueta)

    def _menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Editar…", lambda: self.editar.emit(self.bloque))
        menu.addSeparator()
        menu.addAction("Eliminar", lambda: self.eliminar.emit(self.bloque))
        menu.exec(self.cursor().pos())


def _mezclar(fondo: str, tinte: str, proporcion: float) -> str:
    """Mezcla dos colores ``#RRGGBB``. Es el degradado del mapa de calor."""
    proporcion = max(0.0, min(1.0, proporcion))
    base = tuple(int(fondo[i : i + 2], 16) for i in (1, 3, 5))
    encima = tuple(int(tinte[i : i + 2], 16) for i in (1, 3, 5))
    mezcla = tuple(
        round(b + (e - b) * proporcion) for b, e in zip(base, encima, strict=True)
    )
    return "#{:02X}{:02X}{:02X}".format(*mezcla)
