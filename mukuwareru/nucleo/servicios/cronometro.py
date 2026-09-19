"""Cronometro de la sesion de trabajo indefinida: cuenta hacia arriba.

Python puro, igual que ``RelojPomodoro``: la interfaz avanza el tiempo llamando
a ``avanzar(segundos)``, de modo que un test simula tres horas en microsegundos.

Existe porque no todo el estudio cabe en bloques de veinticinco minutos. Un
examen resuelto de principio a fin, o una clase, duran lo que duran, y trocear
eso en pomodoros solo para que el tiempo quede registrado seria poner la
herramienta por delante del estudio.

La diferencia con el reloj del Pomodoro no es solo el signo de la cuenta: aqui
**no hay fin previsto**, asi que nadie termina la sesion salvo el usuario. Por
eso ``detener`` devuelve lo transcurrido en lugar de limitarse a apagarse: ese
numero es lo unico que quedara registrado.
"""

from __future__ import annotations

from mukuwareru.nucleo.servicios.recorrido import Estado

__all__ = ["Cronometro"]


class Cronometro:
    """Tiempo acumulado de una sesion de trabajo sin duracion fijada."""

    def __init__(self) -> None:
        self.estado = Estado.DETENIDO
        self.transcurrido_seg = 0

    # -- Consulta ----------------------------------------------------------

    @property
    def activo(self) -> bool:
        """Si hay una sesion abierta, este corriendo o en pausa.

        Una pausa no cierra la sesion: el tiempo sigue ahi, pendiente de
        registrarse. Solo ``detener`` lo cierra.
        """
        return self.estado is not Estado.DETENIDO

    @property
    def corriendo(self) -> bool:
        """Si el tiempo esta avanzando ahora mismo."""
        return self.estado is Estado.CORRIENDO

    # -- Control -----------------------------------------------------------

    def iniciar(self) -> None:
        """Abre la sesion, o la reanuda tras una pausa."""
        self.estado = Estado.CORRIENDO

    def pausar(self) -> None:
        """Congela la cuenta conservando lo transcurrido."""
        if self.estado is Estado.CORRIENDO:
            self.estado = Estado.PAUSADO

    def alternar(self) -> None:
        """Alterna entre correr y pausar."""
        if self.estado is Estado.CORRIENDO:
            self.pausar()
        else:
            self.iniciar()

    def detener(self) -> int:
        """Cierra la sesion, la deja a cero y devuelve los segundos contados."""
        transcurrido = self.transcurrido_seg
        self.estado = Estado.DETENIDO
        self.transcurrido_seg = 0
        return transcurrido

    # -- Avance del tiempo -------------------------------------------------

    def avanzar(self, segundos: int = 1) -> None:
        """Suma tiempo. En pausa o detenido no cuenta nada."""
        if self.estado is Estado.CORRIENDO and segundos > 0:
            self.transcurrido_seg += segundos
