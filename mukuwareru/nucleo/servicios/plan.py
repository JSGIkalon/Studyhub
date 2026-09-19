"""Plan de estudio opcional y sugerencias de repaso.

**Todo esto es opcional.** Si no se configura nada, el calendario funciona igual
y en el Panel no aparece ninguna banda. Un plan que se impone solo se convierte
en una lista de reproches.

Dos piezas:

- ``diagnostico``: dado el proximo hito y los modulos que faltan, calcula el
  ritmo necesario y lo compara con el real. Es aritmetica sobre datos que ya
  existen, sin tablas nuevas.
- ``sugerencias``: repaso activo **calculado**, no un sistema de repeticion
  espaciada. Modulos completados hace tiempo sin sesion reciente, y materias con
  material escrito que no se ha vuelto a tocar. Sin colas ni estado que
  mantener, de modo que ignorarlas no rompe nada.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from mukuwareru.nucleo.repositorios import (
    RepositorioAjustes,
    RepositorioBloques,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioNotas,
    RepositorioSesiones,
)
from mukuwareru.nucleo.servicios.carga import ServicioCarga

_MINUTOS_POR_DIA = "plan.minutos_por_dia"
_ACTIVO = "plan.activo"

# Siete valores, de lunes a domingo. El reparto por defecto deja el domingo
# libre: un plan que no descansa nunca no se cumple.
_POR_DEFECTO: tuple[int, ...] = (60, 60, 60, 60, 60, 90, 0)
_MAXIMO_DIARIO = 16 * 60

# Ventanas del repaso activo, en dias.
_DIAS_PARA_REPASAR = 21
_DIAS_SIN_TOCAR = 30

# Hasta cuando se considera «cercana» una fecha limite de materia. Dos semanas:
# mas lejos no es una sugerencia para hoy, es ansiedad anticipada.
_DIAS_DE_HORIZONTE = 14


@dataclass(frozen=True, slots=True)
class PlanSemanal:
    """Minutos que se piensa dedicar cada dia de la semana."""

    minutos: tuple[int, ...] = _POR_DEFECTO
    activo: bool = False

    @property
    def minutos_semana(self) -> int:
        """Total semanal previsto."""
        return sum(self.minutos)

    @property
    def horas_semana(self) -> float:
        """El total semanal en horas, que es como se piensa."""
        return self.minutos_semana / 60

    def para(self, dia: date) -> int:
        """Minutos previstos para ese dia de la semana."""
        return self.minutos[dia.weekday()]


@dataclass(frozen=True, slots=True)
class Diagnostico:
    """Como va el proyecto frente a su proxima fecha clave."""

    pendientes: int = 0
    total: int = 0
    dias_restantes: int | None = None
    titulo_hito: str = ""
    modulos_por_semana: float = 0.0
    horas_por_semana_necesarias: float = 0.0
    horas_por_semana_reales: float = 0.0

    # Horas que quedan segun lo DECLARADO en las materias, o `None` si el
    # proyecto no ha estimado ninguna. Cuando existe, es lo que alimenta
    # `horas_por_semana_necesarias` en lugar de la extrapolacion del historial.
    horas_restantes_declaradas: float | None = None

    @property
    def declarado(self) -> bool:
        """Si el ritmo sale de horas estimadas y no de extrapolar el historial.

        La interfaz lo dice: «faltan 25 h» y «calculamos que faltan 25 h» no
        merecen la misma confianza.
        """
        return self.horas_restantes_declaradas is not None

    @property
    def hay_fecha(self) -> bool:
        """Sin fecha por delante no hay ritmo que calcular."""
        return self.dias_restantes is not None and self.pendientes > 0

    @property
    def al_dia(self) -> bool:
        """Si el ritmo real cubre el necesario."""
        return self.horas_por_semana_reales >= self.horas_por_semana_necesarias

    @property
    def desviacion_horas(self) -> float:
        """Horas semanales que faltan (positivo) o sobran (negativo)."""
        return self.horas_por_semana_necesarias - self.horas_por_semana_reales


@dataclass(frozen=True, slots=True)
class Sugerencia:
    """Algo que conviene repasar, y por que."""

    titulo: str
    motivo: str
    materia_id: int | None = None
    modulo_id: int | None = None


@dataclass(frozen=True, slots=True)
class PrevisionPlan:
    """Lo que se creara al generar el plan, antes de escribir nada."""

    bloques: list[tuple[date, int]] = field(default_factory=list)
    omitidos: int = 0

    @property
    def minutos(self) -> int:
        """Minutos totales que anadiria el plan."""
        return sum(minutos for _fecha, minutos in self.bloques)


class ServicioPlan:
    """Ritmo necesario, generacion de bloques y sugerencias de repaso."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._ajustes = RepositorioAjustes(conexion)
        self._modulos = RepositorioModulos(conexion)
        self._materias = RepositorioMaterias(conexion)
        self._sesiones = RepositorioSesiones(conexion)
        self._hitos = RepositorioHitos(conexion)
        self._bloques = RepositorioBloques(conexion)
        self._notas = RepositorioNotas(conexion)
        self._carga = ServicioCarga(conexion)

    # -- Preferencias, por proyecto -----------------------------------------

    def cargar(self, proyecto_id: int) -> PlanSemanal:
        """Plan semanal del proyecto, con los valores por defecto aplicados."""
        bruto = self._ajustes.obtener(_MINUTOS_POR_DIA, proyecto_id)
        minutos = _POR_DEFECTO
        if bruto:
            trozos = [t.strip() for t in bruto.split(",")]
            if len(trozos) == 7:
                try:
                    minutos = tuple(
                        max(0, min(_MAXIMO_DIARIO, int(t))) for t in trozos
                    )
                except ValueError:
                    minutos = _POR_DEFECTO
        return PlanSemanal(
            minutos=minutos,
            activo=self._ajustes.obtener(_ACTIVO, proyecto_id) == "1",
        )

    def guardar(self, proyecto_id: int, plan: PlanSemanal) -> None:
        """Persiste el plan, recortado a valores con sentido."""
        recortados = [max(0, min(_MAXIMO_DIARIO, m)) for m in plan.minutos]
        self._ajustes.establecer(
            _MINUTOS_POR_DIA, ",".join(str(m) for m in recortados), proyecto_id
        )
        self._ajustes.establecer(_ACTIVO, "1" if plan.activo else "0", proyecto_id)

    # -- Diagnostico ---------------------------------------------------------

    def diagnostico(self, proyecto_id: int, hoy: date | None = None) -> Diagnostico:
        """Ritmo necesario para llegar al proximo hito, frente al real."""
        dia = hoy or date.today()
        total, completados = self._modulos.conteo_total(proyecto_id)
        pendientes = total - completados

        declaradas = self._carga.horas_restantes(proyecto_id)

        proximos = self._hitos.proximos(proyecto_id, dia.isoformat(), limite=1)
        if not proximos:
            # Sin fecha por delante no hay ritmo que calcular, pero las horas
            # declaradas si se conocen y el Panel las ensena igualmente.
            return Diagnostico(
                pendientes=pendientes,
                total=total,
                horas_restantes_declaradas=declaradas,
            )

        hito = proximos[0]
        dias = max(0, hito.dias_restantes(dia))
        semanas = max(dias / 7, 1 / 7)  # nunca dividir por cero
        reales = self._horas_por_semana_reales(proyecto_id, dia)

        # Si el proyecto declara horas, se usan: son un dato y no una
        # extrapolacion. Si no, se estima el tiempo por modulo con el ritmo real
        # del proyecto; sin historial se usa una hora, que es un modulo tipico.
        # Esta bifurcacion es toda la integracion con la carga declarada: el
        # planificador no cambia en nada mas.
        if declaradas is not None:
            horas_pendientes = declaradas
        else:
            horas_pendientes = pendientes * self._horas_por_modulo(
                proyecto_id, completados
            )

        return Diagnostico(
            pendientes=pendientes,
            total=total,
            dias_restantes=dias,
            titulo_hito=hito.titulo,
            modulos_por_semana=pendientes / semanas,
            horas_por_semana_necesarias=horas_pendientes / semanas,
            horas_por_semana_reales=reales,
            horas_restantes_declaradas=declaradas,
        )

    def _horas_por_semana_reales(self, proyecto_id: int, hoy: date) -> float:
        """Ritmo de las ultimas cuatro semanas.

        Cuatro y no todo el historial: lo que importa es si el ritmo de ahora
        llega, no el de hace seis meses.
        """
        desde = hoy - timedelta(days=27)
        segundos = self._sesiones.segundos_trabajo(
            proyecto_id, desde=desde.isoformat(), hasta=hoy.isoformat()
        )
        return segundos / 3600 / 4

    def _horas_por_modulo(self, proyecto_id: int, completados: int) -> float:
        """Cuanto ha costado de media cada modulo ya hecho."""
        if completados <= 0:
            return 1.0
        segundos = self._sesiones.segundos_trabajo(proyecto_id)
        if segundos <= 0:
            return 1.0
        return segundos / 3600 / completados

    # -- Generacion ----------------------------------------------------------

    def prever(
        self, proyecto_id: int, desde: date, hasta: date
    ) -> PrevisionPlan:
        """Que bloques crearia el plan en ese rango, sin escribir nada.

        Vista previa antes de tocar la base, como hace el asistente de
        importacion: llenar el calendario de golpe sin ensenar que se va a
        crear es dificil de deshacer.
        """
        plan = self.cargar(proyecto_id)
        bloques: list[tuple[date, int]] = []
        omitidos = 0

        actual = desde
        while actual <= hasta:
            minutos = plan.para(actual)
            if minutos > 0:
                if self._bloques.existe_en(proyecto_id, actual, None):
                    omitidos += 1
                else:
                    bloques.append((actual, minutos))
            actual += timedelta(days=1)
        return PrevisionPlan(bloques=bloques, omitidos=omitidos)

    def generar(self, proyecto_id: int, prevision: PrevisionPlan) -> int:
        """Crea los bloques previstos y devuelve cuantos escribio.

        Recibe la prevision ya calculada para que lo que se guarda sea
        exactamente lo que se enseno.
        """
        for fecha, minutos in prevision.bloques:
            self._bloques.crear(
                proyecto_id,
                fecha,
                duracion_min=minutos,
                hora_inicio=None,
                titulo="Estudio planificado",
            )
        return len(prevision.bloques)

    # -- Repaso activo -------------------------------------------------------

    def sugerencias(
        self, proyecto_id: int, hoy: date | None = None, limite: int = 5
    ) -> list[Sugerencia]:
        """Que conviene repasar hoy, calculado sobre lo que ya hay.

        No es repeticion espaciada: no hay cola, ni intervalos, ni estado. Son
        dos preguntas sobre los datos existentes, de modo que ignorarlas durante
        un mes no deja nada roto.
        """
        dia = hoy or date.today()

        # 1. Modulos completados hace tiempo. Lo aprendido hace tres semanas es
        #    justo lo que esta a punto de olvidarse.
        limite_repaso = dia - timedelta(days=_DIAS_PARA_REPASAR)
        # Se guarda la antiguedad junto a cada sugerencia para poder ordenar por
        # ella. Ordenar por el texto del motivo —como se hacia— compara cadenas:
        # «hace 25 dias» va antes que «hace 9 dias» porque '2' < '9', y el corte
        # a `limite` se quedaba con las equivocadas.
        candidatas: list[tuple[int, Sugerencia]] = []
        for materia in self._materias.listar(proyecto_id):
            for modulo in self._modulos.listar(materia.id):
                if not modulo.completado or modulo.completado_en is None:
                    continue
                if modulo.completado_en.date() > limite_repaso:
                    continue
                dias = (dia - modulo.completado_en.date()).days
                candidatas.append((
                    dias,
                    Sugerencia(
                        titulo=modulo.nombre,
                        motivo=f"Completado hace {dias} dias · {materia.nombre}",
                        materia_id=materia.id,
                        modulo_id=modulo.id,
                    ),
                ))

        # Lo mas antiguo primero: es lo que peor se recuerda. El desempate por
        # titulo mantiene el orden estable entre dos modulos del mismo dia.
        candidatas.sort(key=lambda par: (-par[0], par[1].titulo))
        sugerencias = [sugerencia for _, sugerencia in candidatas[:limite]]

        # 2. Materias con fecha limite encima. Va antes que las notas olvidadas
        #    porque una fecha que se acerca es mas urgente que un repaso.
        if len(sugerencias) < limite:
            sugerencias += self._limites_cercanos(
                proyecto_id, dia, limite - len(sugerencias)
            )

        # 3. Material escrito que no se ha vuelto a abrir. Una nota que nadie
        #    relee es tiempo invertido que no rinde.
        if len(sugerencias) < limite:
            sugerencias += self._notas_olvidadas(
                proyecto_id, dia, limite - len(sugerencias)
            )
        return sugerencias

    def _limites_cercanos(
        self, proyecto_id: int, hoy: date, limite: int
    ) -> list[Sugerencia]:
        """Materias con fecha limite dentro del horizonte y horas por delante.

        Solo mira lo que el usuario ha declarado: sin fecha limite no aparece
        nadie, y el comportamiento de un proyecto que no usa esto es el de
        siempre. Sigue sin haber cola ni estado que mantener.
        """
        cercanas: list[Sugerencia] = []
        for carga in self._carga.urgentes(proyecto_id, hoy, limite=limite):
            dias = carga.dias_para_limite(hoy)
            if dias is None or dias > _DIAS_DE_HORIZONTE:
                continue
            if dias < 0:
                cuando = f"Fecha limite pasada hace {-dias} dias"
            elif dias == 0:
                cuando = "Fecha limite hoy"
            else:
                cuando = f"Fecha limite en {dias} dias"
            horas = carga.horas_restantes
            resto = f" · quedan {horas:.0f} h" if horas > 0 else ""
            cercanas.append(
                Sugerencia(
                    titulo=carga.nombre,
                    motivo=f"{cuando}{resto}",
                    materia_id=carga.materia_id,
                )
            )
        return cercanas

    def _notas_olvidadas(
        self, proyecto_id: int, hoy: date, limite: int
    ) -> list[Sugerencia]:
        """Notas sin tocar desde hace mas de un mes."""
        corte = hoy - timedelta(days=_DIAS_SIN_TOCAR)
        olvidadas: list[Sugerencia] = []
        for listada in self._notas.listar_del_proyecto(proyecto_id):
            actualizada = listada.nota.actualizado_en
            if actualizada is None or actualizada.date() > corte:
                continue
            dias = (hoy - actualizada.date()).days
            olvidadas.append(
                Sugerencia(
                    titulo=listada.nota.titulo or "Nota sin titulo",
                    motivo=f"Sin releer desde hace {dias} dias · {listada.seccion}",
                )
            )
            if len(olvidadas) == limite:
                break
        return olvidadas
