"""Nota de las evaluaciones.

Tres niveles, cada uno ponderado por el de abajo:

* **Evaluacion** — puntos obtenidos sobre posibles. Es el dato crudo.
* **Asignatura** — media de sus evaluaciones ponderada por ``evaluacion.peso``.
  Es el «30 % parcial + 70 % final» de una asignatura de master.
* **Proyecto** — media de las asignaturas ponderada por ``materia.peso``, el
  mismo que usa el progreso.

Nada de esto tiene que ver con el progreso del temario, y es deliberado: se puede
llevar el 30 % del temario y sacar un 70 % en un simulacro. Progreso mide lo
cubierto; esto mide el rendimiento. Comparten ``materia.peso`` y nada mas.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from mukuwareru.nucleo.modelos.entidades import Evaluacion, LineaEvaluacion, Materia
from mukuwareru.nucleo.repositorios import (
    LineaPesada,
    RepositorioAjustes,
    RepositorioEvaluaciones,
    RepositorioMaterias,
)

# Claves de la escala en la tabla `ajuste`, por proyecto. Mismo patron que
# `plan.minutos_por_dia`: tres valores sueltos no justifican una tabla.
_ESCALA_MIN = "notas.escala_min"
_ESCALA_MAX = "notas.escala_max"
_ESCALA_APROBADO = "notas.aprobado"


@dataclass(frozen=True, slots=True)
class DatosEvaluacion:
    """Lo que el formulario de una evaluacion devuelve. No persiste nada.

    Vive en el servicio y no en el dialogo porque es un parametro del servicio:
    ponerla en ``ui/`` obligaria al nucleo a importar de la interfaz, que el test
    de arquitectura prohibe. Mismo sitio que ``DatosProyecto``.
    """

    titulo: str
    fecha: date
    puntos_obtenidos: float | None   # None = declarada, todavia sin corregir
    puntos_posibles: float
    peso: float = 1.0
    hito_id: int | None = None
    nota: str | None = None
    materias: tuple[LineaEvaluacion, ...] = ()


@dataclass(frozen=True, slots=True)
class EscalaNotas:
    """En que unidades se leen las notas de un proyecto.

    La aplicacion guarda siempre puntos obtenidos sobre posibles, que es la
    forma en que vienen dados los examenes. La escala es **solo la manera de
    leerlos**: 0-5 con aprobado en 3, 0-100 con aprobado en 60, 0-10 con
    aprobado en 5. Por eso no hay ninguna tabla nueva ni ninguna conversion en
    la base: cambiar la escala no reescribe ni una nota.

    El valor por defecto —0 a 100, aprobado en 60— es el porcentaje de toda la
    vida, de modo que un proyecto que no la configure se ve exactamente igual
    que antes.
    """

    minimo: float = 0.0
    maximo: float = 100.0
    aprobado: float = 60.0

    @property
    def valida(self) -> bool:
        """Si la escala tiene sentido: rango no vacio y aprobado dentro."""
        return self.maximo > self.minimo and self.minimo <= self.aprobado <= self.maximo

    @property
    def recorrido(self) -> float:
        """Distancia entre el minimo y el maximo."""
        return self.maximo - self.minimo

    @property
    def fraccion_aprobado(self) -> float:
        """El aprobado expresado entre 0 y 1."""
        return self.a_fraccion(self.aprobado)

    def desde_fraccion(self, fraccion: float) -> float:
        """Convierte un acierto entre 0 y 1 en un valor de esta escala."""
        return self.minimo + fraccion * self.recorrido

    def a_fraccion(self, valor: float) -> float:
        """Convierte un valor de esta escala en un acierto entre 0 y 1."""
        if self.recorrido <= 0:
            return 0.0
        return (valor - self.minimo) / self.recorrido

    def formatear(self, fraccion: float) -> str:
        """El acierto escrito como se lee en esta escala.

        Con escalas cortas —0-5— hacen falta decimales: la diferencia entre un
        3,0 y un 3,4 es la que decide si se aprueba. Con 0-100 sobran.
        """
        valor = self.desde_fraccion(fraccion)
        if self.recorrido <= 10:
            return f"{valor:.2f}".rstrip("0").rstrip(".")
        return f"{valor:.0f}"


@dataclass(frozen=True, slots=True)
class Calculo:
    """La aritmetica de «como voy y que necesito».

    Todos los valores de nota van en **fraccion** (0 a 1). Traducirlos a la
    escala del proyecto es cosa de quien los pinta, con ``EscalaNotas``: mezclar
    las dos unidades dentro del calculo es la via mas rapida a un error que nadie
    ve hasta que suspende.
    """

    peso_evaluado: float = 0.0
    peso_pendiente: float = 0.0
    nota_acumulada: float = 0.0     # media de lo ya corregido
    aporte_actual: float = 0.0      # parte de la nota final ya asegurada
    fraccion_necesaria: float | None = None
    proyeccion: float = 0.0

    @property
    def peso_total(self) -> float:
        """Peso declarado entre lo corregido y lo pendiente."""
        return self.peso_evaluado + self.peso_pendiente

    @property
    def hay_pendiente(self) -> bool:
        """Si queda algo por hacer. Sin eso, no hay nada que calcular."""
        return self.peso_pendiente > 0

    @property
    def alcanzable(self) -> bool:
        """Si la nota necesaria cabe dentro de la escala.

        ``False`` significa que ni sacando el maximo en todo lo que queda se
        llega al aprobado. Es un dato duro y conviene decirlo, pero se dice una
        vez y sin dramatismo.
        """
        return self.fraccion_necesaria is None or self.fraccion_necesaria <= 1.0

    @property
    def asegurado(self) -> bool:
        """Si ya se aprueba pase lo que pase en lo que queda."""
        return self.fraccion_necesaria is not None and self.fraccion_necesaria <= 0.0


@dataclass(frozen=True, slots=True)
class NotaAsignatura:
    """Nota acumulada de una asignatura y de que evaluaciones sale."""

    materia_id: int
    nombre: str
    peso_materia: float = 0.0
    obtenidos: float = 0.0
    posibles: float = 0.0
    fraccion: float = 0.0
    evaluaciones: int = 0

    @property
    def porcentaje(self) -> int:
        """Nota de la asignatura en porcentaje entero."""
        return round(self.fraccion * 100)

    @property
    def medible(self) -> bool:
        """Si tiene alguna evaluacion: entonces cuenta para la nota del proyecto."""
        return self.evaluaciones > 0


@dataclass(frozen=True, slots=True)
class ResumenResultados:
    """Nota del proyecto con el desglose por asignatura y la lista de examenes."""

    evaluaciones: tuple[Evaluacion, ...] = ()      # de mas reciente a mas antigua
    asignaturas: tuple[NotaAsignatura, ...] = ()   # en el orden del temario

    @property
    def hay_evaluaciones(self) -> bool:
        """Si hay algo que mostrar. La vista lo usa para el estado vacio."""
        return bool(self.evaluaciones)

    @property
    def corregidas(self) -> tuple[Evaluacion, ...]:
        """Las que ya tienen nota. Son las unicas que entran en una media."""
        return tuple(e for e in self.evaluaciones if not e.pendiente)

    @property
    def pendientes(self) -> tuple[Evaluacion, ...]:
        """Las declaradas y todavia sin corregir, de la mas proxima en adelante."""
        return tuple(
            sorted((e for e in self.evaluaciones if e.pendiente), key=lambda e: e.fecha)
        )

    @property
    def porcentaje(self) -> int:
        """Nota global: media de las evaluaciones ponderada por su propio peso.

        Usa la nota global de cada evaluacion y no el desglose, para que una
        evaluacion sin desglose cuente igual que las demas. Si todos los pesos
        fueran cero cae a la media aritmetica: es preferible a devolver cero.

        Las pendientes no participan. Contarlas como un cero diria «vas fatal»
        cuando lo cierto es «aun no lo has hecho».
        """
        corregidas = self.corregidas
        if not corregidas:
            return 0
        peso = sum(e.peso for e in corregidas)
        if peso <= 0:
            return round(sum(e.fraccion for e in corregidas) * 100 / len(corregidas))
        return round(sum(e.peso * e.fraccion for e in corregidas) * 100 / peso)

    @property
    def hay_pesos(self) -> bool:
        """Si alguna asignatura evaluada tiene ``materia.peso``."""
        return self._peso_medible > 0

    @property
    def porcentaje_ponderado(self) -> int:
        """Nota del proyecto ponderando cada asignatura por ``materia.peso``.

        Sin pesos devuelve ``porcentaje``, para que quien lo pinte no tenga que
        preguntar antes. Mismo criterio que ``ResumenProgreso``.
        """
        if not self.hay_pesos:
            return self.porcentaje
        aportado = sum(
            a.peso_materia * a.fraccion for a in self.asignaturas if a.medible
        )
        return round(aportado * 100 / self._peso_medible)

    def cuota(self, asignatura: NotaAsignatura) -> float:
        """Peso de la asignatura como porcentaje del peso declarado."""
        declarado = sum(a.peso_materia for a in self.asignaturas)
        return asignatura.peso_materia * 100 / declarado if declarado else 0.0

    @property
    def pesadas_sin_evaluar(self) -> tuple[NotaAsignatura, ...]:
        """Asignaturas con peso pero sin ninguna nota todavia.

        Quedan fuera del calculo por la misma razon que en el progreso: sin dato
        no hay nada que medir, y contarlas como un cero fijaria un techo
        permanente a la nota del proyecto. La interfaz las avisa.
        """
        return tuple(
            a for a in self.asignaturas if a.peso_materia > 0 and not a.medible
        )

    @property
    def sin_desglose(self) -> tuple[Evaluacion, ...]:
        """Evaluaciones de las que solo se conoce la nota global.

        Cuentan para ``porcentaje`` pero no para ninguna asignatura, asi que
        tampoco para ``porcentaje_ponderado``. Callarselo haria que las dos
        cifras discreparan sin explicacion.
        """
        return tuple(e for e in self.corregidas if not e.materias)

    @property
    def _peso_medible(self) -> float:
        """Suma de los pesos de materia que participan: solo las evaluadas."""
        return sum(a.peso_materia for a in self.asignaturas if a.medible)


class ServicioResultados:
    """Registra evaluaciones y calcula la nota que sale de ellas."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._evaluaciones = RepositorioEvaluaciones(conexion)
        self._materias = RepositorioMaterias(conexion)
        self._ajustes = RepositorioAjustes(conexion)

    # -- Escala -----------------------------------------------------------------

    def escala(self, proyecto_id: int) -> EscalaNotas:
        """Escala de notas del proyecto, con los valores por defecto aplicados.

        Una escala guardada que no tenga sentido —maximo por debajo del minimo,
        aprobado fuera del rango— se descarta entera y se vuelve a la de por
        defecto. Corregir solo el campo malo daria una escala que nadie escribio.
        """
        propuesta = EscalaNotas(
            minimo=self._numero(_ESCALA_MIN, proyecto_id, 0.0),
            maximo=self._numero(_ESCALA_MAX, proyecto_id, 100.0),
            aprobado=self._numero(_ESCALA_APROBADO, proyecto_id, 60.0),
        )
        return propuesta if propuesta.valida else EscalaNotas()

    def fijar_escala(self, proyecto_id: int, escala: EscalaNotas) -> bool:
        """Guarda la escala. Devuelve ``False``, sin escribir, si no es valida."""
        if not escala.valida:
            return False
        self._ajustes.establecer(_ESCALA_MIN, repr(escala.minimo), proyecto_id)
        self._ajustes.establecer(_ESCALA_MAX, repr(escala.maximo), proyecto_id)
        self._ajustes.establecer(_ESCALA_APROBADO, repr(escala.aprobado), proyecto_id)
        return True

    def _numero(self, clave: str, proyecto_id: int, por_defecto: float) -> float:
        """Lee un ajuste numerico, tolerando que este ausente o corrupto."""
        bruto = self._ajustes.obtener(clave, proyecto_id)
        if not bruto:
            return por_defecto
        try:
            return float(bruto)
        except ValueError:
            return por_defecto

    # -- Calculadora ------------------------------------------------------------

    def calculo(self, proyecto_id: int) -> Calculo:
        """Como va el proyecto y que hace falta en lo que queda."""
        return calcular(self._evaluaciones.listar(proyecto_id), self.escala(proyecto_id))

    def simular(
        self, proyecto_id: int, supuestos: Mapping[int, float]
    ) -> Calculo:
        """«Y si saco un 3,5 en el final»: el mismo calculo con notas supuestas.

        ``supuestos`` va en fracciones (0 a 1), como todo el calculo. **No
        escribe nada**: lee las evaluaciones, sustituye en memoria y devuelve el
        resultado. Un escenario no puede modificar una nota real porque este
        metodo no tiene por donde hacerlo.
        """
        return calcular(
            self._evaluaciones.listar(proyecto_id), self.escala(proyecto_id), supuestos
        )

    def resumen(self, proyecto_id: int) -> ResumenResultados:
        """Nota global, por asignatura y lista de evaluaciones del proyecto."""
        evaluaciones = tuple(self._evaluaciones.listar(proyecto_id))
        lineas = self._evaluaciones.lineas_por_materia(proyecto_id)

        agrupadas: dict[int, list[LineaPesada]] = {}
        for linea in lineas:
            agrupadas.setdefault(linea.materia_id, []).append(linea)

        # Se recorre el temario y no las lineas para que las asignaturas salgan
        # en el orden del temario y para incluir las que tienen peso y ninguna
        # nota: son las que alimentan `pesadas_sin_evaluar`.
        asignaturas = tuple(
            _nota_de(materia, agrupadas.get(materia.id, []))
            for materia in self._materias.listar(proyecto_id)
        )
        return ResumenResultados(evaluaciones=evaluaciones, asignaturas=asignaturas)

    def evolucion(self, proyecto_id: int) -> tuple[tuple[date, int], ...]:
        """Porcentaje global de cada evaluacion, en orden cronologico.

        Es lo que pinta la curva: sirve para ver si se mejora, que es la unica
        pregunta interesante de un historial de simulacros.

        Las pendientes no salen: un punto a cero en un examen que aun no se ha
        hecho hundiria la curva y diria una mentira.
        """
        evaluaciones = [e for e in self._evaluaciones.listar(proyecto_id) if not e.pendiente]
        return tuple(
            (e.fecha, e.porcentaje) for e in sorted(evaluaciones, key=lambda x: x.fecha)
        )

    # -- Escritura --------------------------------------------------------------

    def registrar(self, proyecto_id: int, datos: DatosEvaluacion) -> Evaluacion:
        """Da de alta una evaluacion con su desglose.

        ``datos`` viene del dialogo, que no escribe nada. Aqui se filtra lo que
        el CHECK de SQLite no puede explicar bien: una materia de otro proyecto
        se descarta en vez de reventar con un fallo de clave foranea.
        """
        return self._evaluaciones.crear(
            proyecto_id,
            datos.titulo,
            datos.fecha,
            datos.puntos_obtenidos,
            datos.puntos_posibles,
            peso=datos.peso,
            hito_id=datos.hito_id,
            nota=datos.nota,
            materias=self._propias(proyecto_id, datos.materias),
        )

    def editar(self, evaluacion_id: int, datos: DatosEvaluacion) -> None:
        """Guarda los cambios de una evaluacion existente y rehace su desglose."""
        evaluacion = self._evaluaciones.obtener(evaluacion_id)
        if evaluacion is None:
            return

        evaluacion.titulo = datos.titulo
        evaluacion.fecha = datos.fecha
        evaluacion.puntos_obtenidos = datos.puntos_obtenidos
        evaluacion.puntos_posibles = datos.puntos_posibles
        evaluacion.peso = datos.peso
        evaluacion.hito_id = datos.hito_id
        evaluacion.nota = datos.nota

        self._evaluaciones.actualizar(evaluacion)
        self._evaluaciones.desglosar(
            evaluacion_id, self._propias(evaluacion.proyecto_id, datos.materias)
        )

    def eliminar(self, evaluacion_id: int) -> None:
        """Borra una evaluacion. El desglose se va con ella."""
        self._evaluaciones.eliminar(evaluacion_id)

    def materias(self, proyecto_id: int) -> list[Materia]:
        """Materias del proyecto, para poblar el desglose del dialogo."""
        return self._materias.listar(proyecto_id)

    def _propias(
        self, proyecto_id: int, lineas: Sequence[LineaEvaluacion]
    ) -> list[LineaEvaluacion]:
        """Descarta las lineas de materias que no son de este proyecto."""
        propias = {m.id for m in self._materias.listar(proyecto_id)}
        return [linea for linea in lineas if linea.materia_id in propias]


