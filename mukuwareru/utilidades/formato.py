"""Formateo de valores para mostrar en la interfaz.

Vive en ``utilidades`` y no en ``ui`` porque no depende de Qt y se prueba
directamente con pytest.
"""

from __future__ import annotations

from datetime import date, datetime

_MESES = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)

_DIAS_SEMANA = (
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
)


def horas(segundos: int) -> str:
    """``9000`` -> ``'2.5 h'``. Por debajo de una hora usa minutos."""
    if segundos < 3600:
        return f"{segundos // 60} min"
    return f"{segundos / 3600:.1f} h".replace(".0 h", " h")


def duracion_reloj(segundos: int) -> str:
    """``1500`` -> ``'25:00'``; ``9045`` -> ``'2:30:45'``.

    Pasada la hora se muestra el campo de horas. Sin el, una sesion de trabajo
    indefinida —que no tiene fin previsto— llegaria a marcar ``150:45``, y un
    bloque de dos horas, ``120:00``.
    """
    segundos = max(0, segundos)
    horas_, resto = divmod(segundos, 3600)
    minutos, sobrantes = divmod(resto, 60)
    if horas_:
        return f"{horas_}:{minutos:02d}:{sobrantes:02d}"
    return f"{minutos:02d}:{sobrantes:02d}"


def tamano(bytes_: int) -> str:
    """``1536000`` -> ``'1.5 MB'``."""
    unidades = ("B", "KB", "MB", "GB")
    valor = float(bytes_)
    for unidad in unidades:
        if valor < 1024 or unidad == unidades[-1]:
            return f"{valor:.0f} {unidad}" if unidad == "B" else f"{valor:.1f} {unidad}"
        valor /= 1024
    return f"{valor:.1f} GB"


def fecha_corta(dia: date) -> str:
    """``date(2026, 11, 13)`` -> ``'13 nov 2026'``."""
    return f"{dia.day} {_MESES[dia.month - 1]} {dia.year}"


def fecha_larga(dia: date) -> str:
    """``date(2026, 11, 13)`` -> ``'viernes, 13 nov 2026'``.

    Para las cabeceras del calendario, donde saber el dia de la semana importa
    tanto como la fecha.
    """
    return f"{_DIAS_SEMANA[dia.weekday()]}, {fecha_corta(dia)}"


def dias_relativos(dias: int) -> str:
    """``3`` -> ``'en 3 dias'``, ``1`` -> ``'manana'``, ``0`` -> ``'hoy'``,
    ``-1`` -> ``'ayer'``, ``-2`` -> ``'hace 2 dias'``."""
    if dias > 1:
        return f"en {dias} dias"
    if dias == 1:
        return "manana"
    if dias == 0:
        return "hoy"
    if dias == -1:
        return "ayer"
    return f"hace {-dias} dias"


def apertura(momento: datetime | None, *, hoy: date | None = None) -> str:
    """Cuando se abrio algo por ultima vez: ``'hoy 10:30'``, ``'ayer'`` o la fecha.

    En minusculas, para ir dentro de una linea; quien la ponga sola la
    capitaliza. Antes el Panel y la Biblioteca tenian cada uno su copia, y una
    decia «Hoy» y la otra «hoy».
    """
    if momento is None:
        return "sin abrir"
    dias = ((hoy or date.today()) - momento.date()).days
    if dias == 0:
        return f"hoy {momento:%H:%M}"
    if dias == 1:
        return "ayer"
    return fecha_corta(momento.date())


def porcentaje(parte: int, total: int) -> int:
    """Porcentaje entero, tolerante a un total de cero."""
    if total <= 0:
        return 0
    return round(parte * 100 / total)
