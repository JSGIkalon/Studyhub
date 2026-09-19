"""Acceso a las tablas ``grafo_nodo`` y ``grafo_arista``.

Aqui no se calcula ningun estado: un nodo se guarda y se lee tal cual, que es
una referencia y una posicion. «Bloqueado» o «En curso» los deduce
``ServicioGrafo`` cruzando estas filas con el progreso real.
"""

from __future__ import annotations

import sqlite3

from mukuwareru.nucleo.modelos.entidades import AristaGrafo, DestinoNodo, NodoGrafo
from mukuwareru.nucleo.repositorios.base import Repositorio, a_fecha_hora, ahora_iso

_CAMPOS = """
    id, proyecto_id, materia_id, modulo_id, hito_id, evaluacion_id,
    x, y, etiqueta, nota, creado_en
"""

# Nombre de la columna que corresponde a cada destino. Vive aqui, en el unico
# archivo que escribe SQL, para que el servicio no tenga que saber como se
# llaman las columnas.
_COLUMNA: dict[DestinoNodo, str] = {
    DestinoNodo.MATERIA: "materia_id",
    DestinoNodo.MODULO: "modulo_id",
    DestinoNodo.HITO: "hito_id",
    DestinoNodo.EVALUACION: "evaluacion_id",
}


class RepositorioGrafo(Repositorio):
    """Nodos y aristas del grafo de dependencias de un proyecto."""

    # -- Nodos -----------------------------------------------------------------

    def listar_nodos(self, proyecto_id: int) -> list[NodoGrafo]:
        """Todos los nodos del proyecto, en orden de creacion."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM grafo_nodo WHERE proyecto_id = ? ORDER BY id",
            (proyecto_id,),
        ).fetchall()
        return [_a_nodo(f) for f in filas]

    def obtener_nodo(self, nodo_id: int) -> NodoGrafo | None:
        """Un nodo por id, o ``None`` si ya no existe."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM grafo_nodo WHERE id = ?", (nodo_id,)
        ).fetchone()
        return _a_nodo(fila) if fila else None

    def nodo_de(self, destino: DestinoNodo, objeto_id: int) -> NodoGrafo | None:
        """El nodo que representa esa entidad, si ya esta en algun lienzo."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM grafo_nodo WHERE {_COLUMNA[destino]} = ?",
            (objeto_id,),
        ).fetchone()
        return _a_nodo(fila) if fila else None

    def crear_nodo(
        self,
        proyecto_id: int,
        destino: DestinoNodo,
        objeto_id: int,
        *,
        x: float = 0.0,
        y: float = 0.0,
        etiqueta: str | None = None,
    ) -> NodoGrafo:
        """Coloca una entidad en el lienzo, o mueve la que ya estaba.

        Soltar dos veces la misma materia **no** crea un segundo nodo: lo impide
        el indice unico parcial, y aqui se aprovecha para mover el existente. Es
        el comportamiento que espera quien arrastra: la materia acaba donde la
        solto, haya estado o no antes en el lienzo.
        """
        existente = self.nodo_de(destino, objeto_id)
        if existente is not None:
            self.mover_nodo(existente.id, x, y)
            existente.x, existente.y = x, y
            return existente

        columna = _COLUMNA[destino]
        cursor = self._cx.execute(
            f"""
            INSERT INTO grafo_nodo (proyecto_id, {columna}, x, y, etiqueta, creado_en)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (proyecto_id, objeto_id, x, y, etiqueta, ahora_iso()),
        )
        creado = self.obtener_nodo(int(cursor.lastrowid or 0))
        assert creado is not None
        return creado

    def mover_nodo(self, nodo_id: int, x: float, y: float) -> None:
        """Fija la posicion del nodo, en coordenadas de la escena."""
        self._cx.execute(
            "UPDATE grafo_nodo SET x = ?, y = ? WHERE id = ?", (x, y, nodo_id)
        )

    def renombrar_nodo(self, nodo_id: int, etiqueta: str | None) -> None:
        """Alias del nodo dentro del grafo. ``None`` vuelve al nombre real."""
        self._cx.execute(
            "UPDATE grafo_nodo SET etiqueta = ? WHERE id = ?", (etiqueta or None, nodo_id)
        )

    def fijar_nota(self, nodo_id: int, nota: str | None) -> None:
        """Comentario libre sobre el nodo."""
        self._cx.execute(
            "UPDATE grafo_nodo SET nota = ? WHERE id = ?", (nota or None, nodo_id)
        )

    def eliminar_nodo(self, nodo_id: int) -> None:
        """Quita el nodo del lienzo. La entidad a la que apuntaba no se toca."""
        self._cx.execute("DELETE FROM grafo_nodo WHERE id = ?", (nodo_id,))

    def ocupados(self, proyecto_id: int) -> dict[DestinoNodo, set[int]]:
        """Que entidades del proyecto ya estan colocadas, por tipo.

        Es lo que el panel lateral necesita para no volver a ofrecer lo que ya
        se ve en el lienzo: la forma mas barata de que nadie intente duplicar.
        """
        colocados: dict[DestinoNodo, set[int]] = {d: set() for d in DestinoNodo}
        for nodo in self.listar_nodos(proyecto_id):
            colocados[nodo.destino].add(nodo.objeto_id)
        return colocados

    # -- Aristas ---------------------------------------------------------------

    def listar_aristas(self, proyecto_id: int) -> list[AristaGrafo]:
        """Aristas del proyecto. El JOIN evita mezclar grafos de proyectos."""
        filas = self._cx.execute(
            """
            SELECT a.destino, a.origen, a.grupo, a.creado_en
              FROM grafo_arista a
              JOIN grafo_nodo n ON n.id = a.destino
             WHERE n.proyecto_id = ?
             ORDER BY a.destino, a.grupo, a.origen
            """,
            (proyecto_id,),
        ).fetchall()
        return [_a_arista(f) for f in filas]

    def entrantes(self, nodo_id: int) -> list[AristaGrafo]:
        """Prerrequisitos de un nodo, agrupados por su columna ``grupo``."""
        filas = self._cx.execute(
            """
            SELECT destino, origen, grupo, creado_en
              FROM grafo_arista WHERE destino = ? ORDER BY grupo, origen
            """,
            (nodo_id,),
        ).fetchall()
        return [_a_arista(f) for f in filas]

    def proximo_grupo(self, destino: int) -> int:
        """``MAX(grupo) + 1`` del destino, o 1. Una arista nueva es un Y."""
        fila = self._cx.execute(
            "SELECT MAX(grupo) FROM grafo_arista WHERE destino = ?", (destino,)
        ).fetchone()
        return int(fila[0]) + 1 if fila and fila[0] is not None else 1

    def crear_arista(self, destino: int, origen: int, grupo: int) -> AristaGrafo:
        """Anade un prerrequisito. Repetirlo no hace nada.

        El ``DO NOTHING`` deja que dibujar dos veces la misma flecha sea
        inofensivo, en vez de un ``IntegrityError`` que la interfaz tendria que
        traducir.
        """
        marca = ahora_iso()
        self._cx.execute(
            """
            INSERT INTO grafo_arista (destino, origen, grupo, creado_en)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (destino, origen) DO NOTHING
            """,
            (destino, origen, max(1, grupo), marca),
        )
        return AristaGrafo(
            destino=destino, origen=origen, grupo=max(1, grupo),
            creado_en=a_fecha_hora(marca),
        )

    def fijar_grupo(self, destino: int, origen: int, grupo: int) -> None:
        """Cambia de grupo un prerrequisito: es lo que convierte un Y en un O."""
        self._cx.execute(
            "UPDATE grafo_arista SET grupo = ? WHERE destino = ? AND origen = ?",
            (max(1, grupo), destino, origen),
        )

    def eliminar_arista(self, destino: int, origen: int) -> None:
        """Quita un prerrequisito."""
        self._cx.execute(
            "DELETE FROM grafo_arista WHERE destino = ? AND origen = ?",
            (destino, origen),
        )

    def contar(self, proyecto_id: int) -> tuple[int, int]:
        """``(nodos, aristas)`` del proyecto. Para el estado vacio de la vista."""
        nodos = self._cx.execute(
            "SELECT COUNT(*) FROM grafo_nodo WHERE proyecto_id = ?", (proyecto_id,)
        ).fetchone()
        aristas = self._cx.execute(
            """
            SELECT COUNT(*) FROM grafo_arista a
              JOIN grafo_nodo n ON n.id = a.destino
             WHERE n.proyecto_id = ?
            """,
            (proyecto_id,),
        ).fetchone()
        return int(nodos[0]), int(aristas[0])


def _a_nodo(fila: sqlite3.Row) -> NodoGrafo:
    return NodoGrafo(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        x=float(fila["x"]),
        y=float(fila["y"]),
        materia_id=fila["materia_id"],
        modulo_id=fila["modulo_id"],
        hito_id=fila["hito_id"],
        evaluacion_id=fila["evaluacion_id"],
        etiqueta=fila["etiqueta"],
        nota=fila["nota"],
        creado_en=a_fecha_hora(fila["creado_en"]),
    )


def _a_arista(fila: sqlite3.Row) -> AristaGrafo:
    return AristaGrafo(
        destino=fila["destino"],
        origen=fila["origen"],
        grupo=int(fila["grupo"]),
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
