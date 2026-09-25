"""Lo comun a los dos relojes compactos: el de la barra lateral y el flotante.

Los dos ensenan lo mismo —fase, tiempo, Pausar/Reanudar y, en una sesion
indefinida, Detener— y se refrescan cada segundo. Lo unico que cambia es donde
coloca cada uno las piezas, asi que las piezas y su logica viven aqui.

El color de la fase **no** se pone con ``setStyleSheet`` en cada tic: eso
obligaba a Qt a re-analizar la hoja de estilos cuatro veces por segundo. Va en
una propiedad dinamica (``fase``) que el QSS colorea, y solo se toca cuando la
fase cambia.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from mukuwareru.nucleo.servicios import Estado, Fase
from mukuwareru.ui.tema import tokens
from mukuwareru.utilidades import formato

# Color de cada fase, para quien pinte a mano (los bloques del timeline). Los
# relojes compactos usan los mismos colores desde el QSS (`[fase="..."]`).
COLOR_FASE = {
    Fase.TRABAJO: tokens.ACENTO,
    Fase.DESCANSO_CORTO: tokens.INFO,
    Fase.DESCANSO_LARGO: tokens.EXITO,
}

_LIBRE = "libre"
_ETIQUETA_LIBRE = "TRABAJO INDEFINIDO"


class PiezasReloj:
    """Etiquetas y botones de un reloj compacto, con su refresco.

    No es un widget: el contenedor coloca las piezas donde quiera y conecta los
    botones a sus senales.
    """

    def __init__(self) -> None:
        self.fase = QLabel()
        self.fase.setObjectName("RelojFase")
        self.tiempo = QLabel()
        self.tiempo.setObjectName("RelojTiempo")

        self.alternar = QPushButton()
        self.alternar.setCursor(Qt.CursorShape.PointingHandCursor)

        self.detener = QPushButton("Detener")
        self.detener.setToolTip("Cierra la sesion y registra el tiempo.")
        self.detener.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detener.setVisible(False)

        self._clave: str | None = None

    def actualizar(self, fase: Fase, restante_seg: int, estado: Estado) -> bool:
        """Cuenta atras del Pomodoro. Devuelve si cambio la fase."""
        self.detener.setVisible(False)
        return self._volcar(str(fase), fase.etiqueta.upper(), restante_seg, estado)

    def actualizar_libre(self, transcurrido_seg: int, estado: Estado) -> bool:
        """Sesion indefinida: cuenta hacia arriba y ofrece Detener.

        Detener sale aqui en los dos relojes: una sesion indefinida no termina
        sola, y obligar a volver a la seccion Pomodoro para cerrarla era un
        paso de mas.
        """
        self.detener.setVisible(True)
        return self._volcar(_LIBRE, _ETIQUETA_LIBRE, transcurrido_seg, estado)

    def _volcar(self, clave: str, etiqueta: str, segundos: int, estado: Estado) -> bool:
        self.tiempo.setText(formato.duracion_reloj(segundos))
        self.alternar.setText("Pausar" if estado is Estado.CORRIENDO else "Reanudar")
        if clave == self._clave:
            return False

        self._clave = clave
        self.fase.setText(etiqueta)
        for etiqueta_qt in (self.fase, self.tiempo):
            _repulir(etiqueta_qt, clave)
        return True


def _repulir(widget: QWidget, fase: str) -> None:
    """Cambia la propiedad ``fase`` y fuerza a Qt a re-aplicar el selector."""
    widget.setProperty("fase", fase)
    estilo = widget.style()
    estilo.unpolish(widget)
    estilo.polish(widget)
