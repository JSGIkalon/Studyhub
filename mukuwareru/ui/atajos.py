"""Catalogo de atajos de teclado.

Es a los atajos lo que ``SECCIONES`` a las vistas: **la unica declaracion**. Quien
crea el `QShortcut` pide aqui la combinacion, y la ayuda de Ajustes se pinta
recorriendo esta misma lista. Asi no puede pasar lo de siempre —cambiar una tecla
y dejar la documentacion mintiendo—, porque no hay dos sitios que cuadrar.

Anadir un atajo es anadir una linea aqui y una llamada a `secuencia()` donde toca.

Algunas entradas no tienen `tecla`: son teclas que no se enganchan con un
`QShortcut` sino dentro de un `eventFilter` o por el comportamiento normal de Qt
—las flechas del buscador, el Esc que cierra un dialogo—. Se declaran igual,
porque al usuario le da lo mismo como esten implementadas y el objeto de esta
lista es que sepa que existen.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QKeySequence

# Ambitos, en el orden en que se ensenan. Se nombran como el sitio donde el
# atajo funciona, no como el modulo que lo implementa.
GLOBAL = "En toda la aplicacion"
BUSCADOR = "En el buscador (Ctrl+K)"
LECTOR = "Leyendo un PDF"
POMODORO = "En el editor de bloques del Pomodoro"

_ORDEN_AMBITOS = (GLOBAL, BUSCADOR, LECTOR, POMODORO)


@dataclass(frozen=True, slots=True)
class Atajo:
    """Una combinacion de teclas y lo que hace."""

    clave: str
    ambito: str
    descripcion: str
    tecla: str | QKeySequence.StandardKey | None = None
    etiqueta: str = ""

    def secuencia(self) -> QKeySequence:
        """La combinacion, para pasarsela a ``QShortcut``."""
        if self.tecla is None:
            raise ValueError(f"El atajo «{self.clave}» no se engancha con QShortcut")
        return QKeySequence(self.tecla)

    def texto(self) -> str:
        """Como se escribe la combinacion en la ayuda.

        Con `tecla` se le pregunta a Qt en formato nativo, de modo que lo que se
        lee es literalmente lo que esta enganchado —incluidas las combinaciones
        estandar, que Qt resuelve segun el sistema—. `etiqueta` solo manda en las
        entradas que son solo documentacion.
        """
        if self.tecla is None:
            return self.etiqueta
        return self.secuencia().toString(QKeySequence.SequenceFormat.NativeText)


ATAJOS: tuple[Atajo, ...] = (
    Atajo("buscar", GLOBAL, "Abrir el buscador global", "Ctrl+K"),
    Atajo("barra", GLOBAL, "Mostrar u ocultar la barra lateral", "Ctrl+B"),
    Atajo("pomodoro", GLOBAL, "Iniciar o pausar el Pomodoro", "Ctrl+Space"),
    Atajo("nota_nueva", GLOBAL, "Nota nueva", "Ctrl+N"),
    # Se atiende en `keyPressEvent` de la ventana: nueve QShortcut para decir
    # una sola cosa llenarian la ayuda de filas iguales.
    Atajo("secciones", GLOBAL, "Ir a la seccion N de la barra lateral",
          etiqueta="Ctrl+1 … Ctrl+9"),

    Atajo("mover", BUSCADOR, "Moverse entre los resultados", etiqueta="↑  ↓"),
    Atajo("abrir", BUSCADOR, "Abrir el resultado elegido", etiqueta="Enter"),
    Atajo("cerrar_buscador", BUSCADOR, "Cerrar el buscador", etiqueta="Esc"),

    Atajo("buscar_pdf", LECTOR, "Buscar dentro del documento",
          QKeySequence.StandardKey.Find),
    Atajo("acercar", LECTOR, "Acercar", QKeySequence.StandardKey.ZoomIn),
    Atajo("alejar", LECTOR, "Alejar", QKeySequence.StandardKey.ZoomOut),
    Atajo("ajustar", LECTOR, "Ajustar la pagina al ancho", "Ctrl+0"),
    Atajo("nota", LECTOR, "Escribir una nota en un cuaderno", "Ctrl+M"),
    Atajo("copiar", LECTOR, "Copiar el texto seleccionado", "Ctrl+C"),
    Atajo("volver", LECTOR, "Volver a donde estabas", "Esc"),

    Atajo("cerrar_editor", POMODORO, "Cerrar el editor", etiqueta="Esc"),
)


def secuencia(clave: str) -> QKeySequence:
    """La combinacion declarada para ese atajo.

    Falla con `KeyError` si la clave no existe: un atajo que se engancha sin
    estar en el catalogo es justo lo que esta lista evita, y es mejor romper al
    arrancar que salir con un atajo fantasma que nadie documenta.
    """
    for atajo in ATAJOS:
        if atajo.clave == clave:
            return atajo.secuencia()
    raise KeyError(f"No hay ningun atajo declarado con la clave «{clave}»")


def por_ambito() -> list[tuple[str, list[Atajo]]]:
    """Los atajos agrupados, en el orden en que se ensenan en Ajustes."""
    return [
        (ambito, [a for a in ATAJOS if a.ambito == ambito])
        for ambito in _ORDEN_AMBITOS
    ]
