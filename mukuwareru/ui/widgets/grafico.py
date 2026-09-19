"""Tarjeta con un grafico de barras verticales.

Nacio dentro de la vista de Estadisticas y salio de ahi cuando Resultados quiso
pintar la evolucion de las notas. Por eso la unidad del eje y el tope son
parametros: el mismo grafico sirve para horas y para porcentajes.
"""

from __future__ import annotations

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets.tarjeta import Tarjeta


class GraficoBarras(Tarjeta):
    """Barras verticales sin leyenda, con el fondo del tema.

    ``formato_valor`` es el de ``QValueAxis.setLabelFormat`` (``"%.0f h"``,
    ``"%.0f %%"``). ``maximo`` fija el tope del eje; con ``None`` se ajusta al
    dato mayor, que es lo que se quiere para horas y no para porcentajes.
    """

    def __init__(
        self,
        titulo: str,
        color: str,
        *,
        formato_valor: str = "%.0f h",
        maximo: float | None = None,
    ) -> None:
        super().__init__(titulo)
        self._color = color
        self._formato_valor = formato_valor
        self._maximo = maximo

        self._grafico = QChart()
        self._grafico.legend().setVisible(False)
        self._grafico.setBackgroundVisible(False)
        self._grafico.setPlotAreaBackgroundVisible(False)
        self._grafico.setMargins(QMargins(0, 0, 0, 0))

        self._vista = QChartView(self._grafico)
        self._vista.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._vista.setMinimumHeight(220)
        self._vista.setStyleSheet("background: transparent;")
        self.agregar(self._vista)

    def establecer(self, barras: list[tuple[str, float]]) -> None:
        """Reemplaza el contenido del grafico."""
        self._grafico.removeAllSeries()
        for eje in list(self._grafico.axes()):
            self._grafico.removeAxis(eje)
        if not barras:
            return

        conjunto = QBarSet("")
        conjunto.setColor(QColor(self._color))
        conjunto.setBorderColor(QColor(self._color))
        conjunto.append([valor for _, valor in barras])

        serie = QBarSeries()
        serie.setBarWidth(0.75)
        serie.append(conjunto)
        self._grafico.addSeries(serie)

        categorias = QBarCategoryAxis()
        categorias.append([etiqueta for etiqueta, _ in barras])
        categorias.setLabelsColor(QColor(tokens.TEXTO_TENUE))
        categorias.setGridLineVisible(False)
        categorias.setLineVisible(False)
        categorias.setLabelsFont(QFont(tokens.FUENTE, tokens.TAM_PEQUENO))
        self._grafico.addAxis(categorias, Qt.AlignmentFlag.AlignBottom)
        serie.attachAxis(categorias)

        valores = QValueAxis()
        tope = self._maximo or max(1.0, max(valor for _, valor in barras) * 1.15)
        valores.setRange(0, tope)
        valores.setLabelFormat(self._formato_valor)
        valores.setLabelsColor(QColor(tokens.TEXTO_TENUE))
        valores.setGridLineColor(QColor(tokens.BORDE_SUTIL))
        valores.setLineVisible(False)
        valores.setLabelsFont(QFont(tokens.FUENTE, tokens.TAM_PEQUENO))
        valores.setTickCount(5)
        self._grafico.addAxis(valores, Qt.AlignmentFlag.AlignLeft)
        serie.attachAxis(valores)
