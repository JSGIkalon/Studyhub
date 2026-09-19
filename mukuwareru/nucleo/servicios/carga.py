"""Carga de estudio declarada: horas, prioridad y fecha limite.

Responde a «cuanto me queda», que es una pregunta distinta de «cuanto llevo».
El progreso cuenta casillas; esto cuenta horas. Una asignatura puede tener el
80 % de los modulos marcados y ser la que mas horas tiene por delante, porque el
ultimo modulo era el gordo.

Las tres fuentes se combinan asi:

* **Horas estimadas** — la suma de las de los modulos si alguno la tiene; si no,
  la de la materia. El desglose manda porque es el dato mas fino, y quien se ha
  molestado en escribirlo no espera que se ignore.
* **Horas dedicadas** — de las sesiones ya registradas, sin tocar nada nuevo:
  ``RepositorioSesiones.segundos_por_materia`` ya reparte el tiempo de una sesion
  entre las materias con que se etiqueto.
* **Horas restantes** — estimadas menos dedicadas, salvo que haya sobrescritura
  manual. Esa resta se equivoca a menudo (se estudio sin cronometro, o el tema
  se entendio en la mitad de tiempo) y corregir el resultado no puede obligar a
  falsear ni la estimacion ni el historial.

Nada de esto es obligatorio. Un proyecto que no declare horas devuelve
``horas_estimadas=None`` en todas sus materias y el planificador sigue haciendo
lo de siempre.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from mukuwareru.nucleo.modelos.entidades import Prioridad
from mukuwareru.nucleo.repositorios import (
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioSesiones,
)


@dataclass(frozen=True, slots=True)
class CargaMateria:
    """Lo que queda por hacer en una materia, en horas."""

    materia_id: int
    nombre: str
    prioridad: Prioridad = Prioridad.MEDIA
    fecha_limite: date | None = None
    horas_estimadas: float | None = None
    horas_dedicadas: float = 0.0
    horas_restantes_manual: float | None = None
    total_modulos: int = 0
    completados: int = 0
    desglosada: bool = False   # la estimacion sale de los modulos, no de la materia

    @property
    def estimada(self) -> bool:
        """Si tiene horas declaradas. Sin ellas no hay nada que repartir."""
        return self.horas_estimadas is not None

    @property
    def horas_restantes(self) -> float:
        """Horas que faltan. La sobrescritura manual manda sobre el calculo.

        Nunca negativa: haber dedicado mas horas de las estimadas significa que
        la estimacion se quedo corta, no que sobren horas.
        """
        if self.horas_restantes_manual is not None:
            return max(0.0, self.horas_restantes_manual)
        if self.horas_estimadas is None:
            return 0.0
        return max(0.0, self.horas_estimadas - self.horas_dedicadas)

    @property
    def sobrescrita(self) -> bool:
        """Si las horas restantes las fijo el usuario a mano."""
        return self.horas_restantes_manual is not None

    @property
    def fraccion(self) -> float:
        """Avance por modulos, entre 0 y 1. El mismo criterio que el progreso."""
        return self.completados / self.total_modulos if self.total_modulos else 0.0

    def dias_para_limite(self, hoy: date) -> int | None:
        """Dias que faltan para la fecha limite. Negativo si ya paso."""
        if self.fecha_limite is None:
            return None
        return (self.fecha_limite - hoy).days

    def urgencia(self, hoy: date) -> tuple[int, float]:
        """Clave de ordenacion: primero lo mas urgente.

        Devuelve ``(dias_hasta_el_limite, -prioridad)``. Sin fecha limite se usa
        un horizonte muy lejano, de modo que una materia con fecha siempre va
        delante de una sin fecha, y entre dos sin fecha decide la prioridad.

        Es deliberadamente simple: dos numeros que se leen. Un scoring con pesos
        ajustables convertiria «que estudio ahora» en una hoja de calculo.
        """
        dias = self.dias_para_limite(hoy)
        return (dias if dias is not None else 10_000, -float(self.prioridad))


class ServicioCarga:
    """Cruza horas declaradas, sesiones registradas y progreso por materia."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._materias = RepositorioMaterias(conexion)
        self._modulos = RepositorioModulos(conexion)
        self._sesiones = RepositorioSesiones(conexion)

    def resumen(self, proyecto_id: int) -> list[CargaMateria]:
        """Carga de cada materia del proyecto, en el orden del temario."""
        horas_modulos = self._modulos.horas_por_materia(proyecto_id)
        segundos = self._sesiones.segundos_por_materia(proyecto_id)
        conteos = {
            c.materia_id: (c.total, c.completados)
            for c in self._modulos.conteo_por_materia(proyecto_id)
        }

        cargas: list[CargaMateria] = []
        for materia in self._materias.listar(proyecto_id):
            total, completados = conteos.get(materia.id, (0, 0))

            # El desglose por modulos manda; y de el se toma lo que queda
            # PENDIENTE, no el total, porque los modulos ya marcados estan hechos
            # aunque no se cronometraran. Sin desglose se cae a la estimacion de
            # la materia menos el tiempo dedicado.
            desglose = horas_modulos.get(materia.id)
            dedicadas = segundos.get(materia.id, 0) / 3600

            if desglose is not None:
                estimadas: float | None = desglose[0]
                # Se finge «dedicadas» lo ya completado para que la resta de
                # `horas_restantes` de exactamente las horas pendientes del
                # desglose, sin duplicar la formula en dos sitios.
                dedicadas_efectivas = desglose[0] - desglose[1]
                desglosada = True
            else:
                estimadas = materia.horas_estimadas
                dedicadas_efectivas = dedicadas
                desglosada = False

            cargas.append(
                CargaMateria(
                    materia_id=materia.id,
                    nombre=materia.nombre,
                    prioridad=materia.prioridad,
                    fecha_limite=materia.fecha_limite,
                    horas_estimadas=estimadas,
                    horas_dedicadas=dedicadas_efectivas,
                    horas_restantes_manual=materia.horas_restantes_manual,
                    total_modulos=total,
                    completados=completados,
                    desglosada=desglosada,
                )
            )
        return cargas

    def horas_restantes(self, proyecto_id: int) -> float | None:
        """Horas declaradas que quedan en todo el proyecto.

        ``None`` si ninguna materia tiene estimacion: entonces no hay dato y
        quien pregunte debe seguir extrapolando del historial, como siempre.
        """
        cargas = self.resumen(proyecto_id)
        estimadas = [c for c in cargas if c.estimada or c.sobrescrita]
        if not estimadas:
            return None
        return sum(c.horas_restantes for c in estimadas)

    def urgentes(
        self, proyecto_id: int, hoy: date | None = None, limite: int = 5
    ) -> list[CargaMateria]:
        """Materias con horas pendientes, de la mas urgente a la menos.

        Solo salen las que tienen algo que hacer: una materia acabada no es
        urgente por mucha prioridad que declare.
        """
        dia = hoy or date.today()
        pendientes = [
            c
            for c in self.resumen(proyecto_id)
            if c.horas_restantes > 0 or c.completados < c.total_modulos
        ]
        pendientes.sort(key=lambda c: c.urgencia(dia))
        return pendientes[:limite]

    # -- Escritura ---------------------------------------------------------

    def fijar(
        self,
        materia_id: int,
        *,
        horas_estimadas: float | None,
        horas_restantes_manual: float | None,
        prioridad: Prioridad,
        fecha_limite: date | None,
    ) -> None:
        """Guarda la carga declarada de una materia."""
        self._materias.fijar_carga(
            materia_id,
            horas_estimadas=horas_estimadas,
            horas_restantes_manual=horas_restantes_manual,
            prioridad=prioridad,
            fecha_limite=fecha_limite,
        )

    def fijar_horas_modulo(self, modulo_id: int, horas: float | None) -> None:
        """Estimacion de horas de un modulo concreto."""
        self._modulos.fijar_horas(modulo_id, horas)
