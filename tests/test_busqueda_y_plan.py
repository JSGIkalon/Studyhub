"""Buscador global y plan de estudio opcional."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

from mukuwareru.nucleo.modelos import (
    OrigenSesion,
    Proyecto,
    TipoAnotacion,
    TipoSesion,
)
from mukuwareru.nucleo.repositorios import (
    RepositorioAnotaciones,
    RepositorioBloques,
    RepositorioCuadernos,
    RepositorioDocumentos,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioNotas,
    RepositorioProyectos,
    RepositorioSesiones,
)
from mukuwareru.nucleo.servicios import (
    Familia,
    PlanSemanal,
    ServicioBusqueda,
    ServicioPlan,
)

HOY = date(2026, 8, 17)  # un lunes


def _poblar(conn: sqlite3.Connection, proyecto: Proyecto) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    RepositorioModulos(conn).crear(materia.id, "Code of Ethics")
    documento = RepositorioDocumentos(conn).crear(
        proyecto.id,
        ruta_relativa="ethics.pdf",
        nombre="Ethics Curriculum",
        huella="abc",
        bytes_=10,
    )
    RepositorioAnotaciones(conn).crear(
        documento.id,
        tipo=TipoAnotacion.RESALTADO,
        pagina=43,
        texto_seleccionado="Un miembro debe mantener su independencia",
    )
    seccion = RepositorioCuadernos(conn).asegurar_por_defecto(proyecto.id)
    RepositorioNotas(conn).crear(
        seccion.id, titulo="Dudas de etica", cuerpo="sobre la independencia"
    )
    RepositorioHitos(conn).crear(proyecto.id, "Examen de Ethics", date(2026, 11, 13))


# --- Busqueda ---------------------------------------------------------------


def test_una_busqueda_recorre_todas_las_familias(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Lo que hace que «todo ligado» se note: un campo, todo el proyecto."""
    _poblar(conn, proyecto)

    familias = {r.familia for r in ServicioBusqueda(conn).buscar(proyecto.id, "ethic")}

    assert Familia.MATERIA in familias
    assert Familia.MODULO in familias
    assert Familia.DOCUMENTO in familias
    assert Familia.HITO in familias


