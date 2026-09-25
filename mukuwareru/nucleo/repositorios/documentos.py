"""Acceso a la tabla ``documento``."""

from __future__ import annotations

import sqlite3

from mukuwareru.nucleo.modelos.entidades import Documento
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha_hora, ahora_iso

_CAMPOS = """
    id, proyecto_id, ruta_relativa, nombre, huella, paginas, bytes,
    pagina_actual, zoom, scroll_x, scroll_y, abierto_en, agregado_en
"""


class RepositorioDocumentos(Repositorio):
    """Consultas y escrituras sobre los PDFs de la biblioteca."""

    # -- Lectura -----------------------------------------------------------

    def listar(self, proyecto_id: int) -> list[Documento]:
        """Todos los PDFs del proyecto, por nombre."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM documento WHERE proyecto_id = ? ORDER BY nombre",
            (proyecto_id,),
        ).fetchall()
        return [_a_documento(f) for f in filas]

    def obtener(self, documento_id: int) -> Documento | None:
        """Un documento por id."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM documento WHERE id = ?", (documento_id,)
        ).fetchone()
        return _a_documento(fila) if fila else None

    def recientes(self, proyecto_id: int, limite: int = 5) -> list[Documento]:
        """PDFs abiertos mas recientemente. Los nunca abiertos quedan fuera."""
        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS} FROM documento
             WHERE proyecto_id = ? AND abierto_en IS NOT NULL
             ORDER BY abierto_en DESC
             LIMIT ?
            """,
            (proyecto_id, limite),
        ).fetchall()
        return [_a_documento(f) for f in filas]

    def contar(self, proyecto_id: int) -> int:
        """Numero de PDFs registrados en el proyecto."""
        fila = self._cx.execute(
            "SELECT COUNT(*) FROM documento WHERE proyecto_id = ?", (proyecto_id,)
        ).fetchone()
        return int(fila[0])

    def por_huella(self, proyecto_id: int, huella: str) -> Documento | None:
        """Busca por contenido. Asi un PDF renombrado conserva su progreso."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM documento WHERE proyecto_id = ? AND huella = ?",
            (proyecto_id, huella),
        ).fetchone()
        return _a_documento(fila) if fila else None

    # -- Escritura ---------------------------------------------------------

    def crear(
        self,
        proyecto_id: int,
        *,
        ruta_relativa: str,
        nombre: str,
        huella: str,
        bytes_: int,
    ) -> Documento:
        """Registra un PDF recien descubierto."""
        cursor = self._cx.execute(
            """
            INSERT INTO documento
                (proyecto_id, ruta_relativa, nombre, huella, bytes, agregado_en)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (proyecto_id, ruta_relativa, nombre, huella, bytes_, ahora_iso()),
        )
        creado = self.obtener(int(cursor.lastrowid or 0))
        assert creado is not None
        return creado

    def mover(self, documento_id: int, *, ruta_relativa: str, nombre: str) -> None:
        """Actualiza la ubicacion de un PDF que se renombro o se movio."""
        self._cx.execute(
            "UPDATE documento SET ruta_relativa = ?, nombre = ? WHERE id = ?",
            (ruta_relativa, nombre, documento_id),
        )

    def actualizar_archivo(self, documento_id: int, *, huella: str, bytes_: int) -> None:
        """Refresca huella y tamano cuando el archivo cambio en disco."""
        self._cx.execute(
            "UPDATE documento SET huella = ?, bytes = ?, paginas = NULL WHERE id = ?",
            (huella, bytes_, documento_id),
        )

    def establecer_paginas(self, documento_id: int, paginas: int) -> None:
        """Guarda el numero de paginas, que solo se conoce al abrir el PDF."""
        self._cx.execute(
            "UPDATE documento SET paginas = ? WHERE id = ?", (paginas, documento_id)
        )

    def guardar_posicion(
        self,
        documento_id: int,
        *,
        pagina: int,
        zoom: float,
        scroll_x: float = 0.0,
        scroll_y: float = 0.0,
    ) -> None:
        """Persiste donde se quedo la lectura."""
        self._cx.execute(
            """
            UPDATE documento
               SET pagina_actual = ?, zoom = ?, scroll_x = ?, scroll_y = ?
             WHERE id = ?
            """,
            (pagina, zoom, scroll_x, scroll_y, documento_id),
        )

    def marcar_abierto(self, documento_id: int) -> None:
        """Registra la apertura, que es lo que ordena «ultimos PDFs»."""
        self._cx.execute(
            "UPDATE documento SET abierto_en = ? WHERE id = ?", (ahora_iso(), documento_id)
        )

    def eliminar(self, documento_id: int) -> None:
        """Borra el documento y, en cascada, sus anotaciones."""
        self._cx.execute("DELETE FROM documento WHERE id = ?", (documento_id,))


def _a_documento(fila: sqlite3.Row) -> Documento:
    return Documento(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        ruta_relativa=fila["ruta_relativa"],
        nombre=fila["nombre"],
        huella=fila["huella"],
        paginas=fila["paginas"],
        bytes=fila["bytes"],
        pagina_actual=fila["pagina_actual"],
        zoom=fila["zoom"],
        scroll_x=fila["scroll_x"],
        scroll_y=fila["scroll_y"],
        abierto_en=a_fecha_hora(fila["abierto_en"]),
        agregado_en=a_fecha_hora(fila["agregado_en"]),
    )
