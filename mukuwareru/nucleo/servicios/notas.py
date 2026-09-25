"""Orquestacion de cuadernos, notas, etiquetas y vinculos.

La interfaz no deberia saber que para escribir una nota rapida hay que asegurar
antes un cuaderno y una seccion, ni como se traduce un vinculo a algo que se
pueda pintar. Eso es lo que resuelve este servicio.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from mukuwareru.nucleo.modelos.entidades import (
    Anotacion,
    Cuaderno,
    Documento,
    Materia,
    Modulo,
    Nota,
    Seccion,
)
from mukuwareru.nucleo.repositorios import (
    NotaListada,
    RepositorioAnotaciones,
    RepositorioCuadernos,
    RepositorioDocumentos,
    RepositorioEtiquetas,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioNotas,
)
from mukuwareru.utilidades.texto import a_texto_plano, primera_linea

SIN_TITULO = "Nota sin titulo"


@dataclass(frozen=True, slots=True)
class NodoArbol:
    """Un cuaderno con sus secciones y cuantas notas tiene cada una."""

    cuaderno: Cuaderno
    secciones: list[tuple[Seccion, int]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Notas del cuaderno entero."""
        return sum(cuenta for _seccion, cuenta in self.secciones)


@dataclass(frozen=True, slots=True)
class ContextoNota:
    """Los vinculos de una nota, resueltos a objetos presentables.

    Es lo que alimenta el panel «Relacionado con»: la interfaz recibe entidades
    con nombre, no identificadores sueltos que tendria que ir a buscar.
    """

    materias: list[Materia] = field(default_factory=list)
    modulos: list[tuple[Modulo, str]] = field(default_factory=list)
    documentos: list[tuple[Documento, int | None]] = field(default_factory=list)
    anotaciones: list[tuple[Anotacion, str]] = field(default_factory=list)

    @property
    def vacio(self) -> bool:
        """Si la nota no esta ligada a nada todavia."""
        return not (self.materias or self.modulos or self.documentos or self.anotaciones)


