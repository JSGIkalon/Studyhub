"""Grafo de dependencias: una segunda lectura del temario existente.

Este servicio **no tiene ningun dato propio sobre el estudio**. Un nodo es un
puntero a una materia, un modulo, un hito o una evaluacion que ya existen, y su
estado se deduce del progreso real cada vez que se pide. No hay `marcar()`: para
completar un modulo se va a la vista Progreso, que es donde siempre ha estado.

Esa es la unica manera de que el grafo no pueda contradecir al resto de la
aplicacion. Guardar aqui un «completado» crearia un segundo sistema de progreso,
y el dia que discreparan no habria forma de saber cual miente.

Las dos reglas que gobiernan el grafo viven en funciones puras al final del
archivo —``estado_de`` y ``cierra_ciclo``—, para poder probarlas sin abrir una
base de datos, igual que ``repartir_cumplimiento``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Container, Iterable, Sequence
from dataclasses import dataclass

from mukuwareru.nucleo.modelos.entidades import (
    AristaGrafo,
    DestinoNodo,
    EstadoNodo,
    NodoGrafo,
)
from mukuwareru.nucleo.repositorios import (
    RepositorioEvaluaciones,
    RepositorioGrafo,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioModulos,
)


class CicloError(ValueError):
    """Conectar esos dos nodos cerraria un ciclo de prerrequisitos.

    Primera excepcion propia del proyecto. El sufijo ``Error`` rompe el
    castellano del resto de nombres, pero lo pide la convencion de ruff (N818) y
    es la unica senal de que una clase es lanzable.
    """


@dataclass(frozen=True, slots=True)
class NodoResuelto:
    """Un nodo listo para pintar: la referencia, el nombre real y el estado.

    ``total`` y ``completados`` estan en las unidades de cada tipo: modulos para
    una materia, y uno o cero para lo que simplemente esta hecho o no.
    """

    nodo: NodoGrafo
    nombre: str
    destino: DestinoNodo
    color: str | None = None
    total: int = 1
    completados: int = 0
    estado: EstadoNodo = EstadoNodo.DISPONIBLE
    prerrequisitos: tuple[tuple[int, ...], ...] = ()   # una tupla por grupo O

    @property
    def fraccion(self) -> float:
        """Avance entre 0 y 1."""
        return self.completados / self.total if self.total else 0.0

    @property
    def porcentaje(self) -> int:
        """Avance en porcentaje entero, para pintarlo."""
        return round(self.fraccion * 100)


@dataclass(frozen=True, slots=True)
class GrafoProyecto:
    """El grafo entero ya resuelto. Es lo unico que consume la vista."""

    nodos: tuple[NodoResuelto, ...] = ()
    aristas: tuple[AristaGrafo, ...] = ()

    @property
    def vacio(self) -> bool:
        """Si no hay nada colocado. La vista lo usa para el estado vacio."""
        return not self.nodos

    def por_id(self, nodo_id: int) -> NodoResuelto | None:
        """Un nodo resuelto por su identificador."""
        for nodo in self.nodos:
            if nodo.nodo.id == nodo_id:
                return nodo
        return None


@dataclass(frozen=True, slots=True)
class Candidato:
    """Una entidad del proyecto que todavia no esta en el lienzo."""

    destino: DestinoNodo
    objeto_id: int
    nombre: str
    detalle: str = ""


class ServicioGrafo:
    """Resuelve el grafo de un proyecto contra el progreso que ya existe."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._grafo = RepositorioGrafo(conexion)
        self._materias = RepositorioMaterias(conexion)
        self._modulos = RepositorioModulos(conexion)
        self._hitos = RepositorioHitos(conexion)
        self._evaluaciones = RepositorioEvaluaciones(conexion)

    # -- Lectura ---------------------------------------------------------------

    def cargar(self, proyecto_id: int) -> GrafoProyecto:
        """Nodos y aristas con el estado ya calculado.

        Las entidades se leen de una vez y se cruzan en memoria: una consulta
        por nodo convertiria pintar el lienzo en decenas de viajes, que es el
        mismo motivo por el que ``RepositorioEvaluaciones.listar`` reparte sus
        lineas asi.
        """
        nodos = self._grafo.listar_nodos(proyecto_id)
        aristas = self._grafo.listar_aristas(proyecto_id)
        if not nodos:
            return GrafoProyecto()

        avances = self._avances(proyecto_id, nodos)

        # Primera pasada: quien esta completado. Hace falta entera antes de
        # poder decidir si alguien esta bloqueado.
        completados = {
            nodo.id
            for nodo in nodos
            if avances.get(nodo.id, (1, 0))[1] >= avances.get(nodo.id, (1, 0))[0]
            and avances.get(nodo.id, (1, 0))[0] > 0
        }

        grupos = _agrupar(aristas)
        resueltos = tuple(
            self._resolver(nodo, avances, grupos.get(nodo.id, ()), completados)
            for nodo in nodos
        )
        return GrafoProyecto(nodos=resueltos, aristas=tuple(aristas))

    def candidatos(self, proyecto_id: int) -> list[Candidato]:
        """Entidades del proyecto que todavia no estan colocadas.

        Alimenta el panel lateral: lo que ya se ve en el lienzo no vuelve a
        ofrecerse, de modo que la no-duplicacion se nota antes de intentarla.
        """
        ocupados = self._grafo.ocupados(proyecto_id)
        fuera: list[Candidato] = []

        for materia in self._materias.listar(proyecto_id):
            if materia.id not in ocupados[DestinoNodo.MATERIA]:
                fuera.append(Candidato(DestinoNodo.MATERIA, materia.id, materia.nombre))
            # Los modulos se ofrecen aunque su materia ya este colocada: poner
            # «Probability» en el lienzo no puede esconder sus temas, que son
            # nodos legitimos por su cuenta.
            for modulo in self._modulos.listar(materia.id):
                if modulo.id in ocupados[DestinoNodo.MODULO]:
                    continue
                fuera.append(
                    Candidato(
                        DestinoNodo.MODULO, modulo.id, modulo.nombre, materia.nombre
                    )
                )

        for hito in self._hitos.listar(proyecto_id):
            if hito.id not in ocupados[DestinoNodo.HITO]:
                fuera.append(
                    Candidato(
                        DestinoNodo.HITO, hito.id, hito.titulo, hito.fecha.isoformat()
                    )
                )

        for evaluacion in self._evaluaciones.listar(proyecto_id):
            if evaluacion.id not in ocupados[DestinoNodo.EVALUACION]:
                fuera.append(
                    Candidato(
                        DestinoNodo.EVALUACION,
                        evaluacion.id,
                        evaluacion.titulo,
                        evaluacion.fecha.isoformat(),
                    )
                )
        return fuera

    # -- Escritura -------------------------------------------------------------

    def agregar(
        self,
        proyecto_id: int,
        destino: DestinoNodo,
        objeto_id: int,
        x: float,
        y: float,
    ) -> NodoGrafo:
        """Coloca una entidad en el lienzo. No la duplica: la referencia."""
        return self._grafo.crear_nodo(proyecto_id, destino, objeto_id, x=x, y=y)

    def mover(self, nodo_id: int, x: float, y: float) -> None:
        """Guarda la posicion de un nodo."""
        self._grafo.mover_nodo(nodo_id, x, y)

    def eliminar(self, nodo_id: int) -> None:
        """Quita el nodo del grafo. La materia, el modulo o el hito siguen ahi."""
        self._grafo.eliminar_nodo(nodo_id)

    def conectar(
        self, destino: int, origen: int, grupo: int | None = None
    ) -> AristaGrafo:
        """Anade un prerrequisito. ``grupo`` en ``None`` abre uno nuevo: un Y.

        Levanta ``CicloError`` —sin escribir nada— si ``destino`` ya alcanza a
        ``origen``: una dependencia circular no se puede cumplir nunca, y dejarla
        entrar convertiria a los dos nodos en bloqueados para siempre.
        """
        if destino == origen:
            raise CicloError("Un nodo no puede depender de si mismo")

        nodo = self._grafo.obtener_nodo(destino)
        if nodo is None:
            raise CicloError("El nodo de destino ya no existe")

        existentes = [
            (a.destino, a.origen) for a in self._grafo.listar_aristas(nodo.proyecto_id)
        ]
        if cierra_ciclo(existentes, destino, origen):
            raise CicloError("Esa conexion cerraria un ciclo de prerrequisitos")

        numero = grupo if grupo is not None else self._grafo.proximo_grupo(destino)
        return self._grafo.crear_arista(destino, origen, numero)

    def desconectar(self, destino: int, origen: int) -> None:
        """Quita un prerrequisito y compacta los grupos que queden."""
        self._grafo.eliminar_arista(destino, origen)
        self._renumerar(destino)

    def alternar_o(self, destino: int, origen_a: int, origen_b: int) -> bool:
        """Convierte dos prerrequisitos en alternativas, o los separa.

        Si ya comparten grupo —son un O— se separan y vuelven a ser ambos
        obligatorios. Si no, el segundo pasa al grupo del primero. Es el unico
        gesto que hace falta para construir cualquier combinacion de Y y O.
        """
        entrantes = {a.origen: a.grupo for a in self._grafo.entrantes(destino)}
        if origen_a not in entrantes or origen_b not in entrantes:
            return False

        if entrantes[origen_a] == entrantes[origen_b]:
            self._grafo.fijar_grupo(
                destino, origen_b, self._grafo.proximo_grupo(destino)
            )
        else:
            self._grafo.fijar_grupo(destino, origen_b, entrantes[origen_a])
        self._renumerar(destino)
        return True

    def _renumerar(self, destino: int) -> None:
        """Deja los grupos de un destino consecutivos desde 1.

        Sin esto quedarian huecos al borrar o al fundir, y los colores de la
        serie —que se eligen por numero de grupo— saltarian sin motivo visible.
        """
        entrantes = self._grafo.entrantes(destino)
        orden = {grupo: i + 1 for i, grupo in enumerate(sorted({a.grupo for a in entrantes}))}
        for arista in entrantes:
            if orden[arista.grupo] != arista.grupo:
                self._grafo.fijar_grupo(destino, arista.origen, orden[arista.grupo])

    # -- Interno ---------------------------------------------------------------

    def _avances(
        self, proyecto_id: int, nodos: Sequence[NodoGrafo]
    ) -> dict[int, tuple[int, int]]:
        """``(total, completados)`` de cada nodo, en las unidades de su tipo.

        Todo sale de los repositorios que ya existen. Aqui no se cuenta nada que
        no estuviera contado antes.
        """
        conteos = {
            c.materia_id: (c.total, c.completados)
            for c in self._modulos.conteo_por_materia(proyecto_id)
        }
        avances: dict[int, tuple[int, int]] = {}

        for nodo in nodos:
            if nodo.destino is DestinoNodo.MATERIA:
                # Una materia sin modulos no se puede medir por conteo; se trata
                # como una sola casilla sin marcar, igual que hace el progreso
                # con `pesadas_sin_temario`.
                total, hechos = conteos.get(nodo.objeto_id, (0, 0))
                avances[nodo.id] = (total, hechos) if total else (1, 0)
            elif nodo.destino is DestinoNodo.MODULO:
                modulo = self._modulos.obtener(nodo.objeto_id)
                avances[nodo.id] = (1, 1 if modulo and modulo.completado else 0)
            elif nodo.destino is DestinoNodo.HITO:
                hito = self._hitos.obtener(nodo.objeto_id)
                avances[nodo.id] = (1, 1 if hito and hito.completado else 0)
            else:
                # Una evaluacion cuenta como hecha en cuanto tiene nota. Una
                # pendiente esta declarada pero no se ha corregido.
                evaluacion = self._evaluaciones.obtener(nodo.objeto_id)
                hecha = evaluacion is not None and not evaluacion.pendiente
                avances[nodo.id] = (1, 1 if hecha else 0)
        return avances

    def _resolver(
        self,
        nodo: NodoGrafo,
        avances: dict[int, tuple[int, int]],
        grupos: tuple[tuple[int, ...], ...],
        completados: Container[int],
    ) -> NodoResuelto:
        """Cruza un nodo con su entidad y decide su estado."""
        total, hechos = avances.get(nodo.id, (1, 0))
        nombre, color = self._identidad(nodo)
        fraccion = hechos / total if total else 0.0
        return NodoResuelto(
            nodo=nodo,
            nombre=nodo.etiqueta or nombre,
            destino=nodo.destino,
            color=color,
            total=total,
            completados=hechos,
            estado=estado_de(fraccion, grupos, completados),
            prerrequisitos=grupos,
        )

    def _identidad(self, nodo: NodoGrafo) -> tuple[str, str | None]:
        """Nombre y color de la entidad a la que apunta el nodo.

        Se lee cada vez. Renombrar una materia en Progreso cambia el nodo sin
        que nadie tenga que sincronizar nada, que es el punto entero.
        """
        if nodo.destino is DestinoNodo.MATERIA:
            materia = self._materias.obtener(nodo.objeto_id)
            return (materia.nombre if materia else "?", materia.color if materia else None)
        if nodo.destino is DestinoNodo.MODULO:
            modulo = self._modulos.obtener(nodo.objeto_id)
            return (modulo.nombre if modulo else "?", None)
        if nodo.destino is DestinoNodo.HITO:
            hito = self._hitos.obtener(nodo.objeto_id)
            return (hito.titulo if hito else "?", hito.color if hito else None)
        evaluacion = self._evaluaciones.obtener(nodo.objeto_id)
        return (evaluacion.titulo if evaluacion else "?", None)


