"""Busqueda global: una consulta, todo el proyecto.

Es lo que hace que «todo ligado» se note a diario. Sin esto hay que recordar en
que seccion vive cada cosa antes de poder buscarla, que es justo lo que una
aplicacion con seis secciones no deberia exigir.

Devuelve ``Resultado`` con lo justo para pintar la fila y para saber a donde ir.
Quien navega es la interfaz: aqui no se conoce ninguna vista.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from mukuwareru.nucleo.repositorios import (
    RepositorioAnotaciones,
    RepositorioDocumentos,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioNotas,
)
from mukuwareru.utilidades import formato
from mukuwareru.utilidades.texto import a_texto_plano, primera_linea

# Tope por familia. Una busqueda de dos letras puede encontrar cientos de cosas y
# la paleta solo muestra un punado: recortar aqui evita construir lo que no se va
# a ver.
_POR_FAMILIA = 8


class Familia(StrEnum):
    """Que clase de cosa encontro la busqueda."""

    NOTA = "nota"
    ANOTACION = "anotacion"
    MATERIA = "materia"
    MODULO = "modulo"
    DOCUMENTO = "documento"
    HITO = "hito"

    @property
    def etiqueta(self) -> str:
        """Como se llama en la paleta."""
        return {
            "nota": "Nota",
            "anotacion": "En PDF",
            "materia": "Materia",
            "modulo": "Modulo",
            "documento": "PDF",
            "hito": "Fecha",
        }[self.value]


@dataclass(frozen=True, slots=True)
class Resultado:
    """Una coincidencia, lista para pintar y para navegar."""

    familia: Familia
    titulo: str
    subtitulo: str
    objeto_id: int
    # Solo para documentos y anotaciones: a que pagina hay que abrir el PDF.
    documento_id: int | None = None
    pagina: int | None = None


class ServicioBusqueda:
    """Busca a la vez en notas, anotaciones, temario, PDFs y fechas."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._notas = RepositorioNotas(conexion)
        self._anotaciones = RepositorioAnotaciones(conexion)
        self._materias = RepositorioMaterias(conexion)
        self._modulos = RepositorioModulos(conexion)
        self._documentos = RepositorioDocumentos(conexion)
        self._hitos = RepositorioHitos(conexion)

    def buscar(self, proyecto_id: int, texto: str) -> list[Resultado]:
        """Coincidencias del proyecto, agrupadas por familia y ya recortadas.

        El texto se compara sin distinguir mayusculas. Una cadena vacia devuelve
        nada: una paleta que lo lista todo antes de escribir no orienta.
        """
        aguja = texto.strip().casefold()
        if not aguja:
            return []

        resultados: list[Resultado] = []
        resultados += self._notas_que_coinciden(proyecto_id, texto)
        resultados += self._anotaciones_que_coinciden(proyecto_id, aguja)
        resultados += self._temario_que_coincide(proyecto_id, aguja)
        resultados += self._documentos_que_coinciden(proyecto_id, aguja)
        resultados += self._hitos_que_coinciden(proyecto_id, aguja)
        return resultados

    # -- Por familia --------------------------------------------------------

    def _notas_que_coinciden(self, proyecto_id: int, texto: str) -> list[Resultado]:
        """El filtro va en SQL: `cuerpo_plano` ya esta preparado para buscar."""
        encontradas = self._notas.listar_del_proyecto(
            proyecto_id, texto=texto, limite=_POR_FAMILIA
        )
        return [
            Resultado(
                familia=Familia.NOTA,
                titulo=(
                    listada.nota.titulo.strip()
                    or primera_linea(listada.nota.cuerpo_plano)
                    or "Nota sin titulo"
                ),
                subtitulo=" -> ".join(
                    (listada.cuaderno, listada.seccion, *listada.destinos)
                ),
                objeto_id=listada.nota.id,
            )
            for listada in encontradas
        ]

    def _anotaciones_que_coinciden(
        self, proyecto_id: int, aguja: str
    ) -> list[Resultado]:
        encontradas: list[Resultado] = []
        for anotacion, documento in self._anotaciones.listar_del_proyecto(proyecto_id):
            campos = (
                anotacion.texto_seleccionado or "",
                a_texto_plano(anotacion.comentario or ""),
            )
            if not any(aguja in campo.casefold() for campo in campos):
                continue
            cuerpo = next((c for c in campos if c.strip()), "")
            encontradas.append(
                Resultado(
                    familia=Familia.ANOTACION,
                    titulo=primera_linea(cuerpo, 70) or anotacion.tipo.capitalize(),
                    subtitulo=f"{documento} · pagina {anotacion.pagina + 1}",
                    objeto_id=anotacion.id,
                    documento_id=anotacion.documento_id,
                    pagina=anotacion.pagina,
                )
            )
            if len(encontradas) == _POR_FAMILIA:
                break
        return encontradas

    def _temario_que_coincide(self, proyecto_id: int, aguja: str) -> list[Resultado]:
        materias: list[Resultado] = []
        modulos: list[Resultado] = []
        por_materia = self._modulos.listar_del_proyecto(proyecto_id)
        for materia in self._materias.listar(proyecto_id):
            if aguja in materia.nombre.casefold() and len(materias) < _POR_FAMILIA:
                materias.append(
                    Resultado(
                        familia=Familia.MATERIA,
                        titulo=materia.nombre,
                        subtitulo="Materia del temario",
                        objeto_id=materia.id,
                    )
                )
            if len(modulos) >= _POR_FAMILIA:
                continue
            for modulo in por_materia.get(materia.id, []):
                if aguja not in modulo.nombre.casefold():
                    continue
                modulos.append(
                    Resultado(
                        familia=Familia.MODULO,
                        titulo=modulo.nombre,
                        subtitulo=materia.nombre
                        + ("  ·  completado" if modulo.completado else ""),
                        objeto_id=modulo.id,
                    )
                )
                if len(modulos) == _POR_FAMILIA:
                    break
        return materias + modulos

    def _documentos_que_coinciden(
        self, proyecto_id: int, aguja: str
    ) -> list[Resultado]:
        encontrados = [
            documento
            for documento in self._documentos.listar(proyecto_id)
            if aguja in documento.nombre.casefold()
        ][:_POR_FAMILIA]
        return [
            Resultado(
                familia=Familia.DOCUMENTO,
                titulo=documento.nombre,
                subtitulo=documento.ruta_relativa,
                objeto_id=documento.id,
                documento_id=documento.id,
                pagina=documento.pagina_actual,
            )
            for documento in encontrados
        ]

    def _hitos_que_coinciden(self, proyecto_id: int, aguja: str) -> list[Resultado]:
        hoy = date.today()
        encontrados = [
            hito
            for hito in self._hitos.listar(proyecto_id)
            if aguja in hito.titulo.casefold()
        ][:_POR_FAMILIA]
        return [
            Resultado(
                familia=Familia.HITO,
                titulo=hito.titulo,
                subtitulo=f"{formato.fecha_corta(hito.fecha)}  ·  "
                + formato.dias_relativos(hito.dias_restantes(hoy)),
                objeto_id=hito.id,
            )
            for hito in encontrados
        ]