class ServicioNotas:
    """Cuadernos, notas y el interlinkado con el resto de la aplicacion."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._cuadernos = RepositorioCuadernos(conexion)
        self._notas = RepositorioNotas(conexion)
        self._etiquetas = RepositorioEtiquetas(conexion)
        self._materias = RepositorioMaterias(conexion)
        self._modulos = RepositorioModulos(conexion)
        self._documentos = RepositorioDocumentos(conexion)
        self._anotaciones = RepositorioAnotaciones(conexion)

    # -- Arbol --------------------------------------------------------------

    def arbol(self, proyecto_id: int) -> list[NodoArbol]:
        """Cuadernos con sus secciones y contadores, listo para pintar."""
        cuentas = self._cuadernos.contar_notas(proyecto_id)
        arbol: list[NodoArbol] = []
        for cuaderno in self._cuadernos.listar(proyecto_id):
            secciones = [
                (seccion, cuentas.get(seccion.id, 0))
                for seccion in self._cuadernos.listar_secciones(cuaderno.id)
            ]
            arbol.append(NodoArbol(cuaderno=cuaderno, secciones=secciones))
        return arbol

    # -- Notas --------------------------------------------------------------

    def crear_rapida(
        self, proyecto_id: int, *, titulo: str = "", cuerpo: str = ""
    ) -> Nota:
        """Nota nueva sin decidir nada: cae en la seccion por defecto.

        Es el camino de «Nota nueva» y el de convertir un resaltado en nota. Que
        no haya que elegir cuaderno es justo lo que distingue una nota rapida de
        una nota organizada.
        """
        seccion = self._cuadernos.asegurar_por_defecto(proyecto_id)
        return self._notas.crear(seccion.id, titulo=titulo, cuerpo=cuerpo)

    def guardar(self, nota_id: int, *, titulo: str, cuerpo: str) -> Nota | None:
        """Guarda la nota; si no tiene titulo, lo deduce de su primera linea.

        Obligar a poner titulo antes de escribir corta el impulso de apuntar
        algo; dejar una lista de «(sin titulo)» tampoco sirve. Deducirlo resuelve
        las dos cosas, y sigue siendo editable.
        """
        limpio = titulo.strip() or primera_linea(cuerpo)
        self._notas.actualizar(nota_id, titulo=limpio, cuerpo=cuerpo)
        return self._notas.obtener(nota_id)

    def titulo_visible(self, nota: Nota) -> str:
        """Como llamar a la nota en una lista, aunque no tenga titulo."""
        return nota.titulo.strip() or primera_linea(nota.cuerpo_plano) or SIN_TITULO

    def buscar(
        self,
        proyecto_id: int,
        texto: str = "",
        *,
        cuaderno_id: int | None = None,
        seccion_id: int | None = None,
        etiqueta_id: int | None = None,
    ) -> list[NotaListada]:
        """Notas del proyecto que cumplen los filtros activos."""
        return self._notas.listar_del_proyecto(
            proyecto_id,
            texto=texto.strip() or None,
            cuaderno_id=cuaderno_id,
            seccion_id=seccion_id,
            etiqueta_id=etiqueta_id,
        )

    # -- Interlinkado -------------------------------------------------------

    def contexto(self, nota_id: int) -> ContextoNota:
        """Resuelve los vinculos de la nota a entidades con nombre."""
        materias: list[Materia] = []
        modulos: list[tuple[Modulo, str]] = []
        documentos: list[tuple[Documento, int | None]] = []
        anotaciones: list[tuple[Anotacion, str]] = []

        for vinculo in self._notas.vinculos_de(nota_id):
            if vinculo.materia_id is not None:
                if (materia := self._materias.obtener(vinculo.materia_id)) is not None:
                    materias.append(materia)
            elif vinculo.modulo_id is not None:
                if (modulo := self._modulos.obtener(vinculo.modulo_id)) is not None:
                    padre = self._materias.obtener(modulo.materia_id)
                    modulos.append((modulo, padre.nombre if padre else ""))
            elif vinculo.documento_id is not None:
                documento = self._documentos.obtener(vinculo.documento_id)
                if documento is not None:
                    documentos.append((documento, vinculo.pagina))
            elif vinculo.anotacion_id is not None:
                par = self._anotaciones.obtener_con_documento(vinculo.anotacion_id)
                if par is not None:
                    anotaciones.append(par)

        return ContextoNota(
            materias=materias,
            modulos=modulos,
            documentos=documentos,
            anotaciones=anotaciones,
        )

    def desde_anotacion(self, proyecto_id: int, anotacion: Anotacion) -> Nota:
        """Convierte un resaltado en nota suelta y las deja vinculadas.

        La anotacion **no se borra**: sigue pintada sobre su pagina. La nota es
        el sitio donde desarrollar la idea, no un traslado.
        """
        semilla = anotacion.texto_seleccionado or a_texto_plano(anotacion.comentario or "")
        nota = self.crear_rapida(
            proyecto_id,
            titulo=primera_linea(semilla) or SIN_TITULO,
            cuerpo=semilla,
        )
        self._notas.vincular_anotacion(nota.id, anotacion.id)
        self._notas.vincular_documento(
            nota.id, anotacion.documento_id, pagina=anotacion.pagina
        )
        recargada = self._notas.obtener(nota.id)
        return recargada if recargada is not None else nota

    def para_documento(
        self, documento_id: int, pagina: int | None = None
    ) -> list[NotaListada]:
        """Notas vinculadas a un PDF, con sus vinculos resueltos.

        El panel del lector necesita saber **a que pagina** apunta cada nota
        para ordenarlas junto a las anotaciones, y eso esta en los vinculos. Son
        las notas de un solo documento, un punado, asi que resolverlas una a una
        no compensa complicar la consulta de lista.
        """
        listadas = self._notas.por_documento(documento_id, pagina)
        for listada in listadas:
            listada.nota.vinculos = self._notas.vinculos_de(listada.nota.id)
        return listadas

    def catalogo_para_vincular(
        self, proyecto_id: int
    ) -> tuple[list[Materia], dict[int, list[Modulo]], list[Documento]]:
        """Materias, sus modulos agrupados y los PDFs del proyecto.

        Agrupar los modulos **por materia** aqui, y no listarlos en plano, es lo
        que permite que el dialogo de vinculacion filtre en cascada: elegir una
        materia deja fuera los modulos de las demas.
        """
        materias = self._materias.listar(proyecto_id)
        agrupados = self._modulos.listar_del_proyecto(proyecto_id)
        modulos = {m.id: agrupados.get(m.id, []) for m in materias}
        return materias, modulos, self._documentos.listar(proyecto_id)

    def vincular(
        self, nota_id: int, clase: str, objeto_id: int, pagina: int | None = None
    ) -> None:
        """Crea el vinculo que corresponda a la clase de destino elegida."""
        if clase == "materia":
            self._notas.vincular_materia(nota_id, objeto_id)
        elif clase == "modulo":
            self._notas.vincular_modulo(nota_id, objeto_id)
        elif clase == "documento":
            self._notas.vincular_documento(nota_id, objeto_id, pagina=pagina)

    def crear_para_documento(
        self,
        proyecto_id: int,
        documento_id: int,
        pagina: int,
        *,
        titulo: str = "",
        cuerpo: str = "",
    ) -> Nota:
        """Nota nueva ya ligada a un PDF y a la pagina que se esta leyendo.

        Es el camino de «Nota en cuaderno» del lector: sin esto habria que crear
        la nota, ir a la vista Notas y relacionarla a mano.
        """
        nota = self.crear_rapida(
            proyecto_id, titulo=titulo or primera_linea(cuerpo), cuerpo=cuerpo
        )
        self._notas.vincular_documento(nota.id, documento_id, pagina=pagina)
        recargada = self._notas.obtener(nota.id)
        return recargada if recargada is not None else nota
