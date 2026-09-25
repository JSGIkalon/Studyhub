"""Panel: pantalla principal del proyecto activo.

Muestra solo informacion util: seis cifras, el avance del temario y la
actividad reciente. Nada configurable, nada decorativo.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Documento
from mukuwareru.nucleo.servicios import CargaMateria, ResumenProgreso
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import (
    AnilloProgreso,
    BarraMateria,
    ListaResumen,
    Tarjeta,
    TarjetaMetrica,
    contenedor,
    vaciar,
)
from mukuwareru.utilidades import formato

_COLUMNAS_METRICAS = 3


class VistaPanel(VistaBase):
    """Tarjetas de metricas, progreso del temario y actividad reciente."""

    abrir_documento = Signal(object)  # Documento: «continuar leyendo»

    titulo = "Panel"
    ignora = frozenset({"anotaciones", "resultados"})

    def _construir(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        raiz.addWidget(desplazable)

        lienzo = QWidget()
        columna = QVBoxLayout(lienzo)
        columna.setContentsMargins(
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
            tokens.ESPACIO_GRANDE, tokens.ESPACIO_GRANDE,
        )
        columna.setSpacing(tokens.ESPACIO)
        desplazable.setWidget(lienzo)

        encabezado = QLabel(self.titulo)
        encabezado.setObjectName("TituloVista")
        columna.addWidget(encabezado)

        self._aviso_incumplimiento = self._construir_aviso_incumplimiento()
        columna.addWidget(self._aviso_incumplimiento)

        self._banda_plan = self._construir_banda_plan()
        columna.addWidget(self._banda_plan)

        columna.addLayout(self._construir_metricas())
        columna.addLayout(self._construir_progreso())

        self._tarjeta_repaso = self._construir_repaso()
        columna.addWidget(self._tarjeta_repaso)

        columna.addLayout(self._construir_actividad())
        columna.addStretch(1)

    # -- Plan y repaso -------------------------------------------------------

    def _construir_aviso_incumplimiento(self) -> QWidget:
        """Recordatorio del ultimo bloque planeado que no se cumplio."""
        tarjeta = Tarjeta("No cumpliste")
        self._texto_incumplimiento = QLabel()
        self._texto_incumplimiento.setWordWrap(True)
        tarjeta.agregar(self._texto_incumplimiento)
        tarjeta.setVisible(False)
        return tarjeta

    def _pintar_aviso_incumplimiento(self, proyecto_id: int, hoy: date) -> None:
        hallazgo = self.contexto.calendario.ultimo_incumplimiento(proyecto_id, hoy)
        if hallazgo is None:
            self._aviso_incumplimiento.setVisible(False)
            return

        fecha, bloque, cumplimiento = hallazgo
        cuando = "Ayer" if fecha == hoy - timedelta(days=1) else formato.fecha_corta(fecha)
        titulo = bloque.titulo or "el bloque planeado"
        self._texto_incumplimiento.setText(
            f"{cuando}, a las {bloque.hora_inicio}: «{titulo}». "
            f"Cumpliste el {cumplimiento.porcentaje} % ({formato.horas(cumplimiento.real_seg)} "
            f"de {formato.horas(cumplimiento.planeado_seg)} planeadas)."
        )
        self._aviso_incumplimiento.setVisible(True)

    def _construir_banda_plan(self) -> QWidget:
        """Ritmo necesario frente al real. Solo sale si hay plan y fecha."""
        tarjeta = Tarjeta("Ritmo")
        self._texto_plan = QLabel()
        self._texto_plan.setWordWrap(True)
        tarjeta.agregar(self._texto_plan)
        tarjeta.setVisible(False)
        return tarjeta

    def _construir_repaso(self) -> QWidget:
        """Sugerencias de repaso activo. Calculadas, sin cola ni estado."""
        tarjeta = Tarjeta("Conviene repasar")
        self._caja_repaso = QVBoxLayout()
        self._caja_repaso.setSpacing(2)
        tarjeta.contenido.addLayout(self._caja_repaso)
        tarjeta.setVisible(False)
        return tarjeta

    def _pintar_plan(
        self, proyecto_id: int, hoy: date, avance: ResumenProgreso, cargas: list[CargaMateria]
    ) -> None:
        plan = self.contexto.plan.cargar(proyecto_id)
        if not plan.activo:
            # Sin plan activo la banda no aparece: un plan que nadie pidio no
            # deberia ponerse a dar cuentas en la pantalla principal. Y no hace
            # falta calcular el diagnostico para no ensenarlo.
            self._banda_plan.setVisible(False)
            return
        diagnostico = self.contexto.plan.diagnostico(
            proyecto_id, hoy, conteo=(avance.total, avance.completados), cargas=cargas
        )
        if not diagnostico.hay_fecha:
            # Sin plan activo la banda no aparece: un plan que nadie pidio no
            # deberia ponerse a dar cuentas en la pantalla principal.
            self._banda_plan.setVisible(False)
            return

        estado = (
            "vas al dia"
            if diagnostico.al_dia
            else f"te faltan {diagnostico.desviacion_horas:.1f} h a la semana"
        )
        self._texto_plan.setText(
            f"{diagnostico.pendientes} modulos para «{diagnostico.titulo_hito}», "
            f"dentro de {diagnostico.dias_restantes} dias.\n"
            f"Necesitas {diagnostico.horas_por_semana_necesarias:.1f} h/semana "
            f"({diagnostico.modulos_por_semana:.1f} modulos); llevas "
            f"{diagnostico.horas_por_semana_reales:.1f} h/semana: {estado}.\n"
            f"Tu plan reserva {plan.horas_semana:.1f} h/semana."
        )
        self._banda_plan.setVisible(True)

    def _pintar_repaso(self, proyecto_id: int, hoy: date, cargas: list[CargaMateria]) -> None:
        vaciar(self._caja_repaso)

        sugerencias = self.contexto.plan.sugerencias(proyecto_id, hoy, cargas=cargas)
        if not sugerencias:
            self._tarjeta_repaso.setVisible(False)
            return

        for sugerencia in sugerencias:
            fila = QLabel(f"{sugerencia.titulo}\n{sugerencia.motivo}")
            fila.setObjectName("TextoSuave")
            fila.setWordWrap(True)
            self._caja_repaso.addWidget(fila)
        self._tarjeta_repaso.setVisible(True)

    def _construir_metricas(self) -> QGridLayout:
        rejilla = QGridLayout()
        rejilla.setSpacing(tokens.ESPACIO)

        self._metricas = {
            "hoy": TarjetaMetrica("Hoy", "reloj", tokens.ACENTO),
            "semana": TarjetaMetrica("Esta semana", "calendario", tokens.INFO),
            "total": TarjetaMetrica("Tiempo total", "estadisticas", tokens.TEXTO_SUAVE),
            "racha": TarjetaMetrica("Racha", "grafico", tokens.NARANJA),
            "pomodoros": TarjetaMetrica("Pomodoros hoy", "reloj", tokens.EXITO),
            "restantes": TarjetaMetrica("Dias restantes", "calendario", tokens.AVISO),
        }
        for indice, tarjeta in enumerate(self._metricas.values()):
            rejilla.addWidget(tarjeta, indice // _COLUMNAS_METRICAS, indice % _COLUMNAS_METRICAS)
        return rejilla

    def _construir_progreso(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO)

        general = Tarjeta("Progreso general")
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(tokens.ESPACIO_GRANDE)

        self._anillo = AnilloProgreso()
        cuerpo.addWidget(self._anillo, 0, Qt.AlignmentFlag.AlignTop)

        leyenda = QVBoxLayout()
        leyenda.setSpacing(tokens.ESPACIO_PEQUENO)
        self._leyenda = {
            "completados": _punto("Completados", tokens.EXITO),
            "pendientes": _punto("Pendientes", tokens.TEXTO_TENUE),
        }
        for widget in self._leyenda.values():
            leyenda.addWidget(widget)
        self._resumen_modulos = QLabel()
        self._resumen_modulos.setObjectName("TextoTenue")
        leyenda.addWidget(self._resumen_modulos)

        # Las dos cifras conviven: el conteo de modulos dice cuanto temario has
        # tocado, el ponderado cuanto del examen llevas. Solo sale si hay pesos.
        self._cifras = _Cifras()
        leyenda.addWidget(self._cifras)
        leyenda.addStretch(1)
        cuerpo.addLayout(leyenda, 1)

        general.agregar(contenedor(cuerpo))
        general.contenido.addStretch(1)
        fila.addWidget(general, 1)

        self._tarjeta_materias = Tarjeta("Modulos por tema")
        self._caja_materias = QVBoxLayout()
        self._caja_materias.setSpacing(2)
        self._tarjeta_materias.agregar(contenedor(self._caja_materias))
        self._tarjeta_materias.contenido.addStretch(1)
        fila.addWidget(self._tarjeta_materias, 1)
        return fila

    def _construir_actividad(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO)

        self._pdfs = ListaResumen(
            "Ultimos PDFs abiertos",
            "Aun no has abierto ningun PDF. Copia tus archivos a la carpeta "
            "de la biblioteca y apareceran solos.",
            pista="Continuar leyendo donde lo dejaste",
        )
        self._documentos_recientes: list[Documento] = []
        self._pdfs.elegido.connect(
            lambda i: self.abrir_documento.emit(self._documentos_recientes[i])
        )
        self._pdfs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        fila.addWidget(self._pdfs, 1)

        self._sesiones = ListaResumen(
            "Ultimas sesiones",
            "Todavia no hay sesiones registradas. Inicia un Pomodoro para empezar.",
        )
        self._sesiones.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        fila.addWidget(self._sesiones, 1)
        return fila

    # -- Datos --------------------------------------------------------------

    def recargar(self) -> None:
        """Vuelca en los widgets las cifras del proyecto activo."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            self._vaciar()
            return

        hoy = date.today()
        estudio = self.contexto.estadisticas.resumen(proyecto.id, hoy)
        avance = self.contexto.progreso.resumen(proyecto.id)
        # La carga la necesitan el ritmo y el repaso: se calcula una vez.
        cargas = self.contexto.carga.resumen(proyecto.id)
        self._pintar_plan(proyecto.id, hoy, avance, cargas)
        self._pintar_repaso(proyecto.id, hoy, cargas)
        self._pintar_aviso_incumplimiento(proyecto.id, hoy)

        self._metricas["hoy"].establecer(
            formato.horas(estudio.segundos_hoy), "Tiempo estudiado"
        )
        self._metricas["semana"].establecer(
            formato.horas(estudio.segundos_semana), "Desde el lunes"
        )
        self._metricas["total"].establecer(
            formato.horas(estudio.segundos_total), "Historico del proyecto"
        )
        self._metricas["racha"].establecer(
            f"{estudio.racha}", "Dias seguidos" if estudio.racha != 1 else "Dia seguido"
        )
        self._metricas["pomodoros"].establecer(
            f"{estudio.pomodoros_hoy}", "Sesiones completadas"
        )
        self._establecer_cuenta_atras(proyecto.dias_restantes(hoy))

        self._anillo.establecer(avance.porcentaje)
        self._leyenda["completados"].establecer(avance.completados)
        self._leyenda["pendientes"].establecer(avance.pendientes)
        self._resumen_modulos.setText(
            f"{avance.completados} / {avance.total} modulos completados"
            if avance.total
            else "Sin temario cargado"
        )
        self._cifras.establecer(avance)
        self._pintar_materias(avance)

        self._documentos_recientes = self.contexto.documentos.recientes(proyecto.id)
        self._pdfs.establecer(
            [
                (d.nombre, formato.apertura(d.abierto_en).capitalize())
                for d in self._documentos_recientes
            ]
        )
        self._sesiones.establecer(
            [
                (formato.fecha_corta(s.inicio.date()), formato.horas(s.duracion_seg))
                for s in self.contexto.sesiones.recientes(proyecto.id)
            ]
        )

    def _establecer_cuenta_atras(self, restantes: int | None) -> None:
        tarjeta = self._metricas["restantes"]
        if restantes is None:
            tarjeta.establecer("—", "Sin fecha objetivo")
        elif restantes > 0:
            tarjeta.establecer(
                f"{restantes}",
                "Hasta la fecha objetivo",
                tokens.ACENTO if restantes <= 30 else None,
            )
        elif restantes == 0:
            tarjeta.establecer("Hoy", "Es el dia", tokens.ACENTO)
        else:
            tarjeta.establecer("—", "Fecha objetivo superada")

    def _pintar_materias(self, avance: ResumenProgreso | None) -> None:
        vaciar(self._caja_materias)

        materias = avance.materias if avance is not None else ()
        if not materias or avance is None:
            aviso = QLabel(
                "Sin materias todavia. Se crearan al importar tu Excel o al "
                "anadirlas desde Progreso."
            )
            aviso.setObjectName("TextoTenue")
            aviso.setWordWrap(True)
            self._caja_materias.addWidget(aviso)
            return

        for indice, materia in enumerate(materias):
            self._caja_materias.addWidget(
                BarraMateria(
                    materia.nombre,
                    materia.completados,
                    materia.total,
                    tokens.color_o_serie(materia.color, indice),
                    cuota=avance.cuota(materia) if avance.hay_pesos else None,
                )
            )

    def _vaciar(self) -> None:
        for tarjeta in self._metricas.values():
            tarjeta.establecer("—", "Sin proyecto")
        self._anillo.establecer(0)
        for punto in self._leyenda.values():
            punto.establecer(0)
        self._resumen_modulos.setText("")
        self._cifras.establecer(None)
        self._pintar_materias(None)
        self._pdfs.establecer([])
        self._sesiones.establecer([])
        self._banda_plan.setVisible(False)
        self._tarjeta_repaso.setVisible(False)
        self._aviso_incumplimiento.setVisible(False)


