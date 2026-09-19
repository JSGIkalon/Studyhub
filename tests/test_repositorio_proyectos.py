"""Repositorio de proyectos."""

from __future__ import annotations

from datetime import date

from mukuwareru.nucleo.repositorios import RepositorioProyectos


def test_crear_y_listar(repo_proyectos: RepositorioProyectos) -> None:
    creado = repo_proyectos.crear("CFA Level I", fecha_objetivo=date(2026, 11, 13))
    assert creado.id > 0
    assert creado.fecha_objetivo == date(2026, 11, 13)
    assert [p.nombre for p in repo_proyectos.listar()] == ["CFA Level I"]


def test_el_orden_se_asigna_de_forma_incremental(repo_proyectos: RepositorioProyectos) -> None:
    primero = repo_proyectos.crear("Uno")
    segundo = repo_proyectos.crear("Dos")
    assert (primero.orden, segundo.orden) == (0, 1)


def test_los_archivados_quedan_fuera_por_defecto(repo_proyectos: RepositorioProyectos) -> None:
    proyecto = repo_proyectos.crear("Antiguo")
    proyecto.archivado = True
    repo_proyectos.actualizar(proyecto)

    assert repo_proyectos.listar() == []
    assert len(repo_proyectos.listar(incluir_archivados=True)) == 1


def test_actualizar_conserva_los_cambios(repo_proyectos: RepositorioProyectos) -> None:
    proyecto = repo_proyectos.crear("Borrador")
    proyecto.nombre = "MSc Financial Engineering"
    proyecto.color = "#3E63DD"
    repo_proyectos.actualizar(proyecto)

    recuperado = repo_proyectos.obtener(proyecto.id)
    assert recuperado is not None
    assert (recuperado.nombre, recuperado.color) == ("MSc Financial Engineering", "#3E63DD")


def test_obtener_inexistente_devuelve_none(repo_proyectos: RepositorioProyectos) -> None:
    assert repo_proyectos.obtener(999) is None


def test_reordenar_reasigna_todas_las_posiciones(
    repo_proyectos: RepositorioProyectos,
) -> None:
    """Se reasigna 0..n-1 y no se intercambian dos valores.

    En bases antiguas ``orden`` puede tener empates, y un intercambio dejaria
    el resultado a merced del desempate por nombre.
    """
    uno = repo_proyectos.crear("Uno")
    dos = repo_proyectos.crear("Dos")
    tres = repo_proyectos.crear("Tres")

    repo_proyectos.reordenar([dos.id, tres.id, uno.id])

    assert [p.nombre for p in repo_proyectos.listar()] == ["Dos", "Tres", "Uno"]
    assert [p.orden for p in repo_proyectos.listar()] == [0, 1, 2]


def test_contar_dependencias_de_un_proyecto_vacio(
    repo_proyectos: RepositorioProyectos,
) -> None:
    proyecto = repo_proyectos.crear("Vacio")
    cuentas = repo_proyectos.contar_dependencias(proyecto.id)
    assert set(cuentas) == {"materias", "modulos", "documentos", "sesiones", "anotaciones"}
    assert sum(cuentas.values()) == 0


def test_dias_restantes(repo_proyectos: RepositorioProyectos) -> None:
    proyecto = repo_proyectos.crear("Examen", fecha_objetivo=date(2026, 11, 13))
    assert proyecto.dias_restantes(date(2026, 8, 16)) == 89
    assert repo_proyectos.crear("Sin fecha").dias_restantes(date(2026, 8, 16)) is None
