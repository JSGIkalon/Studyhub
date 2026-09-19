"""Maquina de estados del Pomodoro.

Python puro: no conoce QTimer ni ningun reloj del sistema. La interfaz avanza el
tiempo llamando a ``avanzar(segundos)``, lo que permite simular un ciclo entero
en microsegundos desde un test.

El reloj **no decide la forma del ciclo**: eso es del ``Recorrido``, que es una
lista de bloques editable y reordenable. Aqui solo se cuenta hacia atras sobre el
bloque en curso y se avisa cuando llega a cero. Las fases, las duraciones y el
``Configuracion`` viven en ``recorrido.py`` y se reexportan aqui porque este era
su modulo de siempre.

El Pomodoro NO se asocia a un modulo: durante una sesion se pueden estudiar
varios temas. El etiquetado por materia es opcional y ocurre al terminar, aunque
un bloque con tema asignado se etiqueta solo.
"""

from __future__ import annotations

from dataclasses import dataclass

from mukuwareru.nucleo.servicios.recorrido import (
    Bloque,
    Configuracion,
    Estado,
    Fase,
    Recorrido,
    fases_del_ciclo,
)

__all__ = [
    "Bloque",
    "Configuracion",
    "Estado",
    "Fase",
    "FaseTerminada",
    "Recorrido",
    "RelojPomodoro",
    "fases_del_ciclo",
]


@dataclass(frozen=True, slots=True)
class FaseTerminada:
    """Lo que hay que persistir cuando una fase llega a cero."""

    fase: Fase
    duracion_seg: int
    bloque: Bloque | None = None


