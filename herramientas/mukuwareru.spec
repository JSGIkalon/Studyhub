# -*- mode: python ; coding: utf-8 -*-
"""Especificacion de PyInstaller para Mukuwareru.

Modo *onedir* deliberado: *onefile* descomprime todo Qt en %TEMP% en cada
arranque (2-5 s), lo que contradice el requisito de que la aplicacion abra
rapido. Los datos del usuario viven fuera del bundle, en ``datos/``.

    pyinstaller herramientas/mukuwareru.spec --noconfirm
"""

import re
import tempfile
from pathlib import Path

RAIZ = Path(SPECPATH).parent  # noqa: F821 (SPECPATH lo inyecta PyInstaller)

# La version se lee del paquete en lugar de importarlo: importar mukuwareru aqui
# arrastraria PySide6 al proceso de PyInstaller sin ninguna necesidad.
VERSION = re.search(
    r'__version__ = "([^"]+)"',
    (RAIZ / "mukuwareru" / "__init__.py").read_text(encoding="utf-8"),
).group(1)
_NUMEROS = tuple(int(parte) for parte in VERSION.split(".")) + (0,)


def _recurso_de_version() -> str:
    """Escribe el recurso VERSIONINFO de Windows y devuelve su ruta.

    Sin esto, el ejecutable sale sin metadatos: Propiedades -> Detalles aparece
    en blanco y el Administrador de tareas lo lista solo por el nombre de
    archivo. Se genera aqui para que la version no haya que repetirla a mano.
    """
    plantilla = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_NUMEROS}, prodvers={_NUMEROS},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable('040a04b0', [
      StringStruct('CompanyName', 'Mukuwareru'),
      StringStruct('FileDescription', 'Mukuwareru - centro de estudio'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'Mukuwareru'),
      StringStruct('OriginalFilename', 'Mukuwareru.exe'),
      StringStruct('ProductName', 'Mukuwareru'),
      StringStruct('ProductVersion', '{VERSION}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [0x040a, 1200])]),  # espanol
  ]
)
"""
    ruta = Path(tempfile.gettempdir()) / "mukuwareru-version.txt"
    ruta.write_text(plantilla, encoding="utf-8")
    return str(ruta)

# Recursos leidos en tiempo de ejecucion con importlib.resources.
datos = [
    (str(RAIZ / "mukuwareru" / "nucleo" / "bd" / "migraciones" / "*.sql"),
     "mukuwareru/nucleo/bd/migraciones"),
    (str(RAIZ / "mukuwareru" / "ui" / "tema" / "oscuro.qss"), "mukuwareru/ui/tema"),
    (str(RAIZ / "mukuwareru" / "recursos" / "iconos" / "*.svg"), "mukuwareru/recursos/iconos"),
    (str(RAIZ / "mukuwareru" / "recursos" / "mukuwareru.svg"), "mukuwareru/recursos"),
    # El logotipo de mapa de bits es opcional: si no esta, se usa el SVG.
    *(
        [(str(logo), "mukuwareru/recursos")]
        if (logo := RAIZ / "mukuwareru" / "recursos" / "logo.png").exists()
        else []
    ),
    # El caminante del timeline: se genera con `preparar_personaje.py`. Tambien
    # opcional; sin el, el timeline pinta un marcador redondo.
    *(
        [(str(personaje), "mukuwareru/recursos")]
        if (personaje := RAIZ / "mukuwareru" / "recursos" / "personaje.png").exists()
        else []
    ),
]

# Modulos Qt que la aplicacion no usa y que pesan decenas de MB.
excluidos = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtMultimedia",
    "PySide6.Qt3DCore",
    "PySide6.QtDataVisualization",
    "pandas",
    "numpy",
    "matplotlib",
    "tkinter",
]

analisis = Analysis(  # noqa: F821
    [str(RAIZ / "mukuwareru" / "__main__.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datos,
    hiddenimports=[
        "mukuwareru.nucleo.bd.migraciones",
        "mukuwareru.recursos",
        "mukuwareru.recursos.iconos",
    ],
    excludes=excluidos,
    noarchive=False,
)

pyz = PYZ(analisis.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    analisis.scripts,
    [],
    exclude_binaries=True,
    name="Mukuwareru",
    console=False,          # sin consola: es una aplicacion de escritorio
    icon=str(RAIZ / "mukuwareru" / "recursos" / "mukuwareru.ico"),
    version=_recurso_de_version(),
    debug=False,
    strip=False,
    upx=False,
)

COLLECT(  # noqa: F821
    exe,
    analisis.binaries,
    analisis.datas,
    strip=False,
    upx=False,
    name="Mukuwareru",
)
