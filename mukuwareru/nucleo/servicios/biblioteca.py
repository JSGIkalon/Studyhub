"""Descubrimiento automatico de los PDFs de un proyecto.

No hay importacion manual: se deja el archivo en la carpeta y aparece. El
escaneo reconcilia lo que hay en disco con lo que hay en la base de datos.

Reconciliar por **huella** y no solo por ruta es lo que permite renombrar o
reordenar los PDFs en carpetas sin perder la posicion de lectura ni las
anotaciones.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from mukuwareru.nucleo.modelos.entidades import Documento, Proyecto
from mukuwareru.nucleo.repositorios import RepositorioDocumentos
from mukuwareru.nucleo.repositorios.base import transaccion
from mukuwareru.utilidades import huella as huellas
from mukuwareru.utilidades import rutas
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoEscaneo:
    """Que cambio en la biblioteca tras reconciliar disco y base de datos."""

    nuevos: int = 0
    movidos: int = 0
    modificados: int = 0
    eliminados: int = 0
    total: int = 0

    @property
    def hubo_cambios(self) -> bool:
        """Si algo cambio, las vistas deben recargarse."""
        return bool(self.nuevos or self.movidos or self.modificados or self.eliminados)


def ruta_biblioteca(proyecto: Proyecto) -> Path:
    """Carpeta de PDFs del proyecto.

    La configurada en Ajustes, o ``Library/<nombre del proyecto>`` por defecto.
    """
    if proyecto.ruta_biblioteca:
        return Path(proyecto.ruta_biblioteca)
    return rutas.carpeta_biblioteca() / proyecto.nombre


class ServicioBiblioteca:
    """Mantiene la tabla ``documento`` al dia con el contenido de la carpeta."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._documentos = RepositorioDocumentos(conexion)
        self._cx = conexion

    def escanear(self, proyecto: Proyecto) -> ResultadoEscaneo:
        """Reconcilia la carpeta del proyecto con la base de datos.

        Crea la carpeta si no existe: es mas util encontrarla vacia y saber
        donde dejar los PDFs que recibir un error.
        """
        carpeta = ruta_biblioteca(proyecto)
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            en_disco = sorted(p for p in carpeta.rglob("*.pdf") if p.is_file())
        except OSError as error:
            _log.warning("No se pudo leer la biblioteca %s: %s", carpeta, error)
            return ResultadoEscaneo(total=self._documentos.contar(proyecto.id))

        registrados = {d.ruta_relativa: d for d in self._documentos.listar(proyecto.id)}
        vistos: set[str] = set()
        nuevos = movidos = modificados = 0

        with transaccion(self._cx):
            for archivo in en_disco:
                relativa = archivo.relative_to(carpeta).as_posix()
                vistos.add(relativa)
                cambio = self._reconciliar(proyecto.id, archivo, relativa, registrados)
                nuevos += cambio == "nuevo"
                movidos += cambio == "movido"
                modificados += cambio == "modificado"

            desaparecidos = [d for ruta, d in registrados.items() if ruta not in vistos]
            for documento in desaparecidos:
                self._documentos.eliminar(documento.id)

        resultado = ResultadoEscaneo(
            nuevos=nuevos,
            movidos=movidos,
            modificados=modificados,
            eliminados=len(desaparecidos),
            total=len(en_disco),
        )
        if resultado.hubo_cambios:
            _log.info("Biblioteca de %s: %s", proyecto.nombre, resultado)
        return resultado

    def _reconciliar(
        self,
        proyecto_id: int,
        archivo: Path,
        relativa: str,
        registrados: dict[str, Documento],
    ) -> str:
        """Da de alta, actualiza o deja igual un archivo. Devuelve que hizo."""
        try:
            marca = huellas.calcular(archivo)
            tamano = archivo.stat().st_size
        except OSError as error:
            _log.warning("No se pudo leer %s: %s", archivo.name, error)
            return "ignorado"

        if (previo := registrados.get(relativa)) is not None:
            if previo.huella != marca:
                # Mismo sitio, contenido distinto: el PDF se reemplazo.
                self._documentos.actualizar_archivo(previo.id, huella=marca, bytes_=tamano)
                return "modificado"
            return "igual"

        # Ruta desconocida: puede ser un archivo movido o renombrado.
        if (mismo := self._documentos.por_huella(proyecto_id, marca)) is not None:
            self._documentos.mover(mismo.id, ruta_relativa=relativa, nombre=archivo.stem)
            registrados.pop(mismo.ruta_relativa, None)
            registrados[relativa] = mismo
            return "movido"

        creado = self._documentos.crear(
            proyecto_id,
            ruta_relativa=relativa,
            nombre=archivo.stem,
            huella=marca,
            bytes_=tamano,
        )
        registrados[relativa] = creado
        return "nuevo"