class RelojPomodoro:
    """Cuenta atras sobre el bloque en curso de un recorrido.

    Al completarse un bloque el reloj pasa al siguiente y **se detiene**: no
    arranca solo. Encadenar descansos sin querer es peor que pulsar un boton.
    """

    def __init__(
        self,
        configuracion: Configuracion | None = None,
        recorrido: Recorrido | None = None,
    ) -> None:
        self._recorrido = recorrido or Recorrido.desde_configuracion(
            configuracion or Configuracion()
        )
        self.estado = Estado.DETENIDO
        self.restante_seg = self._recorrido.actual.duracion_seg

    # -- Consulta ----------------------------------------------------------

    @property
    def recorrido(self) -> Recorrido:
        """Recorrido que se esta haciendo, para que la interfaz lo edite."""
        return self._recorrido

    @property
    def configuracion(self) -> Configuracion:
        """Duraciones por defecto vigentes."""
        return self._recorrido.configuracion

    @property
    def bloque(self) -> Bloque:
        """Bloque en curso."""
        return self._recorrido.actual

    @property
    def fase(self) -> Fase:
        """Fase del bloque en curso."""
        return self._recorrido.actual.tipo

    @property
    def duracion_seg(self) -> int:
        """Duracion total del bloque en curso."""
        return self._recorrido.actual.duracion_seg

    @property
    def transcurrido_seg(self) -> int:
        """Segundos ya consumidos del bloque en curso."""
        return self.duracion_seg - self.restante_seg

    @property
    def progreso(self) -> float:
        """Avance del bloque en curso, de 0.0 a 1.0."""
        duracion = self.duracion_seg
        return max(0.0, min(1.0, self.transcurrido_seg / duracion)) if duracion else 0.0

    @property
    def completadas(self) -> int:
        """Bloques de trabajo ya terminados."""
        return self._recorrido.completados

    @property
    def sesion_del_ciclo(self) -> int:
        """Numero de sesion de trabajo dentro del ciclo actual, empezando en 1."""
        return self.completadas % self._recorrido.configuracion.sesiones_por_ciclo + 1

    @property
    def restante_total_seg(self) -> int:
        """Tiempo que queda en todo el recorrido, contando el bloque en curso."""
        return self._recorrido.restante_seg(self.restante_seg)

    def secuencia(self) -> list[tuple[Fase, int]]:
        """Recorrido como lista de ``(fase, segundos)``, para mostrarlo."""
        return [(bloque.tipo, bloque.duracion_seg) for bloque in self._recorrido.bloques]

    def movible(self, indice: int) -> bool:
        """Si ese bloque se puede reordenar, duplicar o eliminar.

        Lo ya recorrido no se toca, y el bloque en curso tampoco mientras hay
        cuenta atras viva: moverlo dejaria el reloj contando sobre otra cosa.
        """
        if not self._recorrido.dentro(indice) or self._recorrido.recorrido_de(indice):
            return False
        return indice != self._recorrido.indice or self.estado is Estado.DETENIDO

    def editable(self, indice: int) -> bool:
        """Si los datos de ese bloque se pueden cambiar. El pasado no."""
        return self._recorrido.dentro(indice) and not self._recorrido.recorrido_de(indice)

    # -- Control -----------------------------------------------------------

    def iniciar(self) -> None:
        """Arranca o reanuda la cuenta atras."""
        if self.restante_seg > 0:
            self.estado = Estado.CORRIENDO

    def pausar(self) -> None:
        """Detiene la cuenta atras conservando el tiempo restante."""
        if self.estado is Estado.CORRIENDO:
            self.estado = Estado.PAUSADO

    def alternar(self) -> None:
        """Alterna entre correr y pausar."""
        if self.estado is Estado.CORRIENDO:
            self.pausar()
        else:
            self.iniciar()

    def reiniciar(self) -> None:
        """Vuelve al principio del bloque actual sin tocar el recorrido."""
        self.estado = Estado.DETENIDO
        self.restante_seg = self.duracion_seg

    def reiniciar_ciclo(self) -> None:
        """Tira el recorrido y vuelve a generarlo desde la configuracion."""
        self._recorrido.regenerar()
        self.reiniciar()

    def ir_a(self, indice: int) -> None:
        """Coloca el recorrido en otro bloque, sin contar nada como hecho."""
        if not self._recorrido.dentro(indice):
            return
        self._recorrido.indice = indice
        self.reiniciar()

    def saltar(self) -> None:
        """Pasa al bloque siguiente sin registrar nada.

        A diferencia de terminar el bloque, esto no cuenta como sesion
        completada: saltarse un pomodoro no es haberlo hecho.
        """
        self._pasar_a_siguiente(contar=self.fase is not Fase.TRABAJO)

    def aplicar(self, configuracion: Configuracion) -> None:
        """Cambia las duraciones por defecto y reinicia el bloque en curso.

        Reiniciar es lo honesto: si el usuario acorta la duracion a la mitad,
        arrastrar el tiempo restante anterior daria una cuenta atras absurda. Los
        bloques editados a mano no se pisan; eso lo decide el recorrido.
        """
        self._recorrido.reconfigurar(configuracion)
        self.reiniciar()

    # -- Edicion del recorrido ---------------------------------------------

    def ajustar_duracion(self, indice: int, minutos: int) -> None:
        """Cambia la duracion de un bloque respetando lo ya contado.

        Con el reloj vivo sobre ese bloque se traslada la diferencia al tiempo
        restante: pasar de 25 a 45 minutos con 24:13 en pantalla deja 44:13, y no
        reinicia lo que ya se llevaba trabajado.
        """
        if not self.editable(indice):
            return
        bloque = self._recorrido.bloques[indice]
        anterior = bloque.duracion_seg
        bloque.duracion_min = max(1, minutos)
        bloque.editado = True
        self._trasladar(indice, anterior, bloque.duracion_seg)

    def reemplazar_bloque(self, indice: int, bloque: Bloque) -> None:
        """Cambia un bloque entero por su version editada.

        Cambiarle el nombre o el tema a un bloque en marcha no puede tocar la
        cuenta atras; cambiarle la duracion, si, y solo por la diferencia.
        """
        if not self.editable(indice):
            return
        anterior = self._recorrido.bloques[indice].duracion_seg
        self._recorrido.reemplazar(indice, bloque)
        self._trasladar(indice, anterior, bloque.duracion_seg)

    def _trasladar(self, indice: int, anterior: int, nueva: int) -> None:
        """Lleva al restante el cambio de duracion del bloque en curso."""
        if indice != self._recorrido.indice or nueva == anterior:
            return
        if self.estado is Estado.DETENIDO:
            self.restante_seg = nueva
        else:
            self.restante_seg = max(1, self.restante_seg + nueva - anterior)

    def recolocar(self) -> None:
        """Reajusta la cuenta atras tras una edicion estructural del recorrido."""
        if self.estado is Estado.DETENIDO:
            self.restante_seg = self.duracion_seg
        else:
            self.restante_seg = max(1, min(self.restante_seg, self.duracion_seg))

    # -- Avance del tiempo -------------------------------------------------

    def avanzar(self, segundos: int = 1) -> FaseTerminada | None:
        """Consume tiempo y devuelve la fase terminada, si ha llegado a cero.

        El exceso se descarta: al terminar un bloque el reloj se detiene, asi que
        no tiene sentido arrastrar segundos al siguiente.
        """
        if self.estado is not Estado.CORRIENDO or segundos <= 0:
            return None

        self.restante_seg -= segundos
        if self.restante_seg > 0:
            return None

        bloque = self._recorrido.actual
        terminada = FaseTerminada(
            fase=bloque.tipo, duracion_seg=bloque.duracion_seg, bloque=bloque
        )
        self._pasar_a_siguiente(contar=True)
        return terminada

    # -- Interno -----------------------------------------------------------

    def _pasar_a_siguiente(self, *, contar: bool) -> None:
        self._recorrido.avanzar(contar=contar)
        self.estado = Estado.DETENIDO
        self.restante_seg = self.duracion_seg
