"""Migraciones y estructura del esquema."""

from __future__ import annotations

import sqlite3

from mukuwareru.nucleo.bd import conexion as bd
from mukuwareru.nucleo.bd.migrador import migraciones_disponibles, migrar, version_actual

TABLAS_ESPERADAS = {
    "proyecto",
    "materia",
    "modulo",
    "documento",
    "sesion",
    "sesion_materia",
    "anotacion",
    "ajuste",
    "esquema_version",
    # 002 · notas sueltas
    "cuaderno",
    "seccion",
    "nota",
    "etiqueta",
    "nota_etiqueta",
    "nota_vinculo",
    # 007 · grafo de dependencias
    "grafo_nodo",
    "grafo_arista",
}


def test_las_migraciones_estan_numeradas_sin_saltos() -> None:
    versiones = [m.version for m in migraciones_disponibles()]
    assert versiones == list(range(1, len(versiones) + 1))


def test_se_crean_todas_las_tablas(conn: sqlite3.Connection) -> None:
    filas = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert {f["name"] for f in filas} >= TABLAS_ESPERADAS


def test_migrar_es_idempotente(conn: sqlite3.Connection) -> None:
    antes = version_actual(conn)
    assert migrar(conn) == antes


def test_las_claves_foraneas_estan_activas(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_borrar_un_proyecto_arrastra_sus_materias(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO proyecto (id, nombre, creado_en) VALUES (1, 'Prueba', '2026-01-01T00:00:00')"
    )
    conn.execute("INSERT INTO materia (proyecto_id, nombre) VALUES (1, 'Ethics')")
    conn.execute("DELETE FROM proyecto WHERE id = 1")
    assert conn.execute("SELECT COUNT(*) FROM materia").fetchone()[0] == 0


def test_la_006_conserva_las_evaluaciones_ya_guardadas() -> None:
    """La 006 recrea `evaluacion` para poder admitir pendientes.

    Recrear una tabla es la operacion que mas facilmente pierde datos, asi que
    se comprueba sobre una base migrada solo hasta la 005: se escribe una
    evaluacion con su desglose, se aplica el resto y todo tiene que seguir ahi,
    con el mismo id.
    """
    cx = sqlite3.connect(":memory:")
    cx.row_factory = sqlite3.Row
    cx.isolation_level = None
    try:
        for migracion in migraciones_disponibles():
            if migracion.version > 5:
                break
            cx.executescript(migracion.sql)
            cx.execute(
                "CREATE TABLE IF NOT EXISTS esquema_version (version INTEGER NOT NULL)"
            )
            cx.execute(
                "INSERT INTO esquema_version (version) VALUES (?)", (migracion.version,)
            )

        cx.execute(
            "INSERT INTO proyecto (id, nombre, creado_en) "
            "VALUES (1, 'CFA', '2026-01-01T00:00:00')"
        )
        cx.execute("INSERT INTO materia (id, proyecto_id, nombre) VALUES (1, 1, 'Ethics')")
        cx.execute(
            "INSERT INTO evaluacion (id, proyecto_id, titulo, fecha, puntos_obtenidos, "
            "puntos_posibles, peso, creado_en) "
            "VALUES (7, 1, 'Mock 1', '2026-05-01', 38, 50, 0, '2026-05-01T00:00:00')"
        )
        cx.execute(
            "INSERT INTO evaluacion_materia VALUES (7, 1, 14, 18)"
        )

        migrar(cx)

        fila = cx.execute("SELECT * FROM evaluacion WHERE id = 7").fetchone()
        assert fila["titulo"] == "Mock 1"
        assert fila["puntos_obtenidos"] == 38
        assert fila["peso"] == 0
        # El desglose sigue colgando de la misma evaluacion.
        assert cx.execute(
            "SELECT COUNT(*) FROM evaluacion_materia WHERE evaluacion_id = 7"
        ).fetchone()[0] == 1
        # Y ahora caben pendientes, que es para lo que se recreo la tabla.
        cx.execute(
            "INSERT INTO evaluacion (proyecto_id, titulo, fecha, puntos_obtenidos, "
            "puntos_posibles, peso, creado_en) "
            "VALUES (1, 'Final', '2026-12-01', NULL, 100, 50, '2026-09-01T00:00:00')"
        )
    finally:
        cx.close()


def test_una_base_nueva_queda_en_la_ultima_version() -> None:
    cx = bd.abrir(":memory:")
    try:
        assert version_actual(cx) == max(m.version for m in migraciones_disponibles())
    finally:
        cx.close()