# -- Reglas puras: se prueban sin abrir una base de datos -----------------------


def estado_de(
    fraccion: float,
    grupos: Sequence[Sequence[int]],
    completados: Container[int],
) -> EstadoNodo:
    """Las cuatro reglas del estado de un nodo.

    1. Avance completo -> ``COMPLETADO``.
    2. Prerrequisitos sin cumplir -> ``BLOQUEADO``, **aunque haya avance**: el
       grafo esta precisamente para avisar de que se empezo por donde no era.
    3. Algo de avance -> ``EN_CURSO``.
    4. El resto -> ``DISPONIBLE``.

    Cumplir los prerrequisitos es que **todos** los grupos tengan **al menos un**
    origen completado: entre grupos es Y, dentro de un grupo es O. Sin grupos se
    considera cumplido, de modo que un nodo raiz siempre esta disponible.
    """
    if fraccion >= 1.0:
        return EstadoNodo.COMPLETADO
    if not all(any(origen in completados for origen in grupo) for grupo in grupos):
        return EstadoNodo.BLOQUEADO
    return EstadoNodo.EN_CURSO if fraccion > 0 else EstadoNodo.DISPONIBLE


def cierra_ciclo(
    aristas: Iterable[tuple[int, int]], destino: int, origen: int
) -> bool:
    """Si anadir ``origen -> destino`` cerraria un ciclo.

    Recorre hacia atras desde ``origen`` por sus propios prerrequisitos: si se
    llega a ``destino``, la arista nueva cerraria el circulo. Un diamante
    —A antes de B y de C, las dos antes de D— no es un ciclo y debe pasar.
    """
    if destino == origen:
        return True

    entrantes: dict[int, list[int]] = {}
    for hacia, desde in aristas:
        entrantes.setdefault(hacia, []).append(desde)

    pendientes = [origen]
    vistos: set[int] = set()
    while pendientes:
        actual = pendientes.pop()
        if actual == destino:
            return True
        if actual in vistos:
            continue
        vistos.add(actual)
        pendientes.extend(entrantes.get(actual, ()))
    return False


def _agrupar(aristas: Iterable[AristaGrafo]) -> dict[int, tuple[tuple[int, ...], ...]]:
    """Reparte las aristas por destino y por grupo O.

    Devuelve, para cada nodo, una tupla de grupos; cada grupo es una tupla de
    origenes alternativos. Es la forma que consume ``estado_de``.
    """
    por_destino: dict[int, dict[int, list[int]]] = {}
    for arista in aristas:
        por_destino.setdefault(arista.destino, {}).setdefault(arista.grupo, []).append(
            arista.origen
        )
    return {
        destino: tuple(tuple(grupos[g]) for g in sorted(grupos))
        for destino, grupos in por_destino.items()
    }
