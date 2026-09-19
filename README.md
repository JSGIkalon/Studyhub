# Mukuwareru

*報われる — «ser recompensado».*

Centro de estudio personal para Windows. Multi-proyecto, completamente offline,
sin nube y sin servidor. Unifica temporizador, biblioteca PDF, visor de estudio,
notas, progreso y estadisticas en una sola ventana, en lugar de repartirlos
entre una hoja de calculo y media docena de aplicaciones.

Python 3.12 · PySide6 (Qt 6) · SQLite · Windows 11

## Que hace

- **Biblioteca y visor PDF** — documentos por proyecto, con lectura a una o dos
  paginas, seleccion de texto, resaltado y notas ancladas al punto exacto.
- **Pomodoro** — temporizador con timeline del recorrido del dia, bloques
  editables, trabajo indefinido y una ventana flotante independiente.
- **Calendario y planificacion** — hitos, evaluaciones y bloques de estudio.
- **Notas y cuadernos** — anotaciones enlazadas a documentos y materias.
- **Grafo de conocimiento** — relaciones entre materias, modulos y documentos.
- **Progreso y resultados** — avance por materia con pesos configurables,
  calculadora de notas y escenarios.
- **Estadisticas** — tiempo dedicado, atencion y evolucion por materia.

## Arquitectura

Cuatro capas con dependencias en una sola direccion:

```
        ui/            vistas y widgets Qt · sin logica de negocio · sin SQL
         v
   nucleo/servicios/   reglas de negocio · orquestacion
         v
 nucleo/repositorios/  todo el SQL vive aqui · devuelve dataclasses
         v
   nucleo/modelos/     dataclasses puras
         v
        SQLite
```

**Ningun modulo de `mukuwareru/nucleo/` puede importar PySide6 ni
`mukuwareru.ui`.** No es una convencion: `tests/test_arquitectura.py` recorre el
arbol sintactico de cada archivo del nucleo y falla si aparece un import
prohibido. La logica se prueba sin abrir una ventana.

## Desarrollo

```powershell
python -m pip install -r requirements-dev.txt   # entorno de desarrollo
python -m mukuwareru                            # ejecutar
python -m pytest -q                             # tests del nucleo
python herramientas/humo.py                     # prueba de humo de la interfaz
python -m mypy mukuwareru/nucleo                # tipado estricto del nucleo
python -m ruff check .                          # linting
```

## Compilacion y distribucion

```powershell
python herramientas/construir.py    # compila el .exe con PyInstaller
python herramientas/instalar.py     # instala en esta maquina y crea el acceso directo
python herramientas/empaquetar.py   # genera el instalador para otras maquinas
python herramientas/actualizar.py   # encadena los tres, abortando si fallan las comprobaciones
```

La compilacion trabaja bajo `%TEMP%`, nunca dentro del proyecto. La instalacion
por defecto es `%LOCALAPPDATA%\Programs\Mukuwareru`, deliberadamente fuera de
OneDrive: sincronizar una base SQLite abierta puede corromperla. `instalar.py`
copia solo el ejecutable y `_internal/`, y nunca toca `datos/`, `Library/` ni
`logs/`, de modo que actualizar no borra informacion.

Ni el ejecutable ni el instalador han llevado nunca una base de datos.

## Datos

Todo vive en local. La base SQLite y los PDF de la biblioteca quedan fuera del
control de versiones (`datos/`, `Library/`, `logs/`), igual que los binarios
compilados.

## Documentacion

[`PROJECT.md`](PROJECT.md) es la referencia oficial del proyecto: decisiones de
diseño, modelo de datos, convenciones y el detalle de cada version.
