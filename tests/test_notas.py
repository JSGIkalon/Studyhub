"""Notas sueltas: cuadernos, etiquetas y, sobre todo, vinculos.

Lo que se vigila aqui es la diferencia entre una nota y una anotacion: la
anotacion muere con su PDF y la nota le sobrevive. Es la razon de que sean dos
tablas y no una.
"""

from __future__ import annotations

import sqlite3

import pytest

from mukuwareru.nucleo.modelos import DestinoVinculo, Proyecto, TipoAnotacion
from mukuwareru.nucleo.repositorios import (
    RepositorioAnotaciones,
    RepositorioCuadernos,
    RepositorioDocumentos,
    RepositorioEtiquetas,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioNotas,
    RepositorioProyectos,
)
from mukuwareru.nucleo.servicios import ServicioNotas


@pytest.fixture
def proyecto(conn: sqlite3.Connection) -> Proyecto:
    return RepositorioProyectos(conn).crear("CFA")


@pytest.fixture
def seccion_id(conn: sqlite3.Connection, proyecto: Proyecto) -> int:
    return RepositorioCuadernos(conn).asegurar_por_defecto(proyecto.id).id


def _documento(conn: sqlite3.Connection, proyecto: Proyecto, nombre: str = "uno") -> int:
    return RepositorioDocumentos(conn).crear(
        proyecto.id,
        ruta_relativa=f"{nombre}.pdf",
        nombre=nombre,
        huella=f"huella-{nombre}",
        bytes_=10,
    ).id


# --- Cuadernos y secciones -------------------------------------------------


