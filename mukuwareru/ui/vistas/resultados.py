"""Resultados: que tal lo haces, no cuanto temario llevas.

Progreso responde a «cuanto he cubierto» y Estadisticas a «cuanto he estudiado».
Esta vista responde a la tercera pregunta, que es la que predice el resultado:
**cuanto se**. Son ejes distintos y no se mezclan en una sola cifra.

No es una vista solo para el CFA: un simulacro, un parcial de master, un quiz de
un curso y el examen de una certificacion se registran igual, porque la escala
es la del examen —puntos obtenidos sobre posibles— y no una escala interna.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mukuwareru.nucleo.modelos import Evaluacion
from mukuwareru.nucleo.servicios import EscalaNotas, ResumenResultados
from mukuwareru.ui import iconos
from mukuwareru.ui.dialogos.escala import DialogoEscala
from mukuwareru.ui.dialogos.escenarios import DialogoEscenarios
from mukuwareru.ui.dialogos.evaluacion import DialogoEvaluacion
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.vistas.base import VistaBase
from mukuwareru.ui.widgets import BarraMateria, GraficoBarras, Tarjeta, contenedor, vaciar
from mukuwareru.utilidades import formato

# Con una sola evaluacion no hay evolucion que ensenar: un grafico de una barra
# ocupa media pantalla para decir lo que ya dice la cifra de arriba.
_MINIMO_PARA_EVOLUCION = 2


class VistaResultados(VistaBase):
    """Nota por asignatura, evolucion e historial de examenes."""

    titulo = "Resultados"
    dominio = "resultados"
    ignora = frozenset({"anotaciones", "documentos", "notas", "sesiones"})

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

        self._tarjeta_calculo = Tarjeta("Como voy y que necesito")
        self._caja_calculo = QVBoxLayout()
        self._caja_calculo.setSpacing(2)
        self._tarjeta_calculo.agregar(contenedor(self._caja_calculo))
        self._columna.addWidget(self._tarjeta_calculo)

        self._tarjeta_asignaturas = Tarjeta("Nota por asignatura")
        self._caja_asignaturas = QVBoxLayout()
        self._caja_asignaturas.setSpacing(2)
        self._tarjeta_asignaturas.agregar(contenedor(self._caja_asignaturas))
        self._columna.addWidget(self._tarjeta_asignaturas)

        self._evolucion = GraficoBarras(
            "Evolucion", tokens.INFO, formato_valor="%.0f %%", maximo=100.0
        )
        self._columna.addWidget(self._evolucion)

        self._tarjeta_historial = Tarjeta("Historial")
        self._caja_historial = QVBoxLayout()
        self._caja_historial.setSpacing(tokens.ESPACIO_PEQUENO)
        self._tarjeta_historial.agregar(contenedor(self._caja_historial))
        self._columna.addWidget(self._tarjeta_historial)

        self._columna.addStretch(1)

        # Escala vigente del proyecto activo. Se refresca en cada `recargar`; el
        # valor inicial es el porcentaje de siempre.
        self._escala = EscalaNotas()

    def _construir_cabecera(self) -> QVBoxLayout:
        cabecera = QVBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        fila = QHBoxLayout()
        titulo = QLabel(self.titulo)
        titulo.setObjectName("TituloVista")
        fila.addWidget(titulo)
        fila.addStretch(1)

        self._boton_escenarios = QPushButton("  Escenarios")
        self._boton_escenarios.setIcon(iconos.icono("diana", tokens.TEXTO_SUAVE))
        self._boton_escenarios.setToolTip(
            "Supon notas para lo que te queda y mira como saldria la final. "
            "No modifica ninguna nota real."
        )
        self._boton_escenarios.clicked.connect(self._escenarios)
        fila.addWidget(self._boton_escenarios)

        escala = QPushButton("  Escala")
        escala.setIcon(iconos.icono("engranaje", tokens.TEXTO_SUAVE))
        escala.setToolTip("En que unidades se leen las notas: 0-5, 0-100…")
        escala.clicked.connect(self._editar_escala)
        fila.addWidget(escala)

        registrar = QPushButton("  Registrar resultado")
        registrar.setIcon(iconos.icono("mas", tokens.TEXTO_SUAVE))
        registrar.clicked.connect(self._registrar)
        fila.addWidget(registrar)
        cabecera.addLayout(fila)

        self._resumen = QLabel()
        self._resumen.setObjectName("TextoSuave")
        self._resumen.setWordWrap(True)
        cabecera.addWidget(self._resumen)

        self._avisos = QLabel()
        self._avisos.setObjectName("TextoTenue")
        self._avisos.setWordWrap(True)
        cabecera.addWidget(self._avisos)
        return cabecera

    # -- Datos --------------------------------------------------------------

    def recargar(self) -> None:
        """Reconstruye las tres tarjetas con los resultados del proyecto activo."""
        vaciar(self._caja_asignaturas)
        vaciar(self._caja_historial)

        vaciar(self._caja_calculo)

        proyecto = self.contexto.proyecto
        if proyecto is None:
            self._resumen.setText("Sin proyecto seleccionado.")
            self._avisos.setText("")
            self._evolucion.establecer([])
            self._tarjeta_asignaturas.setVisible(False)
            self._tarjeta_calculo.setVisible(False)
            self._evolucion.setVisible(False)
            self._tarjeta_historial.setVisible(False)
            self._boton_escenarios.setEnabled(False)
            return

        resultado = self.contexto.resultados.resumen(proyecto.id)
        self._escala = self.contexto.resultados.escala(proyecto.id)
        self._pintar_calculo(resultado)
        self._escribir_resumen(resultado)
        self._escribir_avisos(resultado)
        self._pintar_asignaturas(resultado)
        self._pintar_evolucion(proyecto.id, resultado)
        self._pintar_historial(resultado)

    def _escribir_resumen(self, resultado: ResumenResultados) -> None:
        if not resultado.hay_evaluaciones:
            self._resumen.setText(
                "Aun no has registrado ningun resultado. Anota tu primer "
                "simulacro, parcial o quiz y sabras en que asignatura fallas."
            )
            return

        cuantas = len(resultado.evaluaciones)
        texto = f"Nota media: {resultado.porcentaje} %"
        if resultado.hay_pesos:
            texto += (
                f"  ·  ponderada por asignatura: {resultado.porcentaje_ponderado} %"
            )
        texto += f"  ·  {cuantas} " + ("evaluacion" if cuantas == 1 else "evaluaciones")
        self._resumen.setText(texto)

    def _pintar_calculo(self, resultado: ResumenResultados) -> None:
        """Nota acumulada, peso pendiente y nota necesaria para aprobar.

        La tarjeta solo aparece cuando hay algo que calcular. Con dos simulacros
        sueltos y sin nada pendiente, «necesitas un 0» no informa de nada.
        """
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return

        calculo = self.contexto.resultados.calculo(proyecto.id)
        self._boton_escenarios.setEnabled(bool(resultado.pendientes))

        visible = bool(resultado.hay_evaluaciones)
        self._tarjeta_calculo.setVisible(visible)
        if not visible:
            return

        escala = self._escala
        self._caja_calculo.addWidget(
            _linea(
                "Nota acumulada",
                escala.formatear(calculo.nota_acumulada),
                f"sobre el peso ya evaluado ({calculo.peso_evaluado:g})",
            )
        )
        self._caja_calculo.addWidget(
            _linea(
                "Aprobado",
                escala.formatear(escala.fraccion_aprobado),
                f"escala {escala.minimo:g} a {escala.maximo:g}",
            )
        )

        if not calculo.hay_pendiente:
            self._caja_calculo.addWidget(
                _linea(
                    "Pendiente",
                    "nada",
                    "declara un examen sin nota para saber que necesitas en el",
                )
            )
            return

        self._caja_calculo.addWidget(
            _linea(
                "Peso pendiente",
                f"{calculo.peso_pendiente:g}",
                f"{len(resultado.pendientes)} evaluacion(es) sin corregir",
            )
        )

        necesaria = calculo.fraccion_necesaria
        if necesaria is None:
            return
        if calculo.asegurado:
            self._caja_calculo.addWidget(
                _linea("Ya aprobado", "—", "pase lo que pase en lo que queda")
            )
        elif not calculo.alcanzable:
            self._caja_calculo.addWidget(
                _linea(
                    "Nota necesaria",
                    escala.formatear(necesaria),
                    "por encima del maximo: no se puede aprobar con lo que queda",
                    color=tokens.ACENTO,
                )
            )
        else:
            self._caja_calculo.addWidget(
                _linea(
                    "Nota necesaria",
                    escala.formatear(necesaria),
                    "de media en lo que queda, para aprobar",
                    color=tokens.EXITO if necesaria <= calculo.nota_acumulada else tokens.AVISO,
                )
            )

    def _escribir_avisos(self, resultado: ResumenResultados) -> None:
        """Por que la nota ponderada puede no cuadrar con la media."""
        avisos: list[str] = []
        if resultado.pesadas_sin_evaluar:
            nombres = ", ".join(a.nombre for a in resultado.pesadas_sin_evaluar)
            avisos.append(
                f"Con peso pero sin ninguna nota todavia, asi que no entran en el "
                f"ponderado: {nombres}."
            )
        if resultado.sin_desglose:
            cuantas = len(resultado.sin_desglose)
            avisos.append(
                f"{cuantas} "
                + ("evaluacion" if cuantas == 1 else "evaluaciones")
                + " sin desglose: cuentan para la media, pero no para ninguna "
                "asignatura."
            )
        self._avisos.setText("\n".join(avisos))

    def _pintar_asignaturas(self, resultado: ResumenResultados) -> None:
        evaluadas = [a for a in resultado.asignaturas if a.medible]
        self._tarjeta_asignaturas.setVisible(bool(evaluadas))
        if not evaluadas:
            return

        for indice, asignatura in enumerate(resultado.asignaturas):
            if not asignatura.medible:
                continue
            barra = BarraMateria(
                asignatura.nombre,
                round(asignatura.obtenidos),
                round(asignatura.posibles),
                tokens.color_serie(indice),
                cuota=resultado.cuota(asignatura) if resultado.hay_pesos else None,
            )
            barra.setToolTip(
                f"{asignatura.nombre}: {asignatura.porcentaje} % "
                f"({asignatura.obtenidos:g} de {asignatura.posibles:g} puntos "
                f"en {asignatura.evaluaciones} "
                + ("evaluacion)" if asignatura.evaluaciones == 1 else "evaluaciones)")
            )
            self._caja_asignaturas.addWidget(barra)

    def _pintar_evolucion(self, proyecto_id: int, resultado: ResumenResultados) -> None:
        evolucion = self.contexto.resultados.evolucion(proyecto_id)
        visible = len(evolucion) >= _MINIMO_PARA_EVOLUCION
        self._evolucion.setVisible(visible)
        if not visible:
            self._evolucion.establecer([])
            return
        self._evolucion.establecer(
            [(f"{fecha.day}/{fecha.month}", float(pct)) for fecha, pct in evolucion]
        )

    def _pintar_historial(self, resultado: ResumenResultados) -> None:
        self._tarjeta_historial.setVisible(resultado.hay_evaluaciones)
        for evaluacion in resultado.evaluaciones:
            fila = _FilaEvaluacion(evaluacion)
            fila.editar.connect(self._editar)
            fila.eliminar.connect(self._eliminar)
            self._caja_historial.addWidget(fila)

    def _al_cambiar(self) -> None:
        self.marcar_sucia()
        self.refrescar_si_hace_falta()
        self.contexto.notificar_cambio(self)

    # -- Acciones -----------------------------------------------------------

    def _registrar(self) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        dialogo = DialogoEvaluacion(
            self.contexto.resultados.materias(proyecto.id),
            self._hitos_libres(proyecto.id),
            parent=self,
        )
        if dialogo.exec():
            self.contexto.resultados.registrar(proyecto.id, dialogo.datos())
            self._al_cambiar()

    def _editar(self, evaluacion: Evaluacion) -> None:
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        dialogo = DialogoEvaluacion(
            self.contexto.resultados.materias(proyecto.id),
            self._hitos_libres(proyecto.id, incluir=evaluacion.hito_id),
            evaluacion,
            parent=self,
        )
        if dialogo.exec():
            self.contexto.resultados.editar(evaluacion.id, dialogo.datos())
            self._al_cambiar()

    def _eliminar(self, evaluacion: Evaluacion) -> None:
        respuesta = QMessageBox.question(
            self,
            "Eliminar resultado",
            f"Se eliminara «{evaluacion.titulo}»"
            + (
                " (pendiente).\n"
                if evaluacion.pendiente
                else f" ({evaluacion.porcentaje} %).\n"
            )
            + "Esta accion no se puede deshacer.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self.contexto.resultados.eliminar(evaluacion.id)
            self._al_cambiar()

    def _editar_escala(self) -> None:
        """Cambia las unidades. No altera ninguna nota guardada."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        dialogo = DialogoEscala(self.contexto.resultados.escala(proyecto.id), self)
        if dialogo.exec():
            self.contexto.resultados.fijar_escala(proyecto.id, dialogo.escala())
            self._al_cambiar()

    def _escenarios(self) -> None:
        """Simulacion sobre lo pendiente. No escribe nada, ni al aceptar."""
        proyecto = self.contexto.proyecto
        if proyecto is None:
            return
        pendientes = self.contexto.resultados.resumen(proyecto.id).pendientes
        if not pendientes:
            QMessageBox.information(
                self,
                "Escenarios",
                "No hay ninguna evaluacion pendiente que simular.\n"
                "Registra un examen sin nota —solo su peso y su fecha— y podras "
                "preguntarte que necesitas en el.",
            )
            return
        DialogoEscenarios(
            pendientes,
            self.contexto.resultados.escala(proyecto.id),
            lambda supuestos: self.contexto.resultados.simular(proyecto.id, supuestos),
            self,
        ).exec()

    def _hitos_libres(self, proyecto_id: int, *, incluir: int | None = None) -> list:
        """Fechas del calendario que aun no tienen resultado.

        Como maximo hay una evaluacion por hito, asi que ofrecer los ocupados
        solo llevaria a un fallo de clave unica. Al editar se incluye el propio,
        o el combo perderia la fecha que ya tenia elegida.
        """
        ocupados = {
            e.hito_id
            for e in self.contexto.evaluaciones.listar(proyecto_id)
            if e.hito_id is not None and e.hito_id != incluir
        }
        return [
            h for h in self.contexto.hitos.listar(proyecto_id) if h.id not in ocupados
        ]


