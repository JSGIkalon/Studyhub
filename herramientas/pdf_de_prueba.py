"""Genera PDFs de prueba con texto realmente extraible.

    python herramientas/pdf_de_prueba.py [carpeta] [--paginas N]

Sirven para desarrollar la biblioteca, el visor y las anotaciones sin depender
de material con derechos de autor.

Se emite PDF crudo con las fuentes base-14 (Helvetica) en lugar de usar
``QPdfWriter``: este ultimo rasteriza el texto sin un mapeo a Unicode utilizable,
de modo que ``QPdfDocument.getAllText()`` devuelve cadena vacia y no se puede
probar ni la busqueda ni la seleccion de texto.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

ANCHO = 595   # A4 en puntos
ALTO = 842
MARGEN = 64

_TEMAS = [
    (
        "Quantitative Methods",
        "Sampling and Estimation",
        [
            "Al investigar rara vez es posible recoger datos de toda la poblacion. "
            "En su lugar se toma una muestra y se usan sus estadisticos para "
            "inferir los parametros poblacionales.",
            "La distribucion muestral de un estadistico es la distribucion de "
            "probabilidad de ese estadistico sobre todas las muestras posibles "
            "del mismo tamano.",
            "El teorema central del limite establece que la media muestral se "
            "aproxima a una distribucion normal a medida que crece el tamano de "
            "la muestra, con independencia de la distribucion de la poblacion.",
            "El error estandar de la media es la desviacion tipica de la "
            "distribucion muestral y decrece con la raiz del tamano muestral.",
        ],
    ),
    (
        "Fixed Income",
        "Bond Valuation",
        [
            "El precio de un bono es el valor presente de sus flujos de caja "
            "futuros, descontados a la tasa de rendimiento exigida por el mercado.",
            "La duracion mide la sensibilidad del precio ante cambios en los tipos "
            "de interes. La convexidad captura la curvatura que la duracion no "
            "recoge.",
            "Un bono cotiza con prima cuando su cupon supera el rendimiento "
            "exigido, y con descuento en el caso contrario.",
        ],
    ),
    (
        "Ethics",
        "Code of Ethics and Standards",
        [
            "Los miembros deben actuar con integridad, competencia, diligencia y "
            "respeto, de forma etica con el publico, los clientes y los "
            "empleadores.",
            "La Norma I trata del profesionalismo: conocimiento de la ley, "
            "independencia y objetividad, tergiversacion y mala conducta.",
            "El interes del cliente siempre precede al interes del empleador y al "
            "interes personal del profesional.",
        ],
    ),
]


class _Escritor:
    """Constructor minimo de archivos PDF con objetos numerados."""

    def __init__(self) -> None:
        self._objetos: list[bytes] = []

    def agregar(self, cuerpo: bytes) -> int:
        """Anade un objeto y devuelve su numero."""
        self._objetos.append(cuerpo)
        return len(self._objetos)

    def reservar(self) -> int:
        """Reserva un numero de objeto para rellenarlo despues."""
        return self.agregar(b"")

    def rellenar(self, numero: int, cuerpo: bytes) -> None:
        """Define el cuerpo de un objeto previamente reservado."""
        self._objetos[numero - 1] = cuerpo

    def construir(self, raiz: int) -> bytes:
        """Serializa el archivo completo con su tabla de referencias cruzadas."""
        salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posiciones = []
        for numero, cuerpo in enumerate(self._objetos, start=1):
            posiciones.append(len(salida))
            salida += f"{numero} 0 obj\n".encode() + cuerpo + b"\nendobj\n"

        inicio_xref = len(salida)
        total = len(self._objetos) + 1
        salida += f"xref\n0 {total}\n".encode()
        salida += b"0000000000 65535 f \n"
        for posicion in posiciones:
            salida += f"{posicion:010d} 00000 n \n".encode()
        salida += (
            f"trailer\n<< /Size {total} /Root {raiz} 0 R >>\n"
            f"startxref\n{inicio_xref}\n%%EOF\n"
        ).encode()
        return bytes(salida)


def _texto_pdf(cadena: str) -> bytes:
    """Codifica una cadena como literal PDF en WinAnsi."""
    crudo = cadena.encode("cp1252", errors="replace")
    for original, sustituto in ((b"\\", b"\\\\"), (b"(", b"\\("), (b")", b"\\)")):
        crudo = crudo.replace(original, sustituto)
    return crudo


def _contenido(tema: str, titulo: str, parrafos: list[str], numero: int, total: int) -> bytes:
    """Genera el flujo de contenido de una pagina."""
    lineas: list[tuple[str, int, str]] = [
        (tema, 20, "F2"),
        ("", 8, "F1"),
        (f"{numero}. {titulo}", 15, "F2"),
        ("", 6, "F1"),
        ("LEARNING OUTCOME STATEMENT", 10, "F2"),
        ("", 10, "F1"),
    ]
    for parrafo in parrafos:
        lineas.extend((linea, 11, "F1") for linea in textwrap.wrap(parrafo, width=78))
        lineas.append(("", 8, "F1"))

    lineas.append(("", 12, "F1"))
    lineas.append((f"Pagina {numero} de {total}", 9, "F1"))

    flujo = bytearray(b"BT\n")
    y = ALTO - MARGEN
    for texto, tamano, fuente in lineas:
        y -= tamano + 5
        if texto:
            flujo += (
                f"/{fuente} {tamano} Tf\n1 0 0 1 {MARGEN} {y} Tm\n".encode()
                + b"("
                + _texto_pdf(texto)
                + b") Tj\n"
            )
    flujo += b"ET\n"
    return bytes(flujo)


def generar(destino: Path, tema: str, titulo: str, parrafos: list[str], paginas: int) -> Path:
    """Escribe un PDF de ``paginas`` paginas con texto seleccionable."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritor = _Escritor()

    catalogo = escritor.reservar()
    arbol = escritor.reservar()
    normal = escritor.agregar(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>"
    )
    negrita = escritor.agregar(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        b"/Encoding /WinAnsiEncoding >>"
    )

    hojas = []
    for numero in range(1, paginas + 1):
        flujo = _contenido(tema, titulo, parrafos, numero, paginas)
        contenido = escritor.agregar(
            f"<< /Length {len(flujo)} >>\nstream\n".encode() + flujo + b"endstream"
        )
        hoja = escritor.reservar()
        escritor.rellenar(
            hoja,
            (
                f"<< /Type /Page /Parent {arbol} 0 R "
                f"/MediaBox [0 0 {ANCHO} {ALTO}] "
                f"/Resources << /Font << /F1 {normal} 0 R /F2 {negrita} 0 R >> >> "
                f"/Contents {contenido} 0 R >>"
            ).encode(),
        )
        hojas.append(hoja)

    referencias = " ".join(f"{h} 0 R" for h in hojas)
    escritor.rellenar(
        arbol, f"<< /Type /Pages /Kids [{referencias}] /Count {len(hojas)} >>".encode()
    )
    escritor.rellenar(catalogo, f"<< /Type /Catalog /Pages {arbol} 0 R >>".encode())

    destino.write_bytes(escritor.construir(catalogo))
    return destino


def main() -> int:
    """Genera el juego completo de PDFs de prueba."""
    analizador = argparse.ArgumentParser(description="Genera PDFs de prueba.")
    analizador.add_argument("carpeta", nargs="?", default="Library/Pruebas")
    analizador.add_argument("--paginas", type=int, default=6)
    argumentos = analizador.parse_args()
    carpeta = Path(argumentos.carpeta)

    for tema, titulo, parrafos in _TEMAS:
        ruta = generar(
            carpeta / f"{tema} - {titulo}.pdf", tema, titulo, parrafos, argumentos.paginas
        )
        print(f"  {ruta}  ({ruta.stat().st_size // 1024} KB)")

    # Uno dentro de una subcarpeta, para comprobar el escaneo recursivo.
    tema, titulo, parrafos = _TEMAS[0]
    ruta = generar(carpeta / "Repaso" / f"{titulo} - repaso.pdf", tema, titulo, parrafos, 3)
    print(f"  {ruta}  ({ruta.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
