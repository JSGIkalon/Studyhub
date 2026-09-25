"""Estadisticas: en que se ha ido el tiempo de estudio.

Graficos simples con QtCharts. Nada interactivo: se miran, se entienden y se
vuelve a estudiar.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.servicios import ResumenProgreso
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import (
    BarraAtencion,
    BarraMateria,
    GraficoBarras,
    Tarjeta,
    TarjetaMetrica,
    contenedor,
    vaciar,
)
from mukuwareru.utilidades import formato

_DIAS_GRAFICO = 30
_SEMANAS = 12
_MESES = 12
_COLUMNAS_METRICAS = 4


class VistaEstadisticas(VistaBase):
    """Horas por dia, semana y mes, mas los totales del proyecto."""

    titulo = "Estadisticas"
    ignora = frozenset({"anotaciones", "documentos", "notas", "resultados"})

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

        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        columna.addWidget(titulo)

        rejilla = QGridLayout()
        rejilla.setSpacing(tokens.ESPACIO)
        self._metricas = {
            "total": TarjetaMetrica("Tiempo total", "estadisticas", tokens.TEXTO_SUAVE),
            "pomodoros": TarjetaMetrica("Pomodoros", "reloj", tokens.EXITO),
            "racha": TarjetaMetrica("Racha", "grafico", tokens.NARANJA),
            "media": TarjetaMetrica("Media diaria", "calendario", tokens.INFO),
            "dias_incumplidos": TarjetaMetrica(
                "Dias incumplidos", "calendario", tokens.AVISO
            ),
            "horas_incumplidas": TarjetaMetrica(
                "Horas incumplidas", "reloj", tokens.AVISO
            ),
        }
        for indice, tarjeta in enumerate(self._metricas.values()):
            rejilla.addWidget(tarjeta, indice // _COLUMNAS_METRICAS, indice % _COLUMNAS_METRICAS)
        columna.addLayout(rejilla)

        self._grafico_dias = GraficoBarras(
            f"Horas por dia (ultimos {_DIAS_GRAFICO})", tokens.ACENTO
        )
        columna.addWidget(self._grafico_dias)

        fila = QHBoxLayout()
        fila.setSpacing(tokens.ESPACIO)
        self._grafico_semanas = GraficoBarras(f"Horas por semana ({_SEMANAS})", tokens.INFO)
        self._grafico_meses = GraficoBarras(f"Horas por mes ({_MESES})", tokens.EXITO)
        fila.addWidget(self._grafico_semanas, 1)
        fila.addWidget(self._grafico_meses, 1)
        columna.addLayout(fila)

        inferior = QHBoxLayout()
        inferior.setSpacing(tokens.ESPACIO)

        self._tarjeta_materias = Tarjeta("Tiempo por materia")
        self._caja_materias = QVBoxLayout()
        self._caja_materias.setSpacing(2)
        self._tarjeta_materias.agregar(contenedor(self._caja_materias))
        self._tarjeta_materias.contenido.addStretch(1)
        inferior.addWidget(self._tarjeta_materias, 1)

        self._tarjeta_proyectos = Tarjeta("Tiempo por proyecto")
        self._caja_proyectos = QVBoxLayout()
        self._caja_proyectos.setSpacing(2)
        self._tarjeta_proyectos.agregar(contenedor(self._caja_proyectos))
        self._tarjeta_proyectos.contenido.addStretch(1)
        inferior.addWidget(self._tarjeta_proyectos, 1)
        columna.addLayout(inferior)

        self._tarjeta_atencion = Tarjeta("Atencion por materia")
        self._caja_atencion = QVBoxLayout()
        self._caja_atencion.setSpacing(2)
        self._tarjeta_atencion.agregar(contenedor(self._caja_atencion))
        self._tarjeta_atencion.setVisible(False)
        columna.addWidget(self._tarjeta_atencion)

        columna.addStretch(1)

    # -- Datos --------------------------------------------------------------

    def recargar(self) -> None:
        """Recalcula todas las cifras y graficos del proyecto activo."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            for tarjeta in self._metricas.values():
                tarjeta.establecer("—", "Sin proyecto")
            for grafico in (self._grafico_dias, self._grafico_semanas, self._grafico_meses):
                grafico.establecer([])
            _vaciar(self._caja_materias, "Sin proyecto seleccionado.")
            _vaciar(self._caja_proyectos, "")
            vaciar(self._caja_atencion)
            self._tarjeta_atencion.setVisible(False)
            return

        hoy = date.today()
        estudio = self.contexto.estadisticas.resumen(proyecto.id, hoy)
        por_dia = self.contexto.estadisticas.por_dia(proyecto.id, _DIAS_GRAFICO, hoy)

        activos = [s for _, s in por_dia if s > 0]
        self._metricas["total"].establecer(
            formato.horas(estudio.segundos_total), "Historico del proyecto"
        )
        self._metricas["pomodoros"].establecer(
            str(self.contexto.sesiones.contar_pomodoros(proyecto.id)), "Sesiones completadas"
        )
        self._metricas["racha"].establecer(
            str(estudio.racha), "Dias seguidos" if estudio.racha != 1 else "Dia seguido"
        )
        self._metricas["media"].establecer(
            formato.horas(round(sum(activos) / len(activos)) if activos else 0),
            f"En los {len(activos)} dias con estudio",
        )
        self._pintar_cumplimiento(proyecto.id, hoy)

        self._grafico_dias.establecer(
            [(f"{dia.day}", segundos / 3600) for dia, segundos in por_dia]
        )
        self._grafico_semanas.establecer(self._por_semana(proyecto.id, hoy))
        self._grafico_meses.establecer(self._por_mes(proyecto.id, hoy))

        # Las dos consultas alimentan dos tarjetas: se piden una sola vez.
        por_materia = self.contexto.sesiones.segundos_por_materia(proyecto.id)
        sin_clasificar = self.contexto.sesiones.segundos_sin_clasificar(proyecto.id)
        avance = self.contexto.progreso.resumen(proyecto.id)
        self._pintar_materias(avance, por_materia, sin_clasificar)
        self._pintar_atencion(avance, por_materia, sin_clasificar)
        self._pintar_proyectos()

    def _pintar_cumplimiento(self, proyecto_id: int, hoy: date) -> None:
        """% de dias y de horas planeadas que no se cumplieron en los ultimos 30."""
        resumen = self.contexto.calendario.resumen_cumplimiento(
            proyecto_id, hoy - timedelta(days=_DIAS_GRAFICO - 1), hoy
        )
        if not resumen.dias_con_plan:
            self._metricas["dias_incumplidos"].establecer("—", "Sin bloques planeados")
            self._metricas["horas_incumplidas"].establecer("—", "Sin bloques planeados")
            return

        self._metricas["dias_incumplidos"].establecer(
            f"{resumen.pct_dias_incumplidos:.0f} %",
            f"{resumen.dias_incumplidos} de {resumen.dias_con_plan} dias planeados",
        )
        self._metricas["horas_incumplidas"].establecer(
            f"{resumen.pct_horas_incumplidas:.0f} %",
            f"{formato.horas(resumen.segundos_faltantes)} sin estudiar de lo planeado",
        )

    def _por_semana(self, proyecto_id: int, hoy: date) -> list[tuple[str, float]]:
        """Horas de las ultimas semanas, de lunes a domingo."""
        lunes = hoy - timedelta(days=hoy.weekday())
        primero = lunes - timedelta(weeks=_SEMANAS - 1)
        # Una consulta para todo el rango y se agrupa por semana aqui: antes era
        # una consulta por barra.
        por_dia = self.contexto.sesiones.segundos_por_dia(
            proyecto_id, primero.isoformat(), (lunes + timedelta(days=6)).isoformat()
        )
        semanas = [0] * _SEMANAS
        for fecha, segundos in por_dia.items():
            semanas[(date.fromisoformat(fecha) - primero).days // 7] += segundos
        return [
            (f"{inicio.day}/{inicio.month}", segundos / 3600)
            for inicio, segundos in (
                (primero + timedelta(weeks=n), s) for n, s in enumerate(semanas)
            )
        ]

    def _por_mes(self, proyecto_id: int, hoy: date) -> list[tuple[str, float]]:
        """Horas de los ultimos meses naturales."""
        barras = []
        ano, mes = hoy.year, hoy.month
        pendientes = []
        for _ in range(_MESES):
            pendientes.append((ano, mes))
            mes -= 1
            if mes == 0:
                ano, mes = ano - 1, 12

        ano_min, mes_min = pendientes[-1]
        por_mes = self.contexto.sesiones.segundos_por_periodo(
            proyecto_id, date(ano_min, mes_min, 1).isoformat(), hoy.isoformat(), "%Y-%m"
        )
        for ano_, mes_ in reversed(pendientes):
            inicio = date(ano_, mes_, 1)
            segundos = por_mes.get(f"{ano_:04d}-{mes_:02d}", 0)
            barras.append((formato.fecha_corta(inicio).split()[1], segundos / 3600))
        return barras

    def _pintar_materias(
        self, avance: ResumenProgreso, por_materia: dict[int, int], sin_clasificar: int
    ) -> None:
        vaciar(self._caja_materias)
        # El porcentaje es la parte del tiempo total de estudio, no la
        # comparacion con la materia mayor: si no, la primera siempre sale al
        # 100 % y el bloque se lee como un reparto que no es.
        total = sum(por_materia.values()) + sin_clasificar

        if not por_materia:
            _vaciar(
                self._caja_materias,
                "Ninguna sesion tiene materias asignadas.\n\n"
                "Al terminar un pomodoro puedes indicar que estudiaste; ese dato "
                "es lo que alimenta este bloque.",
            )
        else:
            materias = {m.materia_id: m.nombre for m in avance.materias}
            ordenadas = sorted(por_materia.items(), key=lambda par: par[1], reverse=True)
            for indice, (materia_id, segundos) in enumerate(ordenadas):
                nombre = materias.get(materia_id, "—")
                barra = BarraMateria(nombre, segundos, total, tokens.color_serie(indice))
                barra.setToolTip(f"{nombre}: {formato.horas(segundos)} de {formato.horas(total)}")
                self._caja_materias.addWidget(barra)

        if sin_clasificar:
            porcentaje = round(sin_clasificar * 100 / total) if total else 0
            nota = QLabel(f"Sin clasificar: {formato.horas(sin_clasificar)} ({porcentaje} %)")
            nota.setObjectName("TextoTenue")
            self._caja_materias.addWidget(nota)

    def _pintar_atencion(
        self, avance: ResumenProgreso, por_materia: dict[int, int], sin_clasificar: int
    ) -> None:
        """Donde pones las horas frente a lo que cada asignatura pesa.

        La tarjeta entera desaparece si el proyecto no reparte pesos: sin peso
        no hay objetivo con el que comparar y seria una lista de obviedades.
        """
        vaciar(self._caja_atencion)
        desvios = avance.desvio_atencion(por_materia)
        self._tarjeta_atencion.setVisible(bool(desvios))
        if not desvios:
            return

        if not por_materia:
            _vaciar(
                self._caja_atencion,
                "Etiqueta tus pomodoros con la materia que estudiaste y aqui "
                "veras si el reparto de tus horas sigue el peso de cada "
                "asignatura.",
            )
            return

        # Color por materia, en el orden del temario: asi una asignatura tiene
        # el mismo color aqui, en el Panel y en Progreso, aunque esta lista vaya
        # ordenada por deficit.
        colores = {
            m.materia_id: tokens.color_o_serie(m.color, indice)
            for indice, m in enumerate(avance.materias)
        }
        escala = max(max(d.real for d in desvios), max(d.objetivo for d in desvios))

        for desvio in desvios:
            barra = BarraAtencion(
                desvio.nombre,
                desvio.real,
                desvio.objetivo,
                colores.get(desvio.materia_id, tokens.TEXTO_SUAVE),
                escala=escala,
                desatendida=desvio.desatendida,
            )
            barra.setToolTip(
                f"{desvio.nombre}: {formato.horas(desvio.segundos)} "
                f"({desvio.real:.1f} % del tiempo clasificado) · le corresponde "
                f"{desvio.objetivo:.1f} % por su peso"
            )
            self._caja_atencion.addWidget(barra)

        pie: list[str] = ["La marca vertical es lo que le tocaria por su peso."]
        if sin_clasificar:
            # Se dice, porque el denominador es solo el tiempo clasificado: con
            # lo no clasificado dentro, todas las materias saldrian por debajo.
            pie.append(
                f"No cuentan {formato.horas(sin_clasificar)} sin clasificar."
            )
        if avance.pesadas_sin_temario:
            nombres = ", ".join(m.nombre for m in avance.pesadas_sin_temario)
            pie.append(f"Con peso y sin temario: {nombres}.")

        nota = QLabel(" ".join(pie))
        nota.setObjectName("TextoTenue")
        nota.setWordWrap(True)
        self._caja_atencion.addWidget(nota)

    def _pintar_proyectos(self) -> None:
        vaciar(self._caja_proyectos)
        por_proyecto = self.contexto.sesiones.segundos_por_proyecto()
        totales = [(p.nombre, por_proyecto.get(p.id, 0)) for p in self.contexto.proyectos.listar()]
        mayor = max((s for _, s in totales), default=0)
        if not mayor:
            _vaciar(self._caja_proyectos, "Todavia no hay tiempo registrado.")
            return
        for indice, (nombre, segundos) in enumerate(totales):
            barra = BarraMateria(nombre, segundos, mayor, tokens.color_serie(indice))
            barra.setToolTip(f"{nombre}: {formato.horas(segundos)}")
            self._caja_proyectos.addWidget(barra)



def _vaciar(caja: QVBoxLayout, mensaje: str) -> None:
    vaciar(caja)
    if not mensaje:
        return
    etiqueta = QLabel(mensaje)
    etiqueta.setObjectName("TextoTenue")
    etiqueta.setWordWrap(True)
    caja.addWidget(etiqueta)
