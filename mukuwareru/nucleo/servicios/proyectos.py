"""Alta, edicion, archivado y borrado de proyectos.

La interfaz no deberia saber que renombrar un proyecto puede mover una carpeta
del disco, ni en que orden hacerlo. Ese es todo el motivo de que este servicio
exista por encima de ``RepositorioProyectos``.

**La trampa del renombrado.** Con ``ruta_biblioteca`` en NULL la carpeta de PDFs
es ``Library/<nombre>`` (ver ``servicios.biblioteca.ruta_biblioteca``). Cambiar
el nombre sin mas reapunta la biblioteca a una carpeta que no existe; el
siguiente escaneo da todos los documentos por desaparecidos, los borra, y
``anotacion ... ON DELETE CASCADE`` se lleva todas las anotaciones. Aqui se
mueve la carpeta y, si el sistema no deja moverla, se fija ``ruta_biblioteca``
a la antigua: un proyecto nunca queda apuntando a una carpeta inexistente.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from mukuwareru.nucleo.modelos.entidades import Proyecto
from mukuwareru.nucleo.repositorios import RepositorioHitos, RepositorioProyectos
from mukuwareru.nucleo.servicios.biblioteca import ruta_biblioteca
from mukuwareru.utilidades import rutas
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)


@dataclass(frozen=True, slots=True)
class DatosProyecto:
    """Lo que el dialogo de proyecto devuelve, sin tocar la base de datos."""

    nombre: str
    icono: str = "libro"
    color: str = "#E5484D"
    fecha_objetivo: date | None = None
    ruta_biblioteca: str | None = None


@dataclass(frozen=True, slots=True)
class ResumenBorrado:
    """Lo que se perderia al borrar un proyecto, para poder avisar sin mentir."""

    materias: int = 0
    modulos: int = 0
    documentos: int = 0
    sesiones: int = 0
    anotaciones: int = 0
    carpeta: Path | None = None

    @property
    def hay_algo(self) -> bool:
        """Si el proyecto esta vacio, la confirmacion puede ser mas breve."""
        return bool(
            self.materias or self.modulos or self.documentos
            or self.sesiones or self.anotaciones
        )


class ServicioProyectos:
    """Reglas de ciclo de vida de un proyecto."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._proyectos = RepositorioProyectos(conexion)
        self._hitos = RepositorioHitos(conexion)

    # -- Alta y edicion -----------------------------------------------------

    def crear(self, datos: DatosProyecto) -> Proyecto:
        """Inserta un proyecto nuevo. No crea la carpeta: la crea el escaneo."""
        creado = self._proyectos.crear(
            datos.nombre,
            icono=datos.icono,
            color=datos.color,
            fecha_objetivo=datos.fecha_objetivo,
            ruta_biblioteca=datos.ruta_biblioteca,
        )
        self._hitos.fijar_objetivo(creado.id, creado.fecha_objetivo)
        return creado

    def guardar(self, proyecto: Proyecto, datos: DatosProyecto) -> Proyecto:
        """Aplica los cambios del dialogo, moviendo la biblioteca si procede.

        Devuelve el proyecto releido de la base de datos: ``ruta_biblioteca``
        puede haber cambiado por su cuenta al no poder moverse la carpeta.
        """
        ruta = datos.ruta_biblioteca
        if ruta is None and datos.nombre != proyecto.nombre:
            ruta = self._reubicar_biblioteca(proyecto, datos.nombre)

        proyecto.nombre = datos.nombre
        proyecto.icono = datos.icono
        proyecto.color = datos.color
        proyecto.fecha_objetivo = datos.fecha_objetivo
        proyecto.ruta_biblioteca = ruta
        self._proyectos.actualizar(proyecto)
        # La columna y el calendario no pueden discrepar, y la sincronizacion va
        # en un solo sentido: de `fecha_objetivo` al hito principal.
        self._hitos.fijar_objetivo(proyecto.id, datos.fecha_objetivo)

        actualizado = self._proyectos.obtener(proyecto.id)
        return actualizado if actualizado is not None else proyecto

    def renombrar(self, proyecto: Proyecto, nombre: str) -> Proyecto:
        """Cambia solo el nombre, conservando la biblioteca. Ver la nota del modulo."""
        return self.guardar(
            proyecto,
            DatosProyecto(
                nombre=nombre,
                icono=proyecto.icono,
                color=proyecto.color,
                fecha_objetivo=proyecto.fecha_objetivo,
                ruta_biblioteca=proyecto.ruta_biblioteca,
            ),
        )

    def _reubicar_biblioteca(self, proyecto: Proyecto, nombre_nuevo: str) -> str | None:
        """Mueve ``Library/<viejo>`` a ``Library/<nuevo>``.

        Devuelve la ``ruta_biblioteca`` que hay que guardar: ``None`` si la
        carpeta por defecto sigue siendo valida tras el movimiento, o la ruta
        antigua fijada de forma explicita si no se pudo mover.
        """
        vieja = ruta_biblioteca(proyecto)
        if not vieja.exists():
            # Nunca se creo (proyecto sin PDFs todavia): no hay nada que perder
            # y el escaneo creara la carpeta con el nombre nuevo.
            return None

        nueva = rutas.carpeta_biblioteca() / nombre_nuevo
        if nueva == vieja:
            return None
        try:
            nueva.parent.mkdir(parents=True, exist_ok=True)
            vieja.rename(nueva)
        except OSError as error:
            # OneDrive puede tener la carpeta tomada, o el destino ya existir.
            # Fijar la ruta antigua conserva los documentos y sus anotaciones,
            # que es lo unico irrecuperable.
            _log.warning(
                "No se pudo mover la biblioteca de «%s» a «%s»: %s. "
                "Se fija la ruta antigua.",
                vieja, nueva, error,
            )
            return str(vieja)

        _log.info("Biblioteca movida de «%s» a «%s»", vieja, nueva)
        return None

    # -- Archivado, orden y borrado -----------------------------------------

    def archivar(self, proyecto: Proyecto, archivado: bool = True) -> None:
        """Saca el proyecto de la barra lateral sin borrar nada."""
        proyecto.archivado = archivado
        self._proyectos.actualizar(proyecto)

    def reordenar(self, ids: list[int]) -> None:
        """Fija el orden de los proyectos en la barra lateral."""
        self._proyectos.reordenar(ids)

    def resumen_borrado(self, proyecto: Proyecto) -> ResumenBorrado:
        """Que se perderia al borrar este proyecto."""
        cuentas = self._proyectos.contar_dependencias(proyecto.id)
        return ResumenBorrado(
            materias=cuentas["materias"],
            modulos=cuentas["modulos"],
            documentos=cuentas["documentos"],
            sesiones=cuentas["sesiones"],
            anotaciones=cuentas["anotaciones"],
            carpeta=ruta_biblioteca(proyecto),
        )

    def eliminar(self, proyecto_id: int) -> None:
        """Borra el proyecto y su rastro en la base de datos.

        **Los PDF del disco no se tocan.** Borrar archivos del usuario a raiz de
        un clic en una barra lateral no es reversible; una carpeta de sobra si.
        """
        self._proyectos.eliminar(proyecto_id)
        _log.info("Proyecto %s eliminado", proyecto_id)
