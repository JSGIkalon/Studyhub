"""Entidades del dominio.

Dataclasses puras: sin Qt, sin SQL, sin comportamiento de persistencia. Son el
lenguaje comun entre repositorios, servicios e interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum, StrEnum


class TipoSesion(StrEnum):
    """Fase del ciclo Pomodoro a la que corresponde una sesion."""

    TRABAJO = "trabajo"
    DESCANSO_CORTO = "descanso_corto"
    DESCANSO_LARGO = "descanso_largo"


class OrigenSesion(StrEnum):
    """De donde salio una sesion registrada."""

    POMODORO = "pomodoro"
    MANUAL = "manual"
    IMPORTADA = "importada"


class TipoAnotacion(StrEnum):
    """Las tres formas que adopta un ancla dentro de un PDF."""

    MARCADOR = "marcador"
    NOTA = "nota"
    RESALTADO = "resaltado"


class TipoHito(StrEnum):
    """Que clase de fecha marca un hito."""

    EXAMEN = "examen"
    ENTREGA = "entrega"
    HITO = "hito"

    @property
    def etiqueta(self) -> str:
        """Como se llama en la interfaz."""
        return {"examen": "Examen", "entrega": "Entrega", "hito": "Hito"}[self.value]


class Prioridad(IntEnum):
    """Urgencia declarada de una materia.

    Entero y no texto porque lo unico que se le pide es ordenar, y porque asi
    ``MEDIA`` es el valor por defecto de la columna sin ninguna conversion. Son
    cuatro niveles fijos a proposito: un scoring configurable convertiria una
    decision de medio segundo en un formulario.
    """

    BAJA = 0
    MEDIA = 1
    ALTA = 2
    CRITICA = 3

    @property
    def etiqueta(self) -> str:
        """Como se llama en la interfaz."""
        return ("Baja", "Media", "Alta", "Critica")[self.value]


class DestinoVinculo(StrEnum):
    """A que apunta el vinculo de una nota."""

    MATERIA = "materia"
    MODULO = "modulo"
    DOCUMENTO = "documento"
    ANOTACION = "anotacion"


@dataclass(slots=True)
class Proyecto:
    """Un ambito de estudio independiente (CFA Level I, MSc, ...)."""

    id: int
    nombre: str
    icono: str = "libro"
    color: str = "#E5484D"
    fecha_objetivo: date | None = None
    ruta_biblioteca: str | None = None
    orden: int = 0
    archivado: bool = False
    creado_en: datetime | None = None

    def dias_restantes(self, hoy: date) -> int | None:
        """Dias que faltan para la fecha objetivo, o ``None`` si no hay."""
        if self.fecha_objetivo is None:
            return None
        return (self.fecha_objetivo - hoy).days


@dataclass(slots=True)
class Materia:
    """Agrupacion de modulos dentro de un proyecto (Ethics, Fixed Income...).

    ``peso`` es un numero relativo, no un porcentaje: se normaliza dividiendo
    entre la suma del proyecto. Cero significa «sin peso».

    Las horas, la prioridad y la fecha limite son la carga declarada: lo que el
    planificador usa cuando existe. Todo lo que puede faltar es ``None``, y un
    proyecto que no rellene nada se planifica igual que antes de la version 1.1.
    """

    id: int
    proyecto_id: int
    nombre: str
    orden: int = 0
    color: str | None = None
    peso: float = 0.0
    horas_estimadas: float | None = None
    horas_restantes_manual: float | None = None
    prioridad: Prioridad = Prioridad.MEDIA
    fecha_limite: date | None = None

    def dias_para_limite(self, hoy: date) -> int | None:
        """Dias que faltan para la fecha limite, o ``None`` si no hay."""
        if self.fecha_limite is None:
            return None
        return (self.fecha_limite - hoy).days


@dataclass(slots=True)
class Modulo:
    """Unidad minima de progreso. Se marca completa a mano.

    ``horas_estimadas`` es opcional. Si los modulos de una materia la traen, su
    suma manda sobre la estimacion de la materia: es un dato mas fino.
    """

    id: int
    materia_id: int
    nombre: str
    orden: int = 0
    completado: bool = False
    completado_en: datetime | None = None
    horas_estimadas: float | None = None


@dataclass(frozen=True, slots=True)
class LineaEvaluacion:
    """Puntuacion de una asignatura dentro de una evaluacion.

    Es el desglose opcional. ``puntos_posibles`` es siempre mayor que cero: lo
    garantiza un CHECK en la base de datos.
    """

    materia_id: int
    puntos_obtenidos: float
    puntos_posibles: float

    @property
    def fraccion(self) -> float:
        """Acierto entre 0 y 1, sin redondear. Es lo que entra en la ponderacion."""
        return self.puntos_obtenidos / self.puntos_posibles

    @property
    def porcentaje(self) -> int:
        """Acierto en porcentaje entero, para pintarlo."""
        return round(self.fraccion * 100)


@dataclass(slots=True)
class Evaluacion:
    """Un examen corregido: simulacro, parcial, final, quiz o certificacion.

    La escala es la del examen, no una escala interna: ``38`` sobre ``50`` se
    guarda tal cual. ``peso`` es relativo (mismo criterio que ``Materia.peso``) y
    decide cuanto manda esta evaluacion en la nota de sus asignaturas.

    ``materias`` es el desglose y puede ir vacio: entonces solo se conoce la nota
    global. No se exige que las lineas sumen esa nota global.

    ``puntos_obtenidos`` en ``None`` significa **pendiente**: el examen esta
    declarado —se conocen su peso y su fecha— pero todavia no tiene nota. Es lo
    que permite preguntar «que necesito en el final». Una pendiente no entra en
    ninguna media; solo aporta su peso al que queda por evaluar.
    """

    id: int
    proyecto_id: int
    titulo: str
    fecha: date
    puntos_obtenidos: float | None
    puntos_posibles: float
    peso: float = 1.0
    hito_id: int | None = None
    nota: str | None = None
    creado_en: datetime | None = None
    materias: list[LineaEvaluacion] = field(default_factory=list)

    @property
    def pendiente(self) -> bool:
        """Si esta declarada pero todavia sin corregir."""
        return self.puntos_obtenidos is None

    @property
    def fraccion(self) -> float:
        """Acierto global entre 0 y 1. Cero mientras este pendiente.

        Devuelve cero y no lanza para que pintar una lista mixta no obligue a
        preguntar antes en cada fila; quien calcula medias filtra por
        ``pendiente``, que es la pregunta correcta.
        """
        if self.puntos_obtenidos is None:
            return 0.0
        return self.puntos_obtenidos / self.puntos_posibles

    @property
    def porcentaje(self) -> int:
        """Acierto global en porcentaje entero."""
        return round(self.fraccion * 100)

    @property
    def cuadra(self) -> bool:
        """Si el desglose suma la nota global, con una decima de tolerancia.

        Sin desglose devuelve ``True``: no hay nada que pueda discrepar. Una
        pendiente tambien: no hay nota global contra la que comparar. La
        tolerancia existe porque los simulacros redondean por tema.
        """
        if not self.materias or self.puntos_obtenidos is None:
            return True
        return (
            abs(sum(linea.puntos_obtenidos for linea in self.materias)
                - self.puntos_obtenidos) <= 0.1
            and abs(sum(linea.puntos_posibles for linea in self.materias)
                    - self.puntos_posibles) <= 0.1
        )


@dataclass(slots=True)
class Documento:
    """Un PDF descubierto en la biblioteca del proyecto."""

    id: int
    proyecto_id: int
    ruta_relativa: str
    nombre: str
    huella: str
    paginas: int | None = None
    bytes: int = 0
    pagina_actual: int = 0
    zoom: float = 1.0
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    abierto_en: datetime | None = None
    agregado_en: datetime | None = None


@dataclass(slots=True)
class Sesion:
    """Un bloque de tiempo de estudio registrado."""

    id: int
    proyecto_id: int
    tipo: TipoSesion
    origen: OrigenSesion
    inicio: datetime
    fin: datetime | None = None
    duracion_seg: int = 0
    fecha_local: str = ""
    completada: bool = False
    materias: list[int] = field(default_factory=list)


@dataclass(slots=True)
class Anotacion:
    """Marcador, nota o resaltado anclado a una pagina de un PDF."""

    id: int
    documento_id: int
    tipo: TipoAnotacion
    pagina: int
    rects: list[tuple[float, float, float, float]] = field(default_factory=list)
    texto_seleccionado: str | None = None
    comentario: str | None = None
    color: str = "#F5A524"
    creado_en: datetime | None = None


@dataclass(slots=True)
class Hito:
    """Una fecha con nombre dentro de un proyecto: examen, entrega o meta."""

    id: int
    proyecto_id: int
    titulo: str
    fecha: date
    tipo: TipoHito = TipoHito.HITO
    hora: str | None = None          # 'HH:MM' local
    nota: str | None = None
    color: str | None = None
    principal: bool = False
    completado: bool = False
    completado_en: datetime | None = None
    creado_en: datetime | None = None

    def dias_restantes(self, hoy: date) -> int:
        """Dias que faltan. Negativo si la fecha ya paso."""
        return (self.fecha - hoy).days


@dataclass(slots=True)
class BloquePlan:
    """Un bloque de estudio planeado de antemano.

    ``hora_inicio`` en ``None`` significa «ese dia, sin hora fijada»: el
    cumplimiento se calcula distinto en ese caso (ver ``repartir_cumplimiento``).
    """

    id: int
    proyecto_id: int
    fecha: date
    duracion_min: int = 25
    hora_inicio: str | None = None   # 'HH:MM' local
    titulo: str = ""
    nota: str | None = None
    creado_en: datetime | None = None
    materias: list[int] = field(default_factory=list)

    @property
    def duracion_seg(self) -> int:
        """Duracion prevista en segundos, para comparar con las sesiones."""
        return self.duracion_min * 60


@dataclass(slots=True)
class Cuaderno:
    """Contenedor de secciones dentro de un proyecto, al estilo OneNote."""

    id: int
    proyecto_id: int
    nombre: str
    color: str | None = None
    orden: int = 0
    creado_en: datetime | None = None


@dataclass(slots=True)
class Seccion:
    """Division de un cuaderno. Todo cuaderno tiene al menos una."""

    id: int
    cuaderno_id: int
    nombre: str
    color: str | None = None
    orden: int = 0
    creado_en: datetime | None = None


@dataclass(slots=True)
class Etiqueta:
    """Clasificacion transversal de notas dentro de un proyecto."""

    id: int
    proyecto_id: int
    nombre: str
    color: str | None = None


@dataclass(slots=True)
class Vinculo:
    """Enlace de una nota a una materia, un modulo, un PDF o una anotacion.

    Exactamente uno de los cuatro identificadores esta relleno; lo garantiza un
    CHECK en la base de datos. ``pagina`` solo acompana a ``documento_id``, y
    ``None`` ahi significa «el documento entero».
    """

    id: int
    nota_id: int
    materia_id: int | None = None
    modulo_id: int | None = None
    documento_id: int | None = None
    anotacion_id: int | None = None
    pagina: int | None = None
    creado_en: datetime | None = None

    @property
    def destino(self) -> DestinoVinculo:
        """Que clase de objeto senala este vinculo."""
        if self.materia_id is not None:
            return DestinoVinculo.MATERIA
        if self.modulo_id is not None:
            return DestinoVinculo.MODULO
        if self.documento_id is not None:
            return DestinoVinculo.DOCUMENTO
        if self.anotacion_id is not None:
            return DestinoVinculo.ANOTACION
        # Imposible con el CHECK puesto, pero no puede ser un `assert`: con las
        # optimizaciones activadas desapareceria y el retorno dejaria de ser puro.
        raise ValueError(f"Vinculo {self.id} no apunta a nada")

    @property
    def objeto_id(self) -> int:
        """Identificador del objeto al que apunta, sea del tipo que sea."""
        for valor in (self.materia_id, self.modulo_id, self.documento_id, self.anotacion_id):
            if valor is not None:
                return valor
        raise ValueError(f"Vinculo {self.id} no apunta a nada")


class DestinoNodo(StrEnum):
    """A que clase de objeto apunta un nodo del grafo."""

    MATERIA = "materia"
    MODULO = "modulo"
    HITO = "hito"
    EVALUACION = "evaluacion"

    @property
    def etiqueta(self) -> str:
        """Como se llama en la interfaz."""
        return {
            "materia": "Materia",
            "modulo": "Modulo",
            "hito": "Hito",
            "evaluacion": "Evaluacion",
        }[self.value]


class EstadoNodo(StrEnum):
    """Situacion de un nodo del grafo. Siempre derivada; nunca se guarda."""

    BLOQUEADO = "bloqueado"
    DISPONIBLE = "disponible"
    EN_CURSO = "en_curso"
    COMPLETADO = "completado"

    @property
    def etiqueta(self) -> str:
        """Como se llama en la interfaz."""
        return {
            "bloqueado": "Bloqueado",
            "disponible": "Disponible",
            "en_curso": "En curso",
            "completado": "Completado",
        }[self.value]


@dataclass(slots=True)
class NodoGrafo:
    """Referencia a una entidad existente mas su posicion en el lienzo.

    Exactamente uno de los cuatro identificadores esta relleno; lo garantiza un
    CHECK en la base de datos, igual que en ``Vinculo``.

    No guarda nombre, color ni progreso: todo eso se lee de la entidad a la que
    apunta cada vez que se pinta. ``etiqueta`` es la unica excepcion y es
    opcional: un alias para este grafo, no una copia del nombre.
    """

    id: int
    proyecto_id: int
    x: float = 0.0
    y: float = 0.0
    materia_id: int | None = None
    modulo_id: int | None = None
    hito_id: int | None = None
    evaluacion_id: int | None = None
    etiqueta: str | None = None
    nota: str | None = None
    creado_en: datetime | None = None

    @property
    def destino(self) -> DestinoNodo:
        """Que clase de objeto representa este nodo."""
        if self.materia_id is not None:
            return DestinoNodo.MATERIA
        if self.modulo_id is not None:
            return DestinoNodo.MODULO
        if self.hito_id is not None:
            return DestinoNodo.HITO
        if self.evaluacion_id is not None:
            return DestinoNodo.EVALUACION
        raise ValueError(f"Nodo {self.id} no apunta a nada")

    @property
    def objeto_id(self) -> int:
        """Identificador de la entidad representada, sea del tipo que sea."""
        for valor in (
            self.materia_id, self.modulo_id, self.hito_id, self.evaluacion_id
        ):
            if valor is not None:
                return valor
        raise ValueError(f"Nodo {self.id} no apunta a nada")


@dataclass(frozen=True, slots=True)
class AristaGrafo:
    """Un prerrequisito: ``origen`` hace falta para ``destino``.

    ``grupo`` codifica el O: dentro del mismo grupo las aristas son
    alternativas; entre grupos son todas obligatorias. Ver la migracion 007.
    """

    destino: int
    origen: int
    grupo: int = 1
    creado_en: datetime | None = None


@dataclass(slots=True)
class Nota:
    """Nota suelta: no depende de ningun PDF ni de ninguna pagina.

    ``cuerpo`` es el HTML autocontenido del editor (imagenes en base64) y
    ``cuerpo_plano`` su version buscable, derivada en el repositorio.
    """

    id: int
    seccion_id: int
    titulo: str = ""
    cuerpo: str = ""
    cuerpo_plano: str = ""
    orden: int = 0
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None
    etiquetas: list[int] = field(default_factory=list)
    vinculos: list[Vinculo] = field(default_factory=list)
