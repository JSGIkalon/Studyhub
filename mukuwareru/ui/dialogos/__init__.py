"""Dialogos modales de la aplicacion."""

from mukuwareru.ui.dialogos.color_materia import DialogoColorMateria
from mukuwareru.ui.dialogos.etiquetar import DialogoEtiquetar
from mukuwareru.ui.dialogos.evaluacion import DialogoEvaluacion
from mukuwareru.ui.dialogos.importar import DialogoImportar
from mukuwareru.ui.dialogos.nota import DialogoNota
from mukuwareru.ui.dialogos.pesos import DialogoPesos
from mukuwareru.ui.dialogos.planificar import DialogoBloque, DialogoHito
from mukuwareru.ui.dialogos.proyecto import DialogoProyecto
from mukuwareru.ui.dialogos.vincular import DestinoElegido, DialogoVincular

__all__ = [
    "DestinoElegido",
    "DialogoBloque",
    "DialogoColorMateria",
    "DialogoEtiquetar",
    "DialogoEvaluacion",
    "DialogoHito",
    "DialogoImportar",
    "DialogoNota",
    "DialogoPesos",
    "DialogoProyecto",
    "DialogoVincular",
]
