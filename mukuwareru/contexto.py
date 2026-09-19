"""Contexto de la aplicacion: el unico estado compartido.

Sustituye a un contenedor de inyeccion de dependencias. Se construye una vez al
arrancar y se pasa por constructor a la ventana y a las vistas.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QObject, Signal

from mukuwareru.nucleo.modelos import Proyecto
from mukuwareru.nucleo.repositorios import (
    RepositorioAjustes,
    RepositorioAnotaciones,
    RepositorioBloques,
    RepositorioCuadernos,
    RepositorioDocumentos,
    RepositorioEtiquetas,
    RepositorioEvaluaciones,
    RepositorioGrafo,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioNotas,
    RepositorioProyectos,
    RepositorioSesiones,
)
from mukuwareru.nucleo.servicios import (
    ServicioBiblioteca,
    ServicioBusqueda,
    ServicioCalendario,
    ServicioCarga,
    ServicioEstadisticas,
    ServicioGrafo,
    ServicioImportacion,
    ServicioNotas,
    ServicioPlan,
    ServicioPreferencias,
    ServicioProgreso,
    ServicioProyectos,
    ServicioResultados,
)
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)


class Contexto(QObject):
    """Conexion, repositorios y proyecto activo.

    Emite ``proyecto_cambiado`` cuando cambia el proyecto activo y
    ``datos_cambiados`` cuando una vista escribe algo que otras muestran. En
    ambos casos las vistas se marcan como sucias y solo la visible se recarga.
    """

    proyecto_cambiado = Signal(object)  # Proyecto | None
    datos_cambiados = Signal(object)    # la vista que provoco el cambio
    disposicion_cambiada = Signal()     # cambio el orden o la visibilidad de las secciones

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        self.proyectos = RepositorioProyectos(conexion)
        self.materias = RepositorioMaterias(conexion)
        self.modulos = RepositorioModulos(conexion)
        self.sesiones = RepositorioSesiones(conexion)
        self.documentos = RepositorioDocumentos(conexion)
        self.anotaciones = RepositorioAnotaciones(conexion)
        self.ajustes = RepositorioAjustes(conexion)
        self.cuadernos = RepositorioCuadernos(conexion)
        self.notas = RepositorioNotas(conexion)
        self.etiquetas = RepositorioEtiquetas(conexion)
        self.hitos = RepositorioHitos(conexion)
        self.bloques = RepositorioBloques(conexion)
        self.evaluaciones = RepositorioEvaluaciones(conexion)
        self.grafo = RepositorioGrafo(conexion)

        self.progreso = ServicioProgreso(conexion)
        self.resultados = ServicioResultados(conexion)
        self.estadisticas = ServicioEstadisticas(conexion)
        self.preferencias = ServicioPreferencias(conexion)
        self.importacion = ServicioImportacion(conexion)
        self.biblioteca = ServicioBiblioteca(conexion)
        self.servicio_proyectos = ServicioProyectos(conexion)
        self.servicio_notas = ServicioNotas(conexion)
        self.calendario = ServicioCalendario(conexion)
        self.busqueda = ServicioBusqueda(conexion)
        self.plan = ServicioPlan(conexion)
        self.carga = ServicioCarga(conexion)
        self.servicio_grafo = ServicioGrafo(conexion)

        self._activo: Proyecto | None = None

    @property
    def proyecto(self) -> Proyecto | None:
        """Proyecto activo, o ``None`` si todavia no hay ninguno."""
        return self._activo

    def activar(self, proyecto: Proyecto | None) -> None:
        """Cambia el proyecto activo y avisa a quien escuche."""
        if proyecto is not None and self._activo is not None and proyecto.id == self._activo.id:
            return
        self._activo = proyecto
        _log.info("Proyecto activo: %s", proyecto.nombre if proyecto else "ninguno")
        self.proyecto_cambiado.emit(proyecto)

    def activar_primero_disponible(self) -> None:
        """Selecciona el primer proyecto no archivado, si existe alguno."""
        disponibles = self.proyectos.listar()
        self.activar(disponibles[0] if disponibles else None)

    def notificar_cambio(self, origen: object = None) -> None:
        """Avisa de que los datos cambiaron y las demas vistas deben recargar.

        ``origen`` es la vista responsable del cambio; se excluye para que no se
        reconstruya a si misma y pierda el scroll o las secciones desplegadas.
        """
        self.datos_cambiados.emit(origen)

    def refrescar_proyecto_activo(self) -> None:
        """Recarga el proyecto activo desde la base de datos."""
        if self._activo is None:
            return
        actualizado = self.proyectos.obtener(self._activo.id)
        self._activo = actualizado
        self.proyecto_cambiado.emit(actualizado)
