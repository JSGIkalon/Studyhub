"""Repositorios: el unico lugar del proyecto donde se escribe SQL."""

from mukuwareru.nucleo.repositorios.ajustes import RepositorioAjustes
from mukuwareru.nucleo.repositorios.anotaciones import RepositorioAnotaciones
from mukuwareru.nucleo.repositorios.bloques import RepositorioBloques
from mukuwareru.nucleo.repositorios.cuadernos import RepositorioCuadernos
from mukuwareru.nucleo.repositorios.documentos import RepositorioDocumentos
from mukuwareru.nucleo.repositorios.etiquetas import RepositorioEtiquetas
from mukuwareru.nucleo.repositorios.evaluaciones import (
    LineaPesada,
    RepositorioEvaluaciones,
)
from mukuwareru.nucleo.repositorios.hitos import RepositorioHitos
from mukuwareru.nucleo.repositorios.materias import RepositorioMaterias
from mukuwareru.nucleo.repositorios.modulos import ConteoMateria, RepositorioModulos
from mukuwareru.nucleo.repositorios.notas import NotaListada, RepositorioNotas
from mukuwareru.nucleo.repositorios.proyectos import RepositorioProyectos
from mukuwareru.nucleo.repositorios.sesiones import RepositorioSesiones

__all__ = [
    "ConteoMateria",
    "LineaPesada",
    "NotaListada",
    "RepositorioAjustes",
    "RepositorioAnotaciones",
    "RepositorioBloques",
    "RepositorioCuadernos",
    "RepositorioDocumentos",
    "RepositorioEtiquetas",
    "RepositorioEvaluaciones",
    "RepositorioHitos",
    "RepositorioMaterias",
    "RepositorioModulos",
    "RepositorioNotas",
    "RepositorioProyectos",
    "RepositorioSesiones",
]
