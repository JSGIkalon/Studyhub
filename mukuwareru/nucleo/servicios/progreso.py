"""Progreso del temario.

El progreso es manual y no tiene ninguna relacion con el tiempo estudiado: se
calcula solo a partir de los modulos marcados.

Se calcula de dos maneras a la vez:

* **Por modulos** — el de siempre: modulos hechos entre modulos totales. Trata
  igual una casilla de Ethics que una de Derivatives.
* **Ponderado** — media de los avances de cada asignatura pesada por
  ``materia.peso``. Responde a «cuanto del examen llevo», no a «cuantas casillas
  llevo».

La segunda solo existe si alguna materia tiene peso. Un proyecto sin pesos
—todos los que ya estaban— se comporta exactamente como antes.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from mukuwareru.nucleo.repositorios import RepositorioMaterias, RepositorioModulos

# Pesos del examen CFA Nivel I (curriculo 2026). El material oficial publica un
# rango por tema; aqui esta el punto medio de cada uno, reescalado para que la
# suma de exactamente 100. Los puntos medios crudos suman 102,5, y repartir ese
# exceso en proporcion deja a cada tema dentro de su rango oficial:
#
#     Ethics 15-20 -> 17,1   ·  Quant 6-9  -> 7,3   ·  Economics 6-9  -> 7,3
#     FSA 11-14    -> 12,2   ·  Corp 6-9   -> 7,3   ·  Equity 11-14   -> 12,2
#     Fixed Income 11-14 -> 12,2  ·  Derivatives 5-8 -> 6,3
#     Alternatives 7-10  -> 8,3   ·  Portfolio Mgmt 8-12 -> 9,8
#
# Que sumen 100 es cosmetico —los pesos se normalizan igualmente— pero hace que
# la columna de cuotas del dialogo se lea como los porcentajes del examen.
# Puntos porcentuales por debajo de su cuota a partir de los cuales una materia
# se considera desatendida. Ver `DesvioMateria.desatendida`.
_DESATENCION_PP = 5.0

PESOS_CFA_NIVEL_I: Mapping[str, float] = {
    "ethical and professional standards": 17.1,
    "quantitative methods": 7.3,
    "economics": 7.3,
    "financial statement analysis": 12.2,
    "corporate issuers": 7.3,
    "equity investments": 12.2,
    "fixed income": 12.2,
    "derivatives": 6.3,
    "alternative investments": 8.3,
    "portfolio management": 9.8,
}

# Como se llaman esas mismas asignaturas en el Excel y en el habla corriente. El
# temario importado dice «Ethics» o «FSA», no el titulo largo del curriculo.
_ALIAS_CFA: Mapping[str, str] = {
    "ethics": "ethical and professional standards",
    "ethical and professional standard": "ethical and professional standards",
    "quantitative method": "quantitative methods",
    "quants": "quantitative methods",
    "quant": "quantitative methods",
    "econ": "economics",
    "fsa": "financial statement analysis",
    "financial reporting and analysis": "financial statement analysis",
    "fra": "financial statement analysis",
    "corporate issuer": "corporate issuers",
    "corporate finance": "corporate issuers",
    "equity": "equity investments",
    "equities": "equity investments",
    "fixed income investments": "fixed income",
    "derivative": "derivatives",
    "alternatives": "alternative investments",
    "alternative investment": "alternative investments",
    "portfolio management and wealth planning": "portfolio management",
    "portfolio": "portfolio management",
    "pm": "portfolio management",
}


@dataclass(frozen=True, slots=True)
class ProgresoMateria:
    """Avance de una materia concreta."""

    materia_id: int
    nombre: str
    total: int
    completados: int
    peso: float = 0.0
    color: str | None = None

    @property
    def fraccion(self) -> float:
        """Avance entre 0 y 1, sin redondear. Es lo que entra en la ponderacion."""
        return self.completados / self.total if self.total else 0.0

    @property
    def porcentaje(self) -> int:
        """Porcentaje entero de modulos completados."""
        return round(self.fraccion * 100)


@dataclass(frozen=True, slots=True)
class DesvioMateria:
    """Horas dedicadas a una materia frente a las que le tocarian por su peso.

    ``real`` y ``objetivo`` son porcentajes sobre el mismo total, de modo que se
    leen uno contra otro directamente.
    """

    materia_id: int
    nombre: str
    segundos: int
    real: float       # % del tiempo clasificado que se lleva esta materia
    objetivo: float   # % que le corresponderia por su peso

    @property
    def desvio(self) -> float:
        """Puntos porcentuales de mas (positivo) o de menos (negativo)."""
        return self.real - self.objetivo

    @property
    def desatendida(self) -> bool:
        """Si recibe bastante menos atencion de la que su peso pide.

        El umbral son puntos porcentuales y no un ratio a proposito: con cuotas
        pequenas —Derivatives pesa un 6 %— un ratio relativo marcaria como
        desatendida cualquier variacion de media hora.
        """
        return self.desvio < -_DESATENCION_PP


@dataclass(frozen=True, slots=True)
class ResumenProgreso:
    """Avance global del proyecto, con el desglose por materia."""

    total: int
    completados: int
    materias: tuple[ProgresoMateria, ...]

    @property
    def pendientes(self) -> int:
        """Modulos que quedan por completar."""
        return self.total - self.completados

    @property
    def porcentaje(self) -> int:
        """Porcentaje entero de avance del proyecto, contando modulos."""
        return round(self.completados * 100 / self.total) if self.total else 0

    @property
    def hay_pesos(self) -> bool:
        """Si alguna materia con temario tiene peso: entonces hay ponderacion."""
        return self._peso_medible > 0

    @property
    def porcentaje_ponderado(self) -> int:
        """Avance ponderado por el peso de cada asignatura.

        Sin pesos devuelve el porcentaje por modulos, para que quien lo pinte no
        tenga que preguntar antes.
        """
        if not self.hay_pesos:
            return self.porcentaje
        aportado = sum(m.peso * m.fraccion for m in self.materias if m.total)
        return round(aportado * 100 / self._peso_medible)

    def cuota(self, materia: ProgresoMateria) -> float:
        """Peso de la materia como porcentaje del peso declarado en el proyecto."""
        declarado = sum(m.peso for m in self.materias)
        return materia.peso * 100 / declarado if declarado else 0.0

    @property
    def pesadas_sin_temario(self) -> tuple[ProgresoMateria, ...]:
        """Materias con peso pero sin ningun modulo.

        Quedan fuera del calculo: si no tienen modulos no hay nada que medir, y
        contarlas como un cero fijaria un techo permanente al porcentaje —un
        proyecto con todo hecho no llegaria nunca al 100 %—. La interfaz las
        avisa, porque un peso que no se usa es casi siempre un descuido.
        """
        return tuple(m for m in self.materias if m.peso > 0 and not m.total)

    def desvio_atencion(
        self, segundos_por_materia: Mapping[int, int]
    ) -> tuple[DesvioMateria, ...]:
        """Cruza las horas dedicadas con el peso de cada asignatura.

        El denominador de ``real`` es **solo el tiempo clasificado**, no el total
        estudiado. Incluir lo que no tiene materia haria que los porcentajes
        reales nunca sumaran 100 y que **todas** las materias salieran
        desatendidas a la vez: el resultado acusaria de no etiquetar las
        sesiones, no de desatender un tema.

        Solo salen las materias con peso: sin peso no hay objetivo con el que
        comparar. Devuelve la lista ordenada por deficit, porque lo primero que
        se lee tiene que ser lo que falta.
        """
        declarado = sum(m.peso for m in self.materias)
        if declarado <= 0:
            return ()

        # Se ignoran los identificadores desconocidos por si acaso: hoy no puede
        # haberlos (`sesion_materia` cae en cascada con la materia), pero
        # sumarlos al total y no poder pintarlos descuadraria los porcentajes.
        conocidas = {m.materia_id for m in self.materias}
        total = sum(
            segundos
            for materia_id, segundos in segundos_por_materia.items()
            if materia_id in conocidas
        )

        desvios = [
            DesvioMateria(
                materia_id=materia.materia_id,
                nombre=materia.nombre,
                segundos=segundos_por_materia.get(materia.materia_id, 0),
                real=(
                    segundos_por_materia.get(materia.materia_id, 0) * 100 / total
                    if total
                    else 0.0
                ),
                objetivo=self.cuota(materia),
            )
            for materia in self.materias
            if materia.peso > 0
        ]
        desvios.sort(key=lambda d: d.desvio)
        return tuple(desvios)

    @property
    def _peso_medible(self) -> float:
        """Suma de los pesos que participan: solo materias con modulos."""
        return sum(m.peso for m in self.materias if m.total)


class ServicioProgreso:
    """Calcula el avance del temario a partir de los modulos marcados."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._modulos = RepositorioModulos(conexion)
        self._materias = RepositorioMaterias(conexion)

    def resumen(self, proyecto_id: int) -> ResumenProgreso:
        """Avance global y por materia del proyecto."""
        conteos = self._modulos.conteo_por_materia(proyecto_id)
        materias = tuple(
            ProgresoMateria(
                materia_id=c.materia_id,
                nombre=c.nombre,
                total=c.total,
                completados=c.completados,
                peso=c.peso,
                color=c.color,
            )
            for c in conteos
        )
        total, completados = self._modulos.conteo_total(proyecto_id)
        return ResumenProgreso(total=total, completados=completados, materias=materias)

    def marcar(self, modulo_id: int, completado: bool) -> None:
        """Marca o desmarca un modulo."""
        self._modulos.marcar(modulo_id, completado)

    def marcar_materia(self, materia_id: int, completado: bool) -> int:
        """Marca o desmarca la materia entera. Devuelve cuantos modulos cambiaron."""
        return self._modulos.marcar_materia(materia_id, completado)

    # -- Pesos ------------------------------------------------------------------

    def fijar_pesos(self, proyecto_id: int, pesos: Mapping[int, float]) -> None:
        """Guarda el peso de varias materias del proyecto."""
        self._materias.fijar_pesos(proyecto_id, pesos)

    def limpiar_pesos(self, proyecto_id: int) -> None:
        """Quita todos los pesos: el proyecto vuelve al conteo de modulos."""
        self._materias.limpiar_pesos(proyecto_id)

    def pesos_cfa(self, proyecto_id: int) -> dict[int, float]:
        """Empareja las materias del proyecto con los pesos del CFA Nivel I.

        Devuelve el reparto **sin guardarlo**: la vista lo ofrece como propuesta
        editable, porque un temario propio puede llamar a las cosas de otra
        manera o no tener las diez asignaturas.
        """
        propuesta: dict[int, float] = {}
        for materia in self._materias.listar(proyecto_id):
            peso = PESOS_CFA_NIVEL_I.get(_clave(materia.nombre))
            if peso is not None:
                propuesta[materia.id] = peso
        return propuesta


def _clave(nombre: str) -> str:
    """Normaliza un nombre de asignatura para buscarlo en la tabla del CFA.

    Minusculas, sin acentos y sin signos: «Ethics», «ethics » y «Éthics» son la
    misma asignatura a la hora de proponer un peso.
    """
    sin_acentos = "".join(
        c
        for c in unicodedata.normalize("NFD", nombre.strip().lower())
        if unicodedata.category(c) != "Mn"
    )
    limpio = " ".join("".join(c if c.isalnum() else " " for c in sin_acentos).split())
    return _ALIAS_CFA.get(limpio, limpio)