class _FilaEvaluacion(QWidget):
    """Una linea del historial: titulo, fecha, puntuacion y menu."""

    editar = Signal(object)
    eliminar = Signal(object)

    def __init__(self, evaluacion: Evaluacion) -> None:
        super().__init__()
        self.setObjectName("Transparente")
        self._evaluacion = evaluacion

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(tokens.ESPACIO_PEQUENO)

        detalle = QVBoxLayout()
        detalle.setSpacing(0)
        titulo = QLabel(evaluacion.titulo)
        titulo.setProperty("fuerte", True)
        titulo.setWordWrap(True)
        detalle.addWidget(titulo)

        partes = [formato.fecha_corta(evaluacion.fecha)]
        if evaluacion.pendiente:
            partes.append("pendiente")
        if evaluacion.peso != 1.0:
            partes.append(f"peso {evaluacion.peso:g}")
        if not evaluacion.materias:
            partes.append("sin desglose")
        elif not evaluacion.cuadra:
            partes.append("el desglose no cuadra con la nota global")
        if evaluacion.nota:
            partes.append(evaluacion.nota)
        pie = QLabel("  ·  ".join(partes))
        pie.setObjectName("TextoTenue")
        # Una nota larga en una sola linea fijaba un ancho minimo enorme y
        # empujaba toda la vista fuera de la pantalla.
        pie.setWordWrap(True)
        detalle.addWidget(pie)
        fila.addLayout(detalle, 1)

        puntos = QLabel(
            f"— / {evaluacion.puntos_posibles:g}"
            if evaluacion.pendiente
            else f"{evaluacion.puntos_obtenidos:g} / {evaluacion.puntos_posibles:g}"
        )
        puntos.setObjectName("TextoSuave")
        fila.addWidget(puntos)

        # Una pendiente no ensena un 0 %: no la ha hecho nadie todavia.
        porcentaje = QLabel("—" if evaluacion.pendiente else f"{evaluacion.porcentaje} %")
        porcentaje.setStyleSheet(
            f"font-weight: 600; color: {tokens.TEXTO_TENUE};"
            if evaluacion.pendiente
            else "font-weight: 600;"
        )
        porcentaje.setFixedWidth(52)
        porcentaje.setAlignment(Qt.AlignmentFlag.AlignRight)
        fila.addWidget(porcentaje)

        opciones = QPushButton("⋯")
        opciones.setObjectName("ElementoNav")
        opciones.setFixedWidth(28)
        opciones.setCursor(Qt.CursorShape.PointingHandCursor)
        opciones.clicked.connect(self._menu)
        fila.addWidget(opciones)

    def _menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Editar…", lambda: self.editar.emit(self._evaluacion))
        menu.addSeparator()
        menu.addAction("Eliminar…", lambda: self.eliminar.emit(self._evaluacion))
        menu.exec(self.cursor().pos())


def _linea(
    etiqueta: str, valor: str, detalle: str = "", *, color: str | None = None
) -> QWidget:
    """Una fila «concepto — cifra — explicacion» de la calculadora."""
    fila = QHBoxLayout()
    fila.setContentsMargins(0, 0, 0, 0)
    fila.setSpacing(tokens.ESPACIO_PEQUENO)

    nombre = QLabel(etiqueta)
    nombre.setObjectName("TextoSuave")
    nombre.setFixedWidth(150)
    fila.addWidget(nombre)

    cifra = QLabel(valor)
    cifra.setStyleSheet(
        "font-weight: 600;" + (f" color: {color};" if color else "")
    )
    fila.addWidget(cifra)

    if detalle:
        explicacion = QLabel(detalle)
        explicacion.setObjectName("TextoTenue")
        explicacion.setWordWrap(True)
        fila.addWidget(explicacion, 1)
    else:
        fila.addStretch(1)
    return contenedor(fila)