def calcular(
    evaluaciones: Sequence[Evaluacion],
    escala: EscalaNotas,
    supuestos: Mapping[int, float] | None = None,
) -> Calculo:
    """Nota acumulada, peso pendiente y nota necesaria para aprobar.

    Funcion **pura**: no toca la base de datos ni las evaluaciones que recibe.
    Es lo que permite que un escenario no pueda modificar una nota real ni por
    accidente, por mucho que se equivoque quien lo llame.

    ``supuestos`` asocia identificadores de evaluacion con fracciones (0 a 1)
    supuestas. Una evaluacion con supuesto se trata como corregida con esa nota,
    tenga o no la suya. Pasar ``None`` calcula la situacion real.

    Las evaluaciones de **peso cero** —los simulacros del CFA— siguen estando en
    la lista y en las medias que no ponderan, pero no aportan peso: no mueven la
    nota final porque no vale nada, que es justo lo que declara un peso de cero.

    La formula de la nota necesaria, con los pesos normalizados sobre el total
    declarado:

        necesaria = (aprobado * peso_total - aporte_actual) / peso_pendiente

    Si no queda peso pendiente devuelve ``None``: no hay ninguna nota que sacar.
    """
    supuestos = supuestos or {}

    corregidas: list[tuple[float, float]] = []   # (peso, fraccion)
    peso_pendiente = 0.0
    for evaluacion in evaluaciones:
        supuesta = supuestos.get(evaluacion.id)
        if supuesta is not None:
            corregidas.append((evaluacion.peso, max(0.0, min(1.0, supuesta))))
        elif evaluacion.pendiente:
            peso_pendiente += evaluacion.peso
        else:
            corregidas.append((evaluacion.peso, evaluacion.fraccion))

    peso_evaluado = sum(peso for peso, _ in corregidas)
    aporte = sum(peso * fraccion for peso, fraccion in corregidas)

    if peso_evaluado > 0:
        acumulada = aporte / peso_evaluado
    elif corregidas:
        # Todo con peso cero: la media aritmetica es mejor respuesta que un
        # cero, igual que en `_nota_de`. Un historial de simulacros sin pesos
        # tiene media, aunque no tenga nota final.
        acumulada = sum(fraccion for _, fraccion in corregidas) / len(corregidas)
    else:
        acumulada = 0.0

    peso_total = peso_evaluado + peso_pendiente
    if peso_pendiente > 0:
        necesaria = (escala.fraccion_aprobado * peso_total - aporte) / peso_pendiente
        proyeccion = (aporte + peso_pendiente * acumulada) / peso_total
    else:
        necesaria = None
        proyeccion = acumulada

    return Calculo(
        peso_evaluado=peso_evaluado,
        peso_pendiente=peso_pendiente,
        nota_acumulada=acumulada,
        aporte_actual=aporte,
        fraccion_necesaria=necesaria,
        proyeccion=proyeccion,
    )


def _nota_de(materia: Materia, lineas: Sequence[LineaPesada]) -> NotaAsignatura:
    """Nota acumulada de una asignatura a partir de sus lineas de desglose."""
    if not lineas:
        return NotaAsignatura(
            materia_id=materia.id, nombre=materia.nombre, peso_materia=materia.peso
        )

    peso = sum(linea.peso_evaluacion for linea in lineas)
    if peso > 0:
        fraccion = sum(linea.peso_evaluacion * linea.fraccion for linea in lineas) / peso
    else:
        # Todos los pesos a cero: la media aritmetica es mejor respuesta que un
        # cero, que se leeria como «lo hiciste fatal» en vez de «no ponderes».
        fraccion = sum(linea.fraccion for linea in lineas) / len(lineas)

    return NotaAsignatura(
        materia_id=materia.id,
        nombre=materia.nombre,
        peso_materia=materia.peso,
        obtenidos=sum(linea.puntos_obtenidos for linea in lineas),
        posibles=sum(linea.puntos_posibles for linea in lineas),
        fraccion=fraccion,
        evaluaciones=len(lineas),
    )