def test_la_busqueda_encuentra_dentro_del_texto(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    _poblar(conn, proyecto)
    familias = {
        r.familia for r in ServicioBusqueda(conn).buscar(proyecto.id, "independencia")
    }
    assert familias == {Familia.NOTA, Familia.ANOTACION}


def test_la_busqueda_ignora_mayusculas(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    _poblar(conn, proyecto)
    assert ServicioBusqueda(conn).buscar(proyecto.id, "ETHICS")


def test_una_busqueda_vacia_no_devuelve_nada(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Una paleta que lo lista todo antes de escribir no orienta."""
    _poblar(conn, proyecto)
    assert ServicioBusqueda(conn).buscar(proyecto.id, "   ") == []


def test_el_resultado_de_una_anotacion_sabe_a_que_pagina_ir(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    _poblar(conn, proyecto)
    resultados = ServicioBusqueda(conn).buscar(proyecto.id, "independencia")
    anotacion = next(r for r in resultados if r.familia is Familia.ANOTACION)
    assert anotacion.documento_id is not None
    assert anotacion.pagina == 43


def test_la_busqueda_no_cruza_proyectos(conn: sqlite3.Connection) -> None:
    proyectos = RepositorioProyectos(conn)
    uno = proyectos.crear("CFA")
    otro = proyectos.crear("MSc")
    _poblar(conn, uno)

    assert ServicioBusqueda(conn).buscar(otro.id, "ethic") == []


# --- Plan semanal -----------------------------------------------------------


def test_el_plan_por_defecto_esta_desactivado(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Nada obligatorio: sin configurar, el calendario funciona igual."""
    plan = ServicioPlan(conn).cargar(proyecto.id)
    assert plan.activo is False
    assert len(plan.minutos) == 7


def test_guardar_y_recargar_el_plan(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    servicio = ServicioPlan(conn)
    servicio.guardar(
        proyecto.id, PlanSemanal(minutos=(30, 0, 45, 0, 60, 120, 0), activo=True)
    )
    plan = servicio.cargar(proyecto.id)
    assert plan.minutos == (30, 0, 45, 0, 60, 120, 0)
    assert plan.activo is True
    assert plan.minutos_semana == 255
    assert plan.para(date(2026, 8, 17)) == 30      # lunes
    assert plan.para(date(2026, 8, 22)) == 120     # sabado


def test_un_plan_corrupto_cae_al_defecto(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    from mukuwareru.nucleo.repositorios import RepositorioAjustes

    RepositorioAjustes(conn).establecer(
        "plan.minutos_por_dia", "mucho,poco", proyecto.id
    )
    assert len(ServicioPlan(conn).cargar(proyecto.id).minutos) == 7


def test_el_plan_recorta_valores_absurdos(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    servicio = ServicioPlan(conn)
    servicio.guardar(proyecto.id, PlanSemanal(minutos=(-30, 9999, 0, 0, 0, 0, 0)))
    minutos = servicio.cargar(proyecto.id).minutos
    assert minutos[0] == 0
    assert minutos[1] == 16 * 60


def test_los_planes_de_dos_proyectos_no_se_pisan(conn: sqlite3.Connection) -> None:
    proyectos = RepositorioProyectos(conn)
    uno = proyectos.crear("CFA")
    otro = proyectos.crear("MSc")
    servicio = ServicioPlan(conn)

    servicio.guardar(uno.id, PlanSemanal(minutos=(30,) * 7, activo=True))

    assert servicio.cargar(otro.id).activo is False
    assert servicio.cargar(uno.id).minutos[0] == 30


# --- Generacion -------------------------------------------------------------


def test_prever_respeta_los_minutos_de_cada_dia(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    servicio = ServicioPlan(conn)
    # Solo lunes y miercoles.
    servicio.guardar(proyecto.id, PlanSemanal(minutos=(60, 0, 90, 0, 0, 0, 0)))

    prevision = servicio.prever(proyecto.id, HOY, HOY + timedelta(days=6))

    assert [(f.weekday(), m) for f, m in prevision.bloques] == [(0, 60), (2, 90)]
    assert prevision.minutos == 150


def test_generar_dos_veces_no_duplica(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Volver a generar no debe llenar el calendario de duplicados."""
    servicio = ServicioPlan(conn)
    servicio.guardar(proyecto.id, PlanSemanal(minutos=(60,) * 7))

    primera = servicio.prever(proyecto.id, HOY, HOY + timedelta(days=6))
    assert servicio.generar(proyecto.id, primera) == 7

    segunda = servicio.prever(proyecto.id, HOY, HOY + timedelta(days=6))
    assert segunda.bloques == []
    assert segunda.omitidos == 7


def test_los_bloques_generados_llegan_al_calendario(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    servicio = ServicioPlan(conn)
    servicio.guardar(proyecto.id, PlanSemanal(minutos=(45, 0, 0, 0, 0, 0, 0)))
    servicio.generar(proyecto.id, servicio.prever(proyecto.id, HOY, HOY))

    bloques = RepositorioBloques(conn).listar(proyecto.id, HOY.isoformat(), HOY.isoformat())
    assert len(bloques) == 1
    assert bloques[0].duracion_min == 45
    assert bloques[0].hora_inicio is None


# --- Diagnostico ------------------------------------------------------------


def test_sin_hito_no_hay_ritmo_que_calcular(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    RepositorioModulos(conn).crear(materia.id, "Uno")

    diagnostico = ServicioPlan(conn).diagnostico(proyecto.id, HOY)

    assert diagnostico.pendientes == 1
    assert diagnostico.hay_fecha is False


def test_el_diagnostico_calcula_el_ritmo_necesario(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    modulos = RepositorioModulos(conn)
    for numero in range(10):
        modulos.crear(materia.id, f"Modulo {numero}")
    RepositorioHitos(conn).crear(proyecto.id, "Examen", HOY + timedelta(days=70))

    diagnostico = ServicioPlan(conn).diagnostico(proyecto.id, HOY)

    assert diagnostico.dias_restantes == 70
    assert diagnostico.titulo_hito == "Examen"
    # 10 modulos en 10 semanas.
    assert round(diagnostico.modulos_por_semana, 2) == 1.0
    assert diagnostico.hay_fecha is True


def test_el_diagnostico_compara_con_el_ritmo_real(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    modulos = RepositorioModulos(conn)
    for numero in range(4):
        modulos.crear(materia.id, f"Modulo {numero}")
    RepositorioHitos(conn).crear(proyecto.id, "Examen", HOY + timedelta(days=28))

    # Sin ninguna sesion, el ritmo real es cero y no se llega.
    diagnostico = ServicioPlan(conn).diagnostico(proyecto.id, HOY)
    assert diagnostico.horas_por_semana_reales == 0
    assert diagnostico.al_dia is False
    assert diagnostico.desviacion_horas > 0


# --- Repaso activo ----------------------------------------------------------


def _completar_hace(
    conn: sqlite3.Connection, materia_id: int, nombre: str, dias: int
) -> None:
    """Crea un modulo completado hace N dias, escribiendo la marca a mano."""
    modulo = RepositorioModulos(conn).crear(materia_id, nombre, completado=True)
    marca = (
        datetime.combine(HOY - timedelta(days=dias), time(10, 0))
        .astimezone()
        .isoformat(timespec="seconds")
    )
    conn.execute("UPDATE modulo SET completado_en = ? WHERE id = ?", (marca, modulo.id))


def test_sugiere_repasar_lo_completado_hace_semanas(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    _completar_hace(conn, materia.id, "Antiguo", 40)
    _completar_hace(conn, materia.id, "Reciente", 3)

    sugerencias = ServicioPlan(conn).sugerencias(proyecto.id, HOY)

    titulos = {s.titulo for s in sugerencias}
    assert "Antiguo" in titulos
    # Lo de hace tres dias todavia se recuerda: sugerirlo seria ruido.
    assert "Reciente" not in titulos


def test_un_modulo_sin_completar_no_se_sugiere(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    RepositorioModulos(conn).crear(materia.id, "Pendiente")

    assert ServicioPlan(conn).sugerencias(proyecto.id, HOY) == []


def test_las_sugerencias_no_pasan_del_limite(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    for numero in range(12):
        _completar_hace(conn, materia.id, f"Modulo {numero}", 40 + numero)

    assert len(ServicioPlan(conn).sugerencias(proyecto.id, HOY, limite=3)) == 3


def test_las_sugerencias_salen_de_lo_mas_antiguo_a_lo_mas_reciente(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Ordenar por el texto del motivo comparaba cadenas, no fechas.

    «Completado hace 25 dias» iba antes que «hace 9 dias» porque '2' < '9', de
    modo que el corte a `limite` se quedaba con las equivocadas.
    """
    # Las tres antiguedades estan elegidas para que el orden por texto difiera
    # del correcto: '100' < '22' < '25' como cadena, pero 100 > 25 > 22 como
    # numero. Con el orden viejo esto daria [Viejo, Nuevo, Medio].
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    for nombre, dias in [("Medio", 25), ("Viejo", 100), ("Nuevo", 22)]:
        _completar_hace(conn, materia.id, nombre, dias)

    sugerencias = ServicioPlan(conn).sugerencias(proyecto.id, HOY)
    assert [s.titulo for s in sugerencias] == ["Viejo", "Medio", "Nuevo"]


def test_el_limite_se_queda_con_lo_mas_antiguo(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    for nombre, dias in [("Medio", 25), ("Viejo", 100), ("Nuevo", 22)]:
        _completar_hace(conn, materia.id, nombre, dias)

    sugerencias = ServicioPlan(conn).sugerencias(proyecto.id, HOY, limite=2)
    assert [s.titulo for s in sugerencias] == ["Viejo", "Medio"]


def test_las_sugerencias_no_guardan_estado(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Se calculan: pedirlas dos veces da lo mismo y no crea filas."""
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    _completar_hace(conn, materia.id, "Antiguo", 40)
    servicio = ServicioPlan(conn)

    primera = servicio.sugerencias(proyecto.id, HOY)
    segunda = servicio.sugerencias(proyecto.id, HOY)
    assert primera == segunda


def test_una_sesion_reciente_alimenta_el_ritmo_real(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    RepositorioModulos(conn).crear(materia.id, "Uno")
    RepositorioHitos(conn).crear(proyecto.id, "Examen", HOY + timedelta(days=28))
    inicio = datetime.combine(HOY - timedelta(days=2), time(9, 0)).astimezone()
    RepositorioSesiones(conn).crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=inicio,
        duracion_seg=8 * 3600,
    )

    diagnostico = ServicioPlan(conn).diagnostico(proyecto.id, HOY)
    assert diagnostico.horas_por_semana_reales == 2.0  # 8 h repartidas en 4 semanas


def _nota_tocada_hace(
    conn: sqlite3.Connection, seccion_id: int, titulo: str, dias: int
) -> None:
    nota = RepositorioNotas(conn).crear(seccion_id, titulo=titulo, cuerpo="x")
    marca = (
        datetime.combine(HOY - timedelta(days=dias), time(10, 0))
        .astimezone()
        .isoformat(timespec="seconds")
    )
    conn.execute("UPDATE nota SET actualizado_en = ? WHERE id = ?", (marca, nota.id))


def test_las_notas_olvidadas_salen_de_la_mas_antigua_a_la_mas_nueva(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Antes se quedaba con las olvidadas MAS RECIENTES: el orden de la lista."""
    seccion = RepositorioCuadernos(conn).asegurar_por_defecto(proyecto.id)
    for titulo, dias in [("Reciente", 5), ("Justo", 30), ("Vieja", 90), ("Media", 45)]:
        _nota_tocada_hace(conn, seccion.id, titulo, dias)

    sugerencias = ServicioPlan(conn).sugerencias(proyecto.id, HOY, limite=2)
    assert [s.titulo for s in sugerencias] == ["Vieja", "Media"]

    todas = ServicioPlan(conn).sugerencias(proyecto.id, HOY)
    # El dia 30 cuenta como olvidada; la de hace 5 dias no.
    assert [s.titulo for s in todas] == ["Vieja", "Media", "Justo"]


def test_las_listas_de_notas_no_cargan_el_cuerpo(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """El cuerpo puede llevar imagenes en base64; solo `obtener` lo trae."""
    seccion = RepositorioCuadernos(conn).asegurar_por_defecto(proyecto.id)
    notas = RepositorioNotas(conn)
    creada = notas.crear(seccion.id, titulo="Con imagen", cuerpo="<img src='data:...'>texto")

    listada = notas.listar_del_proyecto(proyecto.id)[0]
    assert listada.nota.cuerpo == ""
    assert "texto" in listada.nota.cuerpo_plano
    assert "img" in notas.obtener(creada.id).cuerpo


def test_los_modulos_del_proyecto_se_agrupan_en_una_consulta(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materias = RepositorioMaterias(conn)
    modulos = RepositorioModulos(conn)
    ethics = materias.crear(proyecto.id, "Ethics")
    quant = materias.crear(proyecto.id, "Quant")
    materias.crear(proyecto.id, "Vacia")
    modulos.crear(ethics.id, "B", orden=1)
    modulos.crear(ethics.id, "A", orden=0)
    modulos.crear(quant.id, "Q")

    agrupados = modulos.listar_del_proyecto(proyecto.id)
    assert [m.nombre for m in agrupados[ethics.id]] == ["A", "B"]
    assert [m.nombre for m in agrupados[quant.id]] == ["Q"]
    assert len(agrupados) == 2