class _Cifras(QWidget):
    """«Modulos X %» y «Ponderado Y %», una debajo de otra.

    Las dos con el mismo rango tipografico: ninguna de las dos es «la buena».
    La fila del ponderado se oculta entera mientras el proyecto no tenga pesos,
    para no ensenar dos veces el mismo numero.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Transparente")
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, tokens.ESPACIO_PEQUENO, 0, 0)
        caja.setSpacing(2)

        self._modulos = QLabel()
        self._modulos.setObjectName("TextoSuave")
        caja.addWidget(self._modulos)

        self._ponderado = QLabel()
        self._ponderado.setObjectName("TextoSuave")
        caja.addWidget(self._ponderado)

    def establecer(self, avance: ResumenProgreso | None) -> None:
        """Vuelca las dos cifras del resumen, o las vacia si no hay proyecto."""
        if avance is None or not avance.total:
            self._modulos.setText("")
            self._ponderado.setVisible(False)
            return

        self._modulos.setText(f"Modulos      {avance.porcentaje} %")
        self._ponderado.setText(f"Ponderado    {avance.porcentaje_ponderado} %")
        self._ponderado.setVisible(avance.hay_pesos)
        self._ponderado.setToolTip(
            "Media de cada asignatura pesada por lo que vale en el proyecto."
        )


class _Punto(QWidget):
    """Entrada de leyenda: circulo de color, etiqueta y cifra."""

    def __init__(self, texto: str, color: str) -> None:
        super().__init__()
        self.setObjectName("Transparente")
        caja = QHBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(tokens.ESPACIO_PEQUENO)

        marca = QLabel("●")
        marca.setStyleSheet(f"color: {color};")
        caja.addWidget(marca)

        etiqueta = QLabel(texto)
        etiqueta.setObjectName("TextoSuave")
        caja.addWidget(etiqueta)
        caja.addStretch(1)

        self._valor = QLabel("0")
        self._valor.setProperty("fuerte", True)
        caja.addWidget(self._valor)

    def establecer(self, valor: int) -> None:
        """Actualiza la cifra de la entrada."""
        self._valor.setText(str(valor))


def _punto(texto: str, color: str) -> _Punto:
    return _Punto(texto, color)

