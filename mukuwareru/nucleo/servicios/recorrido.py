"""Recorrido de una sesion de estudio: la lista de bloques que se van a hacer.

Python puro, sin Qt y sin reloj del sistema. Aqui viven las fases, las
duraciones y el orden; ``RelojPomodoro`` solo cuenta hacia atras sobre el bloque
que toque.

El ciclo clasico 25/5 x4 deja de estar cableado. Se genera **una vez** desde
``Configuracion`` y a partir de ahi el usuario lo reordena, lo duplica, cambia
duraciones y le pone temas. El recorrido no se persiste: se rearma en cada
arranque desde la configuracion guardada.

Un recorrido **nunca se queda sin salida**: al pasar del ultimo bloque se anade
un par nuevo (trabajo + su descanso), respetando en que punto del ciclo se esta.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from mukuwareru.nucleo.modelos.entidades import TipoSesion


class Fase(StrEnum):
    """Tipo de bloque: trabajar, descansar poco o descansar mucho."""

    TRABAJO = "trabajo"
    DESCANSO_CORTO = "descanso_corto"
    DESCANSO_LARGO = "descanso_largo"

    @property
    def etiqueta(self) -> str:
        """Nombre presentable de la fase."""
        return {
            Fase.TRABAJO: "Trabajo",
            Fase.DESCANSO_CORTO: "Descanso corto",
            Fase.DESCANSO_LARGO: "Descanso largo",
        }[self]

    @property
    def es_descanso(self) -> bool:
        """Si la fase es de descanso, corto o largo."""
        return self is not Fase.TRABAJO

    def a_tipo_sesion(self) -> TipoSesion:
        """Equivalente en el modelo de datos."""
        return TipoSesion(self.value)


class Estado(StrEnum):
    """Si el reloj esta corriendo, en pausa o detenido."""

    DETENIDO = "detenido"
    CORRIENDO = "corriendo"
    PAUSADO = "pausado"


@dataclass(frozen=True, slots=True)
class Configuracion:
    """Duraciones por defecto del recorrido, en minutos.

    Deja de ser la forma del ciclo para ser su **semilla**: de aqui sale el
    recorrido inicial y de aqui salen los bloques nuevos.
    """

    trabajo_min: int = 25
    descanso_corto_min: int = 5
    descanso_largo_min: int = 15
    sesiones_por_ciclo: int = 4

    def segundos_de(self, fase: Fase) -> int:
        """Duracion en segundos de la fase indicada."""
        return self.minutos_de(fase) * 60

    def minutos_de(self, fase: Fase) -> int:
        """Duracion en minutos de la fase indicada."""
        return {
            Fase.TRABAJO: self.trabajo_min,
            Fase.DESCANSO_CORTO: self.descanso_corto_min,
            Fase.DESCANSO_LARGO: self.descanso_largo_min,
        }[fase]


@dataclass(slots=True)
class Bloque:
    """Un tramo del recorrido: que se hace, cuanto dura y sobre que tema.

    ``id`` no viene de la base de datos —el recorrido no se guarda— sino de un
    contador del propio recorrido: sirve para que la interfaz siga sabiendo cual
    es cual mientras se arrastran de sitio.
    """

    id: int
    tipo: Fase
    nombre: str = ""
    duracion_min: int = 25
    materia_id: int | None = None
    materia: str = ""
    color: str | None = None
    icono: str | None = None
    nota: str = ""
    completado: bool = False
    # Tocado a mano: ``reconfigurar`` no le pisa la duracion. Sin esta marca,
    # cambiar las duraciones por defecto borraria el trabajo del usuario.
    editado: bool = False

    @property
    def duracion_seg(self) -> int:
        """Duracion del bloque en segundos."""
        return self.duracion_min * 60

    @property
    def es_trabajo(self) -> bool:
        """Si es un bloque de trabajo y no de descanso."""
        return self.tipo is Fase.TRABAJO

    @property
    def etiqueta(self) -> str:
        """Nombre a mostrar: el suyo, o el de su fase si no tiene."""
        return self.nombre.strip() or self.tipo.etiqueta


def fases_del_ciclo(configuracion: Configuracion) -> list[Fase]:
    """Fases de un ciclo completo: trabajo y descanso, con el largo al final."""
    pasos: list[Fase] = []
    total = configuracion.sesiones_por_ciclo
    for numero in range(1, total + 1):
        pasos.append(Fase.TRABAJO)
        pasos.append(Fase.DESCANSO_LARGO if numero == total else Fase.DESCANSO_CORTO)
    return pasos


@dataclass(slots=True)
class Recorrido:
    """Lista ordenada de bloques con un indice que dice por donde se va."""

    configuracion: Configuracion = field(default_factory=Configuracion)
    bloques: list[Bloque] = field(default_factory=list)
    indice: int = 0
    # Armado a mano: cambiar `sesiones_por_ciclo` ya no puede regenerarlo.
    a_mano: bool = False
    _ultimo_id: int = 0

    @classmethod
    def desde_configuracion(cls, configuracion: Configuracion) -> Recorrido:
        """Recorrido inicial: un ciclo completo con las duraciones por defecto."""
        recorrido = cls(configuracion=configuracion)
        recorrido._regenerar()
        return recorrido

    # -- Consulta ----------------------------------------------------------

    @property
    def actual(self) -> Bloque:
        """Bloque en curso. Nunca falta: el recorrido se alarga solo."""
        if self.indice >= len(self.bloques):
            self._alargar()
        return self.bloques[self.indice]

    @property
    def total(self) -> int:
        """Cuantos bloques tiene el recorrido."""
        return len(self.bloques)

    @property
    def completados(self) -> int:
        """Bloques de trabajo ya terminados."""
        return sum(1 for bloque in self.bloques if bloque.es_trabajo and bloque.completado)

    @property
    def total_seg(self) -> int:
        """Duracion de todo el recorrido, en segundos."""
        return sum(bloque.duracion_seg for bloque in self.bloques)

    def restante_seg(self, restante_actual: int) -> int:
        """Tiempo que queda por delante, contando el bloque en curso."""
        pendientes = sum(
            bloque.duracion_seg for bloque in self.bloques[self.indice + 1 :]
        )
        return pendientes + max(0, restante_actual)

    @property
    def tocado(self) -> bool:
        """Si el recorrido ya no es el que salio de la configuracion."""
        return self.a_mano or self.indice > 0 or any(b.editado for b in self.bloques)

    def dentro(self, indice: int) -> bool:
        """Si el indice apunta a un bloque que existe."""
        return 0 <= indice < len(self.bloques)

    def recorrido_de(self, indice: int) -> bool:
        """Si ese bloque ya quedo atras."""
        return indice < self.indice

    # -- Edicion -----------------------------------------------------------

    def nuevo(self, tipo: Fase = Fase.TRABAJO, *, en: int | None = None) -> Bloque:
        """Crea un bloque con la duracion por defecto de su fase y lo inserta."""
        bloque = self._crear(tipo)
        self.insertar(bloque, en=en)
        return bloque

    def insertar(self, bloque: Bloque, *, en: int | None = None) -> int:
        """Mete un bloque en la posicion indicada, o al final. Devuelve su indice."""
        destino = len(self.bloques) if en is None else max(0, min(len(self.bloques), en))
        # Nunca por delante de lo ya recorrido: un bloque nuevo en el pasado no
        # se haria jamas y falsearia el contador de completados.
        destino = max(destino, self.indice)
        self.bloques.insert(destino, bloque)
        self.a_mano = True
        return destino

    def duplicar(self, indice: int) -> int:
        """Copia un bloque justo detras del original. Devuelve el indice nuevo."""
        if not self.dentro(indice):
            return -1
        copia = replace(
            self.bloques[indice], id=self._siguiente_id(), completado=False, editado=True
        )
        return self.insertar(copia, en=indice + 1)

    def eliminar(self, indice: int) -> bool:
        """Quita un bloque. Se niega a dejar el recorrido vacio."""
        if not self.dentro(indice) or len(self.bloques) <= 1:
            return False
        del self.bloques[indice]
        if indice < self.indice:
            self.indice -= 1
        self.a_mano = True
        return True

    def mover(self, origen: int, destino: int) -> int:
        """Reordena un bloque. Devuelve donde acabo, o ``-1`` si no se pudo.

        ``destino`` es el hueco entre bloques al que se suelta, contado **antes**
        de sacar el bloque de su sitio: es lo que sabe una operacion de arrastre.
        """
        if not self.dentro(origen):
            return -1
        destino = max(self.indice, min(len(self.bloques), destino))
        if destino in (origen, origen + 1):
            return origen

        bloque = self.bloques.pop(origen)
        if destino > origen:
            destino -= 1
        self.bloques.insert(destino, bloque)
        self.a_mano = True
        return destino

    def reemplazar(self, indice: int, bloque: Bloque) -> None:
        """Sustituye un bloque por su version editada."""
        if self.dentro(indice):
            bloque.editado = True
            self.bloques[indice] = bloque

    def reconfigurar(self, configuracion: Configuracion) -> None:
        """Aplica duraciones nuevas sin borrar lo que el usuario haya armado.

        Si el recorrido sigue siendo el que salio de la configuracion, cambiar el
        numero de sesiones por ciclo lo regenera entero. En cuanto hay algo hecho
        a mano se limita a refrescar la duracion de los bloques que nadie tocara.
        """
        cambia_la_forma = (
            configuracion.sesiones_por_ciclo != self.configuracion.sesiones_por_ciclo
        )
        intacto = not self.tocado
        self.configuracion = configuracion

        if cambia_la_forma and intacto:
            self._regenerar()
            return

        for bloque in self.bloques:
            if bloque.completado or bloque.editado:
                continue
            bloque.duracion_min = configuracion.minutos_de(bloque.tipo)

    def regenerar(self) -> None:
        """Vuelve al ciclo que describe la configuracion, tirando lo armado."""
        self._regenerar()

    # -- Avance ------------------------------------------------------------

    def avanzar(self, *, contar: bool) -> None:
        """Pasa al bloque siguiente, marcando el actual como hecho si procede."""
        if self.dentro(self.indice) and contar:
            self.bloques[self.indice].completado = True
        self.indice += 1
        if self.indice >= len(self.bloques):
            self._alargar()

    # -- Interno -----------------------------------------------------------

    def _siguiente_id(self) -> int:
        self._ultimo_id += 1
        return self._ultimo_id

    def _crear(self, tipo: Fase) -> Bloque:
        return Bloque(
            id=self._siguiente_id(),
            tipo=tipo,
            duracion_min=self.configuracion.minutos_de(tipo),
        )

    def _regenerar(self) -> None:
        self.bloques = [self._crear(fase) for fase in fases_del_ciclo(self.configuracion)]
        self.indice = 0
        self.a_mano = False

    def _alargar(self) -> None:
        """Anade el par siguiente para que el recorrido no se agote nunca.

        El descanso que le toca sale de cuantos bloques de trabajo hay ya: el
        largo cierra el ciclo, igual que en un recorrido recien generado.
        """
        trabajos = sum(1 for bloque in self.bloques if bloque.es_trabajo)
        por_ciclo = max(1, self.configuracion.sesiones_por_ciclo)
        cierra_ciclo = trabajos % por_ciclo == por_ciclo - 1
        self.bloques.append(self._crear(Fase.TRABAJO))
        self.bloques.append(
            self._crear(Fase.DESCANSO_LARGO if cierra_ciclo else Fase.DESCANSO_CORTO)
        )