def test_asegurar_por_defecto_crea_cuaderno_y_seccion(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """La migracion no siembra: la siembra tiene un solo camino, este."""
    cuadernos = RepositorioCuadernos(conn)
    assert cuadernos.listar(proyecto.id) == []

    seccion = cuadernos.asegurar_por_defecto(proyecto.id)

    assert len(cuadernos.listar(proyecto.id)) == 1
    assert seccion.nombre == "General"
    assert seccion.creado_en is not None
    # La marca lleva desfase local, como manda la convencion de 001.
    assert seccion.creado_en.tzinfo is not None


def test_asegurar_por_defecto_es_idempotente(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    cuadernos = RepositorioCuadernos(conn)
    primera = cuadernos.asegurar_por_defecto(proyecto.id)
    segunda = cuadernos.asegurar_por_defecto(proyecto.id)
    assert primera.id == segunda.id
    assert len(cuadernos.listar(proyecto.id)) == 1


def test_borrar_un_cuaderno_arrastra_secciones_y_notas(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    cuadernos = RepositorioCuadernos(conn)
    notas = RepositorioNotas(conn)
    notas.crear(seccion_id, titulo="Adios")

    cuaderno = cuadernos.listar(proyecto.id)[0]
    cuadernos.eliminar(cuaderno.id)

    assert cuadernos.listar_secciones(cuaderno.id) == []
    assert notas.contar(proyecto.id) == 0


def test_el_arbol_lleva_los_contadores(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    notas.crear(seccion_id, titulo="Una")
    notas.crear(seccion_id, titulo="Otra")

    arbol = ServicioNotas(conn).arbol(proyecto.id)
    assert len(arbol) == 1
    assert arbol[0].total == 2
    assert arbol[0].secciones[0][1] == 2


# --- Notas y busqueda ------------------------------------------------------


def test_el_cuerpo_plano_se_deriva_al_escribir(
    conn: sqlite3.Connection, seccion_id: int
) -> None:
    html = (
        "<!doctype html><html><body><p>Sobre las normas</p>"
        '<img src="data:image/png;base64,iVBORw0KGgoAAAgifAAA"></body></html>'
    )
    notas = RepositorioNotas(conn)
    nota = notas.crear(seccion_id, titulo="Etica", cuerpo=html)

    assert nota.cuerpo_plano == "Sobre las normas [imagen]"
    assert nota.cuerpo == html


def test_el_cuerpo_plano_se_recalcula_al_actualizar(
    conn: sqlite3.Connection, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    nota = notas.crear(seccion_id, cuerpo="viejo")
    notas.actualizar(nota.id, titulo="T", cuerpo="<!doctype html><p>nuevo</p>")

    releida = notas.obtener(nota.id)
    assert releida is not None
    assert releida.cuerpo_plano == "nuevo"


def test_la_busqueda_no_encuentra_dentro_del_base64(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    """El motivo entero de que exista la columna `cuerpo_plano`."""
    notas = RepositorioNotas(conn)
    notas.crear(
        seccion_id,
        titulo="Con imagen",
        cuerpo='<!doctype html><p>Etica</p><img src="data:image/png;base64,iVBORgif0K">',
    )

    assert len(notas.listar_del_proyecto(proyecto.id, texto="Etica")) == 1
    assert notas.listar_del_proyecto(proyecto.id, texto="gif") == []


def test_la_busqueda_mira_titulo_y_cuerpo(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    notas.crear(seccion_id, titulo="Duracion modificada", cuerpo="nada relevante")
    notas.crear(seccion_id, titulo="Otra", cuerpo="habla de duracion tambien")

    assert len(notas.listar_del_proyecto(proyecto.id, texto="duracion")) == 2


def test_la_nota_listada_dice_de_donde_sale(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    RepositorioNotas(conn).crear(seccion_id, titulo="Una")
    listada = RepositorioNotas(conn).listar_del_proyecto(proyecto.id)[0]
    assert (listada.cuaderno, listada.seccion) == ("General", "General")


def test_la_nota_listada_trae_sus_destinos(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    """Cada fila dice con que esta ligada sin tener que abrir la nota."""
    notas = RepositorioNotas(conn)
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    modulo = RepositorioModulos(conn).crear(materia.id, "Code of Standards")
    documento = _documento(conn, proyecto)
    nota = notas.crear(seccion_id, titulo="Todo ligado")
    notas.vincular_materia(nota.id, materia.id)
    notas.vincular_modulo(nota.id, modulo.id)
    notas.vincular_documento(nota.id, documento, pagina=43)

    listada = notas.listar_del_proyecto(proyecto.id)[0]

    # El orden es materia, modulo, PDF: de lo general a lo concreto.
    assert listada.destinos == ("Ethics", "Code of Standards", "uno p. 44")
    ruta = listada.ruta("Todo ligado")
    assert ruta.startswith("General  ->  General  ->  Todo ligado  ->  ")
    assert "Ethics · Code of Standards · uno p. 44" in ruta


def test_una_nota_sin_vinculos_no_tiene_destinos(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    RepositorioNotas(conn).crear(seccion_id, titulo="Suelta")
    listada = RepositorioNotas(conn).listar_del_proyecto(proyecto.id)[0]
    assert listada.destinos == ()
    assert listada.ruta("Suelta") == "General  ->  General  ->  Suelta"


def test_un_vinculo_al_documento_entero_no_pone_pagina(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    nota = notas.crear(seccion_id, titulo="Del libro")
    notas.vincular_documento(nota.id, _documento(conn, proyecto))

    assert notas.listar_del_proyecto(proyecto.id)[0].destinos == ("uno",)


def test_el_catalogo_para_vincular_agrupa_los_modulos_por_materia(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Lo que permite que el dialogo filtre en cascada."""
    materias = RepositorioMaterias(conn)
    modulos = RepositorioModulos(conn)
    ethics = materias.crear(proyecto.id, "Ethics")
    corporate = materias.crear(proyecto.id, "Corporate Issuers")
    modulos.crear(ethics.id, "Code of Standards")
    modulos.crear(corporate.id, "Capital Structure")
    modulos.crear(corporate.id, "Business Models")

    _materias, por_materia, _documentos = ServicioNotas(
        conn
    ).catalogo_para_vincular(proyecto.id)

    assert [m.nombre for m in por_materia[ethics.id]] == ["Code of Standards"]
    assert len(por_materia[corporate.id]) == 2
    # Ningun modulo de Corporate se cuela entre los de Ethics.
    assert "Capital Structure" not in {m.nombre for m in por_materia[ethics.id]}


def test_crear_para_documento_deja_la_nota_ya_ligada(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """El camino de «Nota en cuaderno» desde el lector."""
    documento = _documento(conn, proyecto)
    servicio = ServicioNotas(conn)

    nota = servicio.crear_para_documento(
        proyecto.id, documento, 12, cuerpo="Lo que entendi de esta pagina"
    )

    assert nota.titulo == "Lo que entendi de esta pagina"
    vinculo = nota.vinculos[0]
    assert (vinculo.documento_id, vinculo.pagina) == (documento, 12)
    assert len(servicio.para_documento(documento, 12)) == 1


def test_el_titulo_se_deduce_de_la_primera_linea(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    servicio = ServicioNotas(conn)
    nota = servicio.crear_rapida(proyecto.id)
    guardada = servicio.guardar(nota.id, titulo="   ", cuerpo="Lo primero que apunto")

    assert guardada is not None
    assert guardada.titulo == "Lo primero que apunto"


# --- Etiquetas -------------------------------------------------------------


def test_etiquetar_reemplaza_las_anteriores(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    etiquetas = RepositorioEtiquetas(conn)
    notas = RepositorioNotas(conn)
    dudas = etiquetas.crear(proyecto.id, "dudas")
    formulas = etiquetas.crear(proyecto.id, "formulas")
    nota = notas.crear(seccion_id, titulo="Una")

    notas.etiquetar(nota.id, [dudas.id, formulas.id])
    notas.etiquetar(nota.id, [formulas.id])

    assert notas.etiquetas_de(nota.id) == [formulas.id]


def test_obtener_o_crear_no_duplica(conn: sqlite3.Connection, proyecto: Proyecto) -> None:
    etiquetas = RepositorioEtiquetas(conn)
    primera = etiquetas.obtener_o_crear(proyecto.id, "dudas")
    segunda = etiquetas.obtener_o_crear(proyecto.id, "dudas")
    assert primera.id == segunda.id
    assert len(etiquetas.listar(proyecto.id)) == 1


def test_filtrar_por_etiqueta(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    etiquetas = RepositorioEtiquetas(conn)
    notas = RepositorioNotas(conn)
    dudas = etiquetas.crear(proyecto.id, "dudas")
    marcada = notas.crear(seccion_id, titulo="Marcada")
    notas.crear(seccion_id, titulo="Suelta")
    notas.etiquetar(marcada.id, [dudas.id])

    encontradas = notas.listar_del_proyecto(proyecto.id, etiqueta_id=dudas.id)
    assert [n.nota.titulo for n in encontradas] == ["Marcada"]


# --- Vinculos: el interlinkado ---------------------------------------------


def test_un_vinculo_apunta_a_una_sola_cosa(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    """El CHECK que impide un vinculo ambiguo."""
    nota = RepositorioNotas(conn).crear(seccion_id, titulo="Una")
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    documento = _documento(conn, proyecto)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO nota_vinculo (nota_id, materia_id, documento_id, creado_en)
            VALUES (?, ?, ?, '2026-08-17T10:00:00-05:00')
            """,
            (nota.id, materia.id, documento),
        )


def test_un_vinculo_sin_destino_tampoco_vale(
    conn: sqlite3.Connection, seccion_id: int
) -> None:
    nota = RepositorioNotas(conn).crear(seccion_id, titulo="Una")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO nota_vinculo (nota_id, creado_en) VALUES (?, '2026-08-17T10:00:00-05:00')",
            (nota.id,),
        )


def test_la_pagina_sin_documento_no_vale(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    nota = RepositorioNotas(conn).crear(seccion_id, titulo="Una")
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO nota_vinculo (nota_id, materia_id, pagina, creado_en)
            VALUES (?, ?, 4, '2026-08-17T10:00:00-05:00')
            """,
            (nota.id, materia.id),
        )


def test_vincular_dos_veces_lo_mismo_es_inocuo(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    """Comprueba de paso el indice unico con COALESCE(pagina, -1)."""
    notas = RepositorioNotas(conn)
    nota = notas.crear(seccion_id, titulo="Una")
    documento = _documento(conn, proyecto)

    notas.vincular_documento(nota.id, documento)
    notas.vincular_documento(nota.id, documento)
    notas.vincular_documento(nota.id, documento, pagina=4)
    notas.vincular_documento(nota.id, documento, pagina=4)

    # El documento entero y la pagina 4 son dos vinculos distintos, pero
    # repetir cualquiera de los dos no anade nada.
    assert len(notas.vinculos_de(nota.id)) == 2


def test_el_destino_del_vinculo_se_deduce(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    nota = notas.crear(seccion_id, titulo="Una")
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    notas.vincular_materia(nota.id, materia.id)

    vinculo = notas.vinculos_de(nota.id)[0]
    assert vinculo.destino is DestinoVinculo.MATERIA
    assert vinculo.objeto_id == materia.id


def test_borrar_el_pdf_no_borra_la_nota(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    """La razon de ser de la tabla `nota`, frente a extender `anotacion`.

    Un resaltado sin su PDF no significa nada y se va con el. Una nota que
    *menciona* ese PDF tiene valor por si sola y debe sobrevivirle.
    """
    notas = RepositorioNotas(conn)
    documentos = RepositorioDocumentos(conn)
    nota = notas.crear(seccion_id, titulo="Lo que aprendi del libro")
    documento = _documento(conn, proyecto)
    notas.vincular_documento(nota.id, documento, pagina=12)

    documentos.eliminar(documento)

    superviviente = notas.obtener(nota.id)
    assert superviviente is not None
    assert superviviente.titulo == "Lo que aprendi del libro"
    # El vinculo si desaparece: apuntaba a algo que ya no existe.
    assert superviviente.vinculos == []


def test_borrar_la_nota_se_lleva_sus_vinculos(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    nota = notas.crear(seccion_id, titulo="Una")
    notas.vincular_documento(nota.id, _documento(conn, proyecto))

    notas.eliminar(nota.id)

    assert conn.execute("SELECT COUNT(*) FROM nota_vinculo").fetchone()[0] == 0


def test_busqueda_inversa_por_documento_y_pagina(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    """Lo que alimenta la pestana «Relacionadas» del lector."""
    notas = RepositorioNotas(conn)
    documento = _documento(conn, proyecto)

    del_libro = notas.crear(seccion_id, titulo="Del libro entero")
    de_la_pagina = notas.crear(seccion_id, titulo="De la pagina 4")
    de_otra = notas.crear(seccion_id, titulo="De la pagina 9")
    notas.vincular_documento(del_libro.id, documento)
    notas.vincular_documento(de_la_pagina.id, documento, pagina=4)
    notas.vincular_documento(de_otra.id, documento, pagina=9)

    titulos = {n.nota.titulo for n in notas.por_documento(documento, pagina=4)}
    # En la pagina 4 es relevante lo suyo y lo del documento entero.
    assert titulos == {"Del libro entero", "De la pagina 4"}
    assert len(notas.por_documento(documento)) == 3


def test_una_nota_con_dos_vinculos_al_mismo_pdf_no_sale_duplicada(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    documento = _documento(conn, proyecto)
    nota = notas.crear(seccion_id, titulo="Una")
    notas.vincular_documento(nota.id, documento)
    notas.vincular_documento(nota.id, documento, pagina=4)

    assert len(notas.por_documento(documento, pagina=4)) == 1


def test_busqueda_inversa_por_materia_y_modulo(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    modulo = RepositorioModulos(conn).crear(materia.id, "Code of Standards")
    nota = notas.crear(seccion_id, titulo="Sobre etica")
    notas.vincular_materia(nota.id, materia.id)
    notas.vincular_modulo(nota.id, modulo.id)

    assert len(notas.por_materia(materia.id)) == 1
    assert len(notas.por_modulo(modulo.id)) == 1
    assert notas.conteo_por_materia(proyecto.id) == {materia.id: 1}


def test_conteo_por_documento(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    uno = _documento(conn, proyecto, "uno")
    dos = _documento(conn, proyecto, "dos")
    for titulo in ("a", "b"):
        notas.vincular_documento(notas.crear(seccion_id, titulo=titulo).id, uno)

    assert notas.conteo_por_documento(proyecto.id) == {uno: 2}
    assert dos not in notas.conteo_por_documento(proyecto.id)


# --- Del resaltado a la nota -----------------------------------------------


def test_convertir_una_anotacion_en_nota_las_deja_ligadas(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    documento = _documento(conn, proyecto)
    anotacion = RepositorioAnotaciones(conn).crear(
        documento,
        tipo=TipoAnotacion.RESALTADO,
        pagina=43,
        texto_seleccionado="Un miembro debe mantener su independencia",
    )

    servicio = ServicioNotas(conn)
    nota = servicio.desde_anotacion(proyecto.id, anotacion)

    assert "independencia" in nota.cuerpo
    destinos = {v.destino for v in nota.vinculos}
    assert destinos == {DestinoVinculo.ANOTACION, DestinoVinculo.DOCUMENTO}
    # El resaltado sigue pintado en su pagina: no es un traslado.
    assert RepositorioAnotaciones(conn).obtener(anotacion.id) is not None


def test_el_contexto_resuelve_los_vinculos_a_nombres(
    conn: sqlite3.Connection, proyecto: Proyecto, seccion_id: int
) -> None:
    notas = RepositorioNotas(conn)
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    modulo = RepositorioModulos(conn).crear(materia.id, "Code of Standards")
    documento = _documento(conn, proyecto)
    anotacion = RepositorioAnotaciones(conn).crear(
        documento, tipo=TipoAnotacion.NOTA, pagina=2, comentario="ojo"
    )

    nota = notas.crear(seccion_id, titulo="Todo ligado")
    notas.vincular_materia(nota.id, materia.id)
    notas.vincular_modulo(nota.id, modulo.id)
    notas.vincular_documento(nota.id, documento, pagina=7)
    notas.vincular_anotacion(nota.id, anotacion.id)

    contexto = ServicioNotas(conn).contexto(nota.id)

    assert [m.nombre for m in contexto.materias] == ["Ethics"]
    assert contexto.modulos[0][1] == "Ethics"          # el modulo dice su materia
    assert contexto.documentos[0][1] == 7              # y el documento su pagina
    assert contexto.anotaciones[0][1] == "uno"         # y la anotacion su PDF
    assert contexto.vacio is False
