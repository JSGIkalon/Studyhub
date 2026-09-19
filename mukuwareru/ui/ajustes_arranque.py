"""Lectura y escritura de ``datos/ajustes.json``.

Aqui vive lo que es geometria de ventanas y no preferencia del usuario: el
tamano de la ventana, donde quedo el reloj flotante y como estaba repartido el
lector. Va en un JSON y no en la base de datos porque parte de esto se necesita
antes de abrirla, y porque perderlo no rompe nada.

Toda escritura es tolerante a fallos: si el archivo esta corrupto o el disco no
deja escribir, la aplicacion sigue con los valores por defecto. Nunca se levanta
una excepcion desde aqui.
"""

from __future__ import annotations

import json
from typing import Any

from mukuwareru.utilidades import rutas
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)


def leer() -> dict[str, Any]:
    """Todo el contenido del archivo, o un diccionario vacio."""
    ruta = rutas.ruta_ajustes_arranque()
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _log.warning("No se pudieron leer los ajustes de arranque: %s", error)
        return {}
    return datos if isinstance(datos, dict) else {}


def obtener_valor(clave: str, por_defecto: Any = None) -> Any:
    """Un unico valor del archivo."""
    return leer().get(clave, por_defecto)


def guardar(clave: str, valor: Any) -> None:
    """Escribe una clave conservando el resto del archivo.

    Se relee antes de escribir a proposito: la geometria de la ventana y la
    posicion del reloj se guardan en momentos distintos, y escribir solo lo
    propio borraria lo del otro.
    """
    datos = leer()
    datos[clave] = valor
    try:
        rutas.ruta_ajustes_arranque().write_text(
            json.dumps(datos, indent=2), encoding="utf-8"
        )
    except OSError as error:
        _log.warning("No se pudieron guardar los ajustes de arranque: %s", error)
