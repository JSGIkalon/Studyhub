# Mukuwareru

*報われる — «ser recompensado».* La aplicacion se llamo **StudyHub** hasta la
version 1.0.0. El cambio de nombre alcanza al paquete de Python, al ejecutable,
al instalador y a la carpeta de instalacion; el unico rastro deliberado del
nombre antiguo esta en `herramientas/instalar.py`, que migra los datos de la
instalacion vieja (ver §7).

Centro de estudio personal para Windows. Multi-proyecto, completamente offline,
sin nube y sin servidor. Reemplaza el seguimiento en Excel por una aplicacion
que unifica temporizador, biblioteca PDF, visor de estudio, progreso y
estadisticas en una sola ventana.

Este archivo es la **referencia oficial del proyecto**. Se actualiza al cerrar
cada etapa.

- **Version:** 1.1.0 — **cerrada el 15 de septiembre de 2026.**
- **Estado:** **Todas las etapas completadas.** Ejecutable e instalador al dia
  con el ultimo cambio (la seccion Resultados, §14).
- **Entorno:** Python 3.12.10 · PySide6 6.11.1 (Qt 6.11.1) · Windows 11
- **Comprobaciones en verde:** 395 tests · `mypy --strict` sobre el nucleo ·
  `ruff` · prueba de humo de la interfaz completa.

---

## 0. Regla de publicacion

> **Todo cambio de codigo termina en:**
>
> ```powershell
> python herramientas/actualizar.py
> ```
>
> Comprueba, compila, instala y regenera el instalador. **No es opcional.**

Cambiar el codigo **no cambia la aplicacion instalada**. Mukuwareru se usa desde el
`.exe`, no desde el repositorio, asi que un arreglo que no se compila no existe
para quien lo usa. Ha pasado ya dos veces: el fallo seguia a la vista despues de
estar arreglado, simplemente porque el ejecutable era el anterior.

Que pasen `ruff`, `mypy`, `pytest` y `humo.py` **no basta**. `actualizar.py` los
pasa igualmente y aborta antes de compilar si alguno falla: publicar un
ejecutable roto es peor que no publicarlo.

Con `--rapido` se salta el instalador, que es el paso lento (comprime 144 MB).
Solo para iterar; antes de dar por cerrado un cambio, sin `--rapido`.

---

## 1. Filosofia

Pocas cosas, hechas muy bien. No es un gestor de productividad, ni un Notion, ni
un Obsidian. Ante dos soluciones se elige siempre la mas simple.

Si una decision aumenta la complejidad sin aportar valor real al estudio, no se
implementa.

Prioridades, en orden: **simplicidad · velocidad · mantenibilidad ·
escalabilidad · experiencia de usuario.**

---

## 2. Arquitectura

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

### Regla de oro

**Ningun modulo de `mukuwareru/nucleo/` puede importar PySide6 ni `mukuwareru.ui`.**

No es una convencion: `tests/test_arquitectura.py` recorre el arbol sintactico
de cada archivo del nucleo y falla si aparece un import prohibido. Garantiza que
la logica es testeable sin abrir una ventana y que la interfaz es reemplazable.

Consecuencia practica en el Pomodoro: el `QTimer` vivira en la UI y llamara a
una maquina de estados de Python puro. El test podra simular 25 minutos en
microsegundos.

### Sin sobreingenieria

No hay contenedor de inyeccion de dependencias, ni bus de eventos generico, ni
patron Command. `mukuwareru/contexto.py` construye conexion y repositorios una vez
al arrancar y se pasa por constructor.

### Recarga perezosa de vistas

`VistaBase` (`mukuwareru/ui/vistas/base.py`) implementa el contrato: al cambiar de
proyecto todas las vistas se marcan como sucias, pero solo la visible se recarga
al momento; las demas esperan a su `showEvent`. Evita reconstruir siete vistas
en cada cambio de proyecto.

---

## 3. Estructura del proyecto

```
CFA/
|-- mukuwareru/
|   |-- __main__.py               python -m mukuwareru
|   |-- aplicacion.py             arranque (sin siembra: ver §4)
|   |-- contexto.py               estado compartido (QObject con senales)
|   |-- nucleo/                   <- cero imports de Qt
|   |   |-- modelos/entidades.py  dataclasses del dominio
|   |   |-- repositorios/         unico lugar con SQL
|   |   |-- servicios/            (vacio hasta la Etapa 3)
|   |   \-- bd/
|   |       |-- conexion.py       apertura + PRAGMAs + migracion
|   |       |-- migrador.py       aplicacion de migraciones
|   |       \-- migraciones/      001_esquema_inicial.sql, ...
|   |-- ui/
|   |   |-- ventana_principal.py  ventana unica + conmutador de vistas
|   |   |-- barra_lateral.py      proyectos + navegacion
|   |   |-- iconos.py             carga de SVG con tinte
|   |   |-- vistas/               una por seccion + base.py + registro
|   |   |-- dialogos/             recogen datos, no escriben (ver §8)
|   |   |-- lector/               visor PDF propio (ver §5)
|   |   |-- grafo/                lienzo del grafo: QGraphicsView (ver §11 ter)
|   |   |-- widgets/              reutilizables, sin dominio
|   |   \-- tema/                 tokens.py + oscuro.qss
|   |-- recursos/iconos/          SVG 24x24 con stroke="{{COLOR}}"
|   \-- utilidades/               rutas.py, registro.py, formato.py
|-- tests/
|-- herramientas/                 mukuwareru.spec, construir.py
|-- PROJECT.md
|-- pyproject.toml
\-- requirements.txt
```

`SECCIONES`, en `mukuwareru/ui/vistas/__init__.py`, es el **catalogo**: declara que
secciones existen, con que icono y con que clase. Anadir una sigue siendo anadir
una linea ahi, y el conmutador de la ventana las construye todas.

El **orden y la visibilidad** ya no se deciden en esa lista, sino en dos claves
de `ajuste` (`interfaz.orden_secciones`, `interfaz.secciones_ocultas`) que el
usuario edita en Ajustes arrastrando. `ServicioPreferencias.disposicion_secciones`
cruza lo guardado con el catalogo mediante `reconciliar_orden`, que es una
funcion pura: lo guardado que sigue existiendo primero, y lo que la version trae
de nuevo al final. Asi una seccion retirada se ignora y una nueva aparece sola,
**sin migracion ni numero de version de la preferencia**.

Dos consecuencias que hay que respetar al tocar la barra lateral:

- El conmutador construye **todas** las secciones aunque esten ocultas, porque
  `ir_a("biblioteca")` es la salida del lector y tiene que funcionar con
  Biblioteca escondida.
- `marcar_seccion` con una seccion oculta **desmarca todo**. Dejar marcado el
  boton anterior senalaria una seccion que no es la que se esta viendo.

Ajustes no se puede ocultar: seria el unico camino de vuelta. El invariante vive
en `ServicioPreferencias`, no en la interfaz.

---

## 4. Modelo de datos

SQLite con `foreign_keys = ON`, `journal_mode = WAL`, `synchronous = NORMAL`.
Esquema completo en `mukuwareru/nucleo/bd/migraciones/001_esquema_inicial.sql`.

| Tabla | Contenido |
|---|---|
| `proyecto` | Ambito de estudio independiente |
| `materia` | Agrupacion de modulos, con su `peso`, horas, prioridad y fecha limite |
| `modulo` | Unidad minima de progreso, marcada a mano; horas opcionales |
| `evaluacion` | Un examen: puntos sobre posibles, o **pendiente** si no tiene nota |
| `evaluacion_materia` | Desglose opcional de una evaluacion por asignatura |
| `documento` | PDF descubierto en la biblioteca + posicion de lectura |
| `sesion` | Bloque de tiempo de estudio |
| `sesion_materia` | Etiquetado opcional de una sesion (N a N) |
| `anotacion` | Marcador, nota o resaltado anclado a una pagina |
| `cuaderno` | Contenedor de secciones dentro de un proyecto |
| `seccion` | Division de un cuaderno; toda nota vive en una |
| `nota` | Nota suelta, sin PDF ni pagina |
| `etiqueta` + `nota_etiqueta` | Clasificacion transversal de notas (N a N) |
| `nota_vinculo` | Enlace de una nota a materia / modulo / PDF / anotacion |
| `hito` | Una fecha con nombre: examen, entrega, meta |
| `bloque_plan` + `bloque_materia` | Bloque de estudio planeado y sus materias |
| `grafo_nodo` | Referencia a materia/modulo/hito/evaluacion + posicion en el lienzo |
| `grafo_arista` | Un prerrequisito; `grupo` codifica el O (ver §11 ter) |
| `ajuste` | Clave/valor; `proyecto_id NULL` = global |
| `esquema_version` | Control de migraciones |

### Decisiones que importan

**`anotacion` unifica marcador, nota y resaltado.** Los tres son lo mismo: un
ancla en una pagina con texto y comentario opcionales. Tres tablas casi
identicas obligarian a tres repositorios y a tres consultas en la vista de
navegacion.

**`nota` es una tabla aparte, y `anotacion` no se toco.** Extender `anotacion`
con `documento_id` y `pagina` nullables parecia mas barato y no lo es. Los dos
ciclos de vida son **opuestos**: un resaltado sin su PDF no significa nada y la
CASCADE se lo lleva, mientras que una nota que *menciona* ese PDF tiene valor por
si sola y debe sobrevivirle. Ademas una nota suelta no tiene proyecto por la via
del documento, `pagina NOT NULL` es un invariante del que dependen el lector y su
panel, y quitar un `NOT NULL` en SQLite obliga a reconstruir la tabla sobre datos
reales del usuario. El precio de la decision se mide en una lista: la migracion
002 no toca ni una fila existente, y `repositorios/anotaciones.py`, el lector y
`001_esquema_inicial.sql` no cambiaron.

**`nota_vinculo` usa cuatro claves foraneas excluyentes, no `(tipo, objeto_id)`.**
El par generico habria tirado la integridad referencial y dejado vinculos
apuntando a PDFs borrados. La exclusividad la garantiza un `CHECK` que suma
booleanos, y cada destino tiene su indice unico **parcial** (misma solucion que
`idx_ajuste_global`), con `COALESCE(pagina, -1)` para que «el documento entero»
tambien sea unico. Todos los `vincular_*` insertan con `ON CONFLICT DO NOTHING`.

**`nota.cuerpo_plano` es derivado, no cacheado.** El cuerpo es HTML con las
imagenes en base64, asi que un `LIKE` sobre el es lento y **falso**: «gif»
aparece dentro del base64 de cualquier imagen. Se recalcula en el repositorio en
cada escritura, en la misma fila, igual que `sesion.fecha_local`, y no puede
desincronizarse porque nadie escribe `cuerpo` sin pasar por ahi. FTS5 se descarto:
tabla virtual mas tres triggers si seria la cache desincronizable que esta
seccion prohibe. El extractor vive en `utilidades/texto.py` con `html.parser`,
sin Qt, para poder probarlo con pytest.

**El calendario no guarda nada de lo ya estudiado.** Las sesiones son una
proyeccion de solo lectura de `sesion`, asi que no puede desincronizarse. Lo
unico que se guarda es lo que todavia no ha pasado: `hito` y `bloque_plan`.
**No hay `bloque_plan.sesion_id`**: obligaria a reclamar la sesion a mano y una
CASCADE desde `sesion` borraria el bloque al borrar la sesion. El cumplimiento
lo **calcula** `repartir_cumplimiento`, una funcion pura con cuatro reglas: el
solape de horas manda; un bloque con materias solo acepta sesiones compatibles
**o sin etiquetar** (etiquetar es opcional y castigar a quien se salto el
dialogo seria injusto); cada segundo se atribuye **una sola vez**, procesando por
`(hora, id)`, de modo que dos bloques solapados no suman el doble; y los bloques
sin hora recogen lo que quede del dia.

**`hito` y `bloque_plan` son dos tablas, no un `evento` generico.** Un hito es un
instante sin duracion que se cumple o no; un bloque tiene hora, duracion,
materias previstas y se compara contra lo estudiado. Unificarlos daria una tabla
con la mitad de las columnas siempre en NULL y dos `CHECK` divergentes.
`proyecto.fecha_objetivo` se conserva y se espeja en el hito `principal` **en un
solo sentido**, desde `ServicioProyectos`; el indice unico parcial
`idx_hito_principal` impide que haya dos. La cuenta atras de la barra lateral
pasa por `proxima_fecha_clave()`, asi que anadir un simulacro mas cercano cambia
el contador.

**El cuaderno por defecto no se siembra en SQL.** `datetime('now')` no lleva
desfase local y romperia la convencion de `creado_en`. Lo crea
`RepositorioCuadernos.asegurar_por_defecto()`: un solo camino que vale igual para
los proyectos anteriores a las notas y para los de manana.

**`rects_json` guarda coordenadas en PUNTOS PDF, no en pixeles.** Es la decision
critica del visor: un resaltado creado al 150 % debe dibujarse bien al 80 % y en
otra pantalla.

**`fecha_local` es una columna, no un calculo.** Racha, horas de hoy y horas por
dia son `GROUP BY fecha_local` sobre un indice, sin funciones de fecha.

**`documento.huella`** = tamano + MD5 parcial (primeros y ultimos 64 KB).
Reconoce un PDF renombrado o movido y le conserva progreso y anotaciones sin
leer el archivo completo.

**Cero tablas de cache o de agregados.** Toda estadistica es una consulta SQL
sobre `sesion`. Nada puede quedar desincronizado.

**Renombrar un proyecto puede mover una carpeta del disco, y si no se hace bien
borra datos.** Con `ruta_biblioteca` en NULL la carpeta es `Library/<nombre>`
(`servicios/biblioteca.py::ruta_biblioteca`). Cambiar el nombre a secas la
reapunta a una carpeta inexistente; el siguiente `escanear()` da todos los
documentos por desaparecidos, los borra, y `anotacion ... ON DELETE CASCADE` se
lleva todas las anotaciones. `ServicioProyectos.renombrar` mueve la carpeta y,
si el sistema no deja (OneDrive la tiene tomada, o el destino ya existe), **fija
`ruta_biblioteca` a la carpeta antigua**: se pierde la coherencia entre nombre y
carpeta, que es cosmetica, y no los PDFs. Es el unico camino por el que debe
pasar un renombrado, y `tests/test_servicio_proyectos.py` lo vigila.

**Borrar un proyecto no borra los PDF del disco.** La cascada limpia la base de
datos; los archivos del usuario se quedan. El dialogo de confirmacion lo dice y
enumera lo que si se pierde, con `contar_dependencias`, que resuelve la cascada
transitiva `proyecto -> documento -> anotacion` en una sola consulta.

**No hay siembra de proyectos.** Una base nueva arranca vacia y la ventana
muestra `PanelBienvenida`. Los dos proyectos de ejemplo que se creaban aqui
obligaban a heredar el temario de otra persona y a borrarlo a mano. El estado
vacio no es un caso raro: es tambien el de «acabo de borrar mi ultimo proyecto»,
y por eso vive en el conmutador y **no** es un dialogo modal de primer arranque
(uno modal en el constructor dejaria colgada la prueba de humo, que construye
varias ventanas sin nadie que pulse botones).

Claves de `ajuste` en uso: `pomodoro.*` (duraciones y la pregunta de materias) e
`interfaz.orden_secciones` / `interfaz.secciones_ocultas` (§3), globales; y
`plan.minutos_por_dia` / `plan.activo`, **por proyecto**, porque cada examen se
prepara a un ritmo distinto.

### Migraciones

`NNN_descripcion.sql` aplicadas en orden numerico dentro de una transaccion,
comparando contra `esquema_version`. Antes de la primera migracion sobre una
base existente se guarda `basedatos.vN.respaldo.db`. Esto es lo que permite
reemplazar el ejecutable sin perder datos.

| # | Que anade |
|---|---|
| 001 | Esquema inicial: proyecto, materia, modulo, documento, sesion, anotacion, ajuste |
| 002 | Notas sueltas: cuaderno, seccion, nota, etiqueta, vinculos |
| 003 | Calendario: hito, bloque_plan |
| 004 | `materia.peso` |
| 005 | Resultados: evaluacion, evaluacion_materia |
| 006 | Carga de estudio en `materia` y `modulo`; evaluaciones **pendientes** |
| 007 | Grafo de dependencias: grafo_nodo, grafo_arista |

La 006 es la unica que **recrea** una tabla (`evaluacion`, para poder quitarle el
`NOT NULL` que SQLite no deja quitar con `ALTER`). Es la operacion que mas
facilmente pierde datos, asi que tiene un test propio que migra una base parada
en la 005 y comprueba que todo sigue ahi con el mismo id.

---

## 5. Visor PDF

**Hallazgo verificado:** `QPdfView` no expone seleccion de texto ni permite
mapear coordenadas del viewport a la pagina (ese mapeo es privado en Qt).
`QPdfDocument.getSelection(pagina, p0, p1)` si existe y devuelve `.text` y
`.bounds`. Qt aporta el motor, no la interaccion.

Por eso el visor es propio (Etapa 6):

```
LectorPdf
|-- BarraLector       pagina X/N · zoom · ajustar ancho/pagina · buscar
|-- PanelLateral      Miniaturas | Contenido (QPdfBookmarkModel) | Busqueda (QPdfSearchModel)
\-- VistaPaginas (QAbstractScrollArea)          <- codigo propio
    |-- DisposicionPaginas   offsets segun pagePointSize() y zoom
    |-- CachePaginas         LRU de QImage por (pagina, zoom, dpr)
    |-- Renderizador         QPdfDocument.render() fuera del hilo de UI
    |-- Mapeo                viewport <-> (pagina, punto PDF)
    |-- ControlSeleccion     arrastre -> getSelection() -> menu contextual
    \-- CapaSuperpuesta      resaltados guardados + seleccion viva + busqueda
```

Scroll continuo, una columna. Se pintan solo las paginas visibles +-1.

### Cuatro trampas de Qt que hubo que sortear

**`getSelection` solo responde si los dos puntos caen dentro de la caja de un
glifo.** Arrastrar desde el margen izquierdo, o soltar entre dos lineas,
devuelve una seleccion invalida. `mukuwareru/ui/lector/seleccion.py` ajusta cada
punto al texto mas cercano antes de preguntar a Qt, que es lo que hace cualquier
visor de verdad. Sin eso, seleccionar texto seria una loteria.

**Los dos enums de rol de Qt no son del mismo tipo.** `QPdfBookmarkModel.Role`
es un `IntEnum` y admite `int()`, pero `QPdfSearchModel.Role` es un `Enum`
normal y hay que leer su `.value`. Pasar el enum directamente a
`QModelIndex.data()` lanza un `TypeError` que Qt se traga dentro del manejador
de senales: la lista de resultados quedaba vacia sin ningun error visible.

**`QPdfDocument.render()` no pinta el fondo del papel.** Devuelve la tinta sobre
pixeles transparentes (`Format_ARGB32`, alfa 0). Compuesta sobre el panel oscuro,
una pagina blanca se ve negra. El lienzo del lector ya rellenaba blanco antes de
dibujar; las miniaturas no, y por eso salian invertidas. Ambos caminos rellenan
ahora, y `humo.py` comprueba que el pixel de la esquina es opaco y blanco.

**Qt genera solo las variantes `Selected` y `Active` de un `QIcon`, tinendolas
con el color de resalte.** En una miniatura eso pinta la hoja entera de rojo al
seleccionarla. `_icono_sin_tinte()` registra las tres variantes a mano con el
mismo mapa de pixeles. Es un fallo puramente visual que ningun assert habitual
detecta: se encontro generando una captura del panel con `QWidget.grab()`, y esa
captura sigue siendo la forma de revisar cambios en el panel lateral.

---

### Anotaciones dentro del lector

`mukuwareru/ui/lector/panel_notas.py` es una cuarta pestana del panel lateral con
las anotaciones del PDF abierto: crear, ir a la pagina, editar el comentario y
borrar, sin salir del documento.

Duplica en parte la vista Anotaciones, y esa duplicidad es intencionada. Son dos
tareas distintas: la vista sirve para repasar todo el proyecto; el panel, para
trabajar sobre el PDF que tienes delante. Revisar una nota sin ver su pagina no
sirve de nada, y salir del lector para editarla pierde la posicion de lectura.

El panel no toca la base de datos: emite senales y `VistaLector` persiste.

**Solo notas de cuaderno.** Se retiraron los caminos para crear notas y
marcadores anclados al PDF: todo lo que se escribe vive en un cuaderno, donde
sobrevive al PDF y se puede buscar, etiquetar y relacionar. Lo que se conserva es
el **resaltado**, que no es escribir sino marcar la pagina; sin el, una nota
diria «pagina 44» y no habria nada que ver al volver alli.

`TipoAnotacion.NOTA` y `MARCADOR` **siguen en el esquema y en `_ETIQUETAS`**: las
anotaciones ya creadas se listan, se editan y se borran como siempre. Lo que
desaparece es el boton para crear nuevas. Borrarlas del modelo habria hecho
desaparecer trabajo del usuario sin avisar.

`Ctrl+M` sigue existiendo y ahora abre una nota de cuaderno ligada a la pagina
visible, que es lo que antes hacia «Nota aqui».

**El reparto entre panel y PDF es del usuario.** `_repartir_notas()` (50/50) se
llama **solo** desde el boton «Notas» de la barra. Todo lo demas —abrir un
documento, crear un resaltado, crear una nota de cuaderno— usa `_traer_notas()`,
que solo trae la pestana al frente. Antes las tres cosas repartian al 50/50 y
cualquier anotacion deshacia el reparto que el usuario acababa de elegir. El
estado del divisor se guarda en `datos/ajustes.json` bajo `lector_divisor`.

---

### Logotipo

`mukuwareru/recursos/logo.png` es la fuente de verdad: el kanji 報 en rojo sobre
negro. Para cambiarlo basta con reemplazar ese archivo y ejecutar
`herramientas/generar_icono.py`; no hay que tocar codigo.

- `iconos.icono_aplicacion()` lo prefiere sobre el SVG y **registra los siete
  tamanos ya escalados**. Con un unico mapa de 1254 px, Qt reduce a 16 px de
  golpe y el trazo del pincel se ensucia en la barra de tareas.
- `generar_icono.py` ensambla el `.ico` **a mano**. `QImage.save` escribe un ICO
  de un solo tamano y sin comprimir: un 256x256 pasaba de 1 MB y el compilador de
  Inno Setup lo rechazaba con «File is too large». Guardando cada tamano como PNG
  dentro del ICO, el archivo queda en 28 KB con los siete tamanos.

El icono solo aparece en barra de tareas, Alt+Tab, notificaciones e instalador;
nunca dentro de la aplicacion. Por eso su fondo negro opaco no desencaja con el
fondo `#0E0E10` de la interfaz.

---

## 6. Tema visual

`mukuwareru/ui/tema/tokens.py` es la **unica** fuente de color, espaciado y radio.
`oscuro.qss` es una plantilla con marcadores `{{TOKEN}}` que se expanden al
arrancar, de modo que el mismo valor sirve para la hoja de estilos y para el
codigo que pinta con `QPainter`.

Base Fusion + paleta oscura. Acento rojo tomate `#E5484D`. Radios de 6-10 px.
**Sin transparencias, sin animaciones, sin efectos.**

Con **una** excepcion, acotada y pedida a proposito: el caminante del timeline
del Pomodoro (`ui/pomodoro/caminante.py`) interpola su posicion en 320 ms al
pasar de un bloque al siguiente. Solo posicion, solo ese widget, y nada mas se
mueve en la aplicacion. La regla sigue en pie para todo lo demas: si aparece una
segunda animacion, la que hay que discutir es la regla, no la excepcion.

Los iconos son SVG con `stroke="{{COLOR}}"`: un solo archivo por icono sirve
para todos los estados, tintado y cacheado en `mukuwareru/ui/iconos.py`.

---

## 6 bis. El Pomodoro fuera de la ventana

Estudiar significa tener Mukuwareru minimizado casi todo el rato. Un temporizador
que solo se ve al restaurar la ventana no cumple su funcion, asi que hay dos
salidas hacia fuera.

**Mini ventana** (`mukuwareru/ui/mini_pomodoro.py`). Unica ventana secundaria de
la aplicacion. Aparece sola **si el reloj corre y Mukuwareru no esta delante**:
minimizada o sin el foco, porque estudiar con el navegador delante deja el reloj
igual de invisible que minimizarlo. Muestra fase y cuenta atras, permite pausar,
y se arrastra a cualquier sitio. Es `Qt.Tool` para no duplicar la entrada en la
barra de tareas, y siempre encima. Se retira al volver a Mukuwareru y cuando el
reloj se detiene por si mismo al acabar una fase.

Tres detalles que no son adorno:

- La decision se toma con `isActiveWindow()` de la **ventana principal**, no con
  `applicationStateChanged`. Pulsar «Pausar» en la mini ventana activa la
  aplicacion; con el estado global la mini se esconderia justo al ir a usarla.
- Sale con **400 ms de retardo** al perder el foco (`_RETARDO_FLOTANTE_MS`).
  Pasar por Mukuwareru con Alt+Tab desactiva y reactiva la ventana en decimas de
  segundo, y sin ese margen el reloj parpadearia en cada paso. Minimizar es una
  decision explicita y no espera.
- `colocar_por_defecto()` **solo coloca la primera vez**. Antes se llamaba en
  cada aparicion y devolvia el reloj a la esquina cada vez que el usuario lo
  movia. La posicion se guarda en `datos/ajustes.json` bajo `mini_pomodoro`.

**Notificaciones** (`mukuwareru/ui/notificaciones.py`). `QSystemTrayIcon` produce
avisos nativos de Windows sin dependencias ni conexion, y es el unico camino que
da Qt para avisar con la ventana minimizada. Sin bandeja disponible las llamadas
no hacen nada y la aplicacion sigue igual. Se avisa al terminar cada fase y
cuando una configuracion editada a mitad de fase por fin se aplica — no en cada
pulsacion del spinbox, que seria una lluvia de avisos.

El reloj vive en `VistaPomodoro`, que expone senales (`reloj_avanzo`,
`fase_termino`, `aviso`) y no sabe que la mini ventana ni la bandeja existen.
`VentanaPrincipal` las conecta.

### Cerrar termina el pomodoro

No hay estado del reloj que sobreviva al cierre. Pero tirar el tiempo ya
trabajado seria peor que no cronometrarlo, asi que al cerrar una fase de trabajo
con **un minuto o mas** se guarda como sesion `completada = 0`: el tiempo cuenta
en las estadisticas y el pomodoro no cuenta como logrado. La columna existia ya
en el esquema justo para esto. Por debajo de un minuto no se registra nada.

---

## 6 ter. El timeline: el recorrido como elemento principal

El ciclo 25/5 x4 dejo de estar cableado. Lo que se ve en la vista Pomodoro es un
**recorrido**: una fila de bloques que se lee de izquierda a derecha y que el
usuario reordena, duplica, edita y amplia.

### Quien manda sobre quien

`nucleo/servicios/recorrido.py` es Python puro y tiene la forma del ciclo:
`Fase`, `Estado`, `Configuracion`, `Bloque` y `Recorrido`. `RelojPomodoro`
(`pomodoro.py`) quedo como lo que siempre debio ser: una cuenta atras sobre el
bloque que toque. `fase`, `duracion_seg`, `completadas` y `secuencia()` son ahora
propiedades **derivadas** del recorrido, no estado propio.

Eso es lo que hace que las 17 pruebas de `tests/test_pomodoro.py` sigan pasando
**sin tocar una linea**: la superficie publica del reloj no cambio. Si una
refactorizacion futura las obliga a cambiar, es senal de que rompio el contrato.

`pomodoro.py` reexporta `Fase`, `Estado` y `Configuracion` porque ese era su
modulo de siempre y media aplicacion los importa de ahi.

### Reglas del recorrido

- **Nunca se queda sin salida.** Al pasar del ultimo bloque, `_alargar()` anade un
  par nuevo (trabajo + su descanso) respetando en que punto del ciclo se esta.
- **Lo recorrido no se toca.** `movible()` niega mover el bloque en curso mientras
  hay cuenta atras viva, y `editable()` niega tocar los que quedaron atras.
- **Editar la duracion del bloque en marcha traslada la diferencia**, no reinicia:
  pasar de 25 a 45 min con 24:13 en pantalla deja 44:13 (`_trasladar`).
- **`editado` protege del usuario contra la configuracion.** Cambiar las
  duraciones por defecto refresca solo los bloques que nadie toco a mano. Para
  tirarlo todo esta el boton «Regenerar recorrido», que pide confirmacion.
- **No se persiste.** El recorrido se rearma en cada arranque desde la
  configuracion guardada, igual que el reloj no sobrevive al cierre. Si algun dia
  hace falta que sobreviva, la migracion `bloque_pomodoro` es un anadido limpio
  sobre este diseno; no hay nada que deshacer.

### La interfaz

`mukuwareru/ui/pomodoro/`: `bloque.py` (tarjeta), `timeline.py` (riel con
desplazamiento y soltado), `caminante.py` (el personaje), `editor_bloque.py`
(panel de edicion) y `temas.py` (tira de materias arrastrables).

- **Dos ritmos de refresco.** `reconstruir()` rehace las tarjetas y solo se llama
  cuando cambia la forma del recorrido. `actualizar_estado()` toca la tarjeta
  activa y mueve al caminante, una vez por segundo. Reconstruir cada segundo
  destruiria diez widgets por tic y un arrastre en curso se quedaria sin origen a
  mitad del gesto.
- **El estado se pinta con propiedades dinamicas** (`estado`, `descanso`) que el
  QSS consulta, no reescribiendo hojas de estilo. La tarjeta lleva ademas una
  **huella** de lo ya pintado para no repintar diez tarjetas que no cambiaron.
- **Arrastrar y soltar** con dos formatos MIME propios:
  `application/x-mukuwareru-bloque` (reordenar) y `.../materia` (un tema de la
  tira se convierte en un bloque de trabajo). Formatos propios y no `text/plain`
  para que el riel distinga lo suyo de cualquier texto del escritorio.
- **La tira de temas se repite dentro de la vista Pomodoro** en lugar de
  arrastrarse desde Progreso. Las secciones viven en un `QStackedWidget` y nunca
  coinciden en pantalla: arrastrar entre ellas es imposible.
- **Atajos sin abrir nada:** rueda del raton sobre una tarjeta = ±5 min; doble
  clic = empezar por ese bloque; clic = editor; clic derecho = duplicar/eliminar.

### El caminante

`recursos/personaje.png` se genera una vez con
`herramientas/preparar_personaje.py`, que recorta el fondo blanco de la foto de
origen (`Imagen.jpg`) con una rampa de alfa y ajusta al rectangulo util. Se carga
con `importlib.resources`, como los iconos: nunca por ruta de disco, que es lo
que hace funcionar la build congelada. Si el PNG falta, el timeline pinta un
marcador redondo y sigue siendo legible.

Dentro de un bloque avanza con el progreso, una vez por segundo y sin animar.
Entre bloques interpola la posicion en 320 ms. Ver la excepcion en §6.

### Un regalo del modelo nuevo

Si el bloque terminado lleva un tema asignado, la sesion se etiqueta sola y el
dialogo de etiquetado no aparece: el usuario ya lo dijo al armar el recorrido, y
volver a preguntarlo seria un dialogo de mas cada veinticinco minutos.

---

## 6 quater. Trabajo indefinido

No todo el estudio cabe en bloques de veinticinco minutos. Un examen resuelto de
principio a fin, o una clase, duran lo que duran, y trocear eso en pomodoros solo
para que el tiempo quede registrado es poner la herramienta por delante del
estudio. El boton **«Iniciar trabajo indefinido»** de la vista Pomodoro abre una
sesion sin duracion fijada, con sus botones de pausa y de detener.

`nucleo/servicios/cronometro.py` es el reflejo de `RelojPomodoro`: Python puro,
la interfaz le pasa el tiempo con `avanzar(segundos)` y un test simula tres horas
en microsegundos. Es deliberadamente pequeño —estado, segundos y cuatro
transiciones— porque no hay recorrido que gobernar: aqui solo se suma.

Las decisiones que no son evidentes:

- **Detener registra; pausar no.** `detener()` devuelve lo transcurrido y deja el
  cronometro a cero: ese numero es lo unico que llega a la base de datos. Una
  pausa deja la sesion **abierta**, con el tiempo pendiente. Por eso `activo` y
  `corriendo` son propiedades distintas y las dos hacen falta.
- **Se guarda como sesion de trabajo `completada = 1`.** Cuenta en el calendario,
  en la racha y en las estadisticas igual que un pomodoro, porque es lo mismo:
  tiempo estudiado. Lo que no cuenta es como *pomodoro logrado*, y no lo cuenta
  porque `completadas` sale del recorrido, no de las sesiones.
- **Se pregunta el tema al terminar**, por el mismo `DialogoEtiquetar` y
  respetando `preguntar_materia`. Aqui no hay bloque con tema asignado que evite
  el dialogo (§6 ter): la sesion libre no sale del recorrido.
- **Las dos formas de cronometrar se excluyen.** Con una sesion libre abierta el
  boton del Pomodoro se deshabilita, y al reves. Dejarlas convivir registraria la
  misma hora dos veces, y ninguna estadistica lo detectaria.
- **Menos de un minuto no se registra**, igual que al cerrar (§6 bis). Al cerrar
  la aplicacion, una sesion libre viva se guarda como `completada = 0` y sin
  preguntar el tema: no puede abrirse un dialogo modal mientras la ventana se va.

### Fuera de la ventana

El reloj flotante y el compacto de la barra lateral sirven a las dos formas: con
el Pomodoro cuentan hacia atras, con una sesion libre hacia arriba y en rojo de
acento. `VentanaPrincipal._volcar_reloj()` es quien decide cual pintar, mirando
`VistaPomodoro.sesion_libre_activa`.

Dos diferencias respecto al Pomodoro, y las dos por la misma razon —esta sesion
no termina sola—:

- **El flotante trae boton «Detener»**, que en modo Pomodoro no aparece. Sin el,
  cerrar la sesion obligaria a restaurar la ventana.
- **El flotante no se retira al pausar.** `VistaPomodoro.corriendo` devuelve
  `True` mientras la sesion libre este abierta, aunque este en pausa. Con la
  regla anterior, pausar escondia el reloj y con el «Detener».

`formato.duracion_reloj` gano el campo de horas por esto: una sesion de tres
horas marcaba `180:00`, y un bloque de trabajo de dos horas —permitido desde
siempre— marcaba `120:00`.

---

## 6 quinquies. Ocultar la barra lateral

Tres estados, no dos: `completa` (244 px), `colapsada` (56 px, solo iconos) y
`oculta` (0 px). Colapsada no basta cuando se lee un PDF a doble pagina: esos
56 px se notan.

- Se persiste en `interfaz.barra_lateral` via `ServicioPreferencias`, con el mismo
  patron clave/valor que la disposicion de secciones. Antes el colapso era solo
  memoria y se perdia al cerrar.
- **Dos vias de vuelta, y las dos hacen falta.** `Ctrl+B` para quien lo sepa, y un
  tirador `#TiradorBarra` de 14 px pegado al borde izquierdo del area de
  contenido para quien no. Sin el tirador, ocultar la barra seria un billete de
  ida.
- Al desocultar vuelve al estado en que estaba, no siempre a completa.

---

## 7. Datos y distribucion

### Compilar e instalar

```powershell
python herramientas/generar_icono.py   # solo si cambio mukuwareru.svg
python herramientas/construir.py       # compila (fuera de OneDrive)
python herramientas/instalar.py        # instala y crea acceso directo
```

**Nada de la compilacion ocurre dentro del proyecto.** PyInstaller trabaja y
escribe bajo `%TEMP%\mukuwareru-build` y `%TEMP%\mukuwareru-dist`. Hay dos razones
concretas, ambas comprobadas:

1. `COLLECT` de PyInstaller **vacia por completo su carpeta de salida**. Si esa
   carpeta fuera tambien la de uso diario, cada compilacion borraria `datos/`.
2. El proyecto vive en OneDrive, cuya sincronizacion mantiene abiertos los
   archivos recien subidos: PyInstaller falla con `PermissionError [WinError 5]`
   al intentar limpiar. Y ademas subiria ~130 MB por compilacion.

`instalar.py` copia **solo** `Mukuwareru.exe` y `_internal/` sobre la carpeta de
instalacion, y nunca toca `datos/`, `Library/` ni `logs/`. Ese es el mecanismo
que permite actualizar sin perder informacion.

Instalacion por defecto: `%LOCALAPPDATA%\Programs\Mukuwareru`, deliberadamente
fuera de OneDrive (sincronizar una base SQLite abierta puede corromperla).

`herramientas/copiar_datos.py` traslada la base de datos de desarrollo a una
instalacion usando la API de respaldo de SQLite, que consolida el WAL.

**Ni el `.exe` ni el instalador han llevado nunca una base de datos.** El `.spec`
empaqueta migraciones, QSS, iconos y logo; el `.iss` copia `Mukuwareru.exe` y
`_internal/`, y su seccion `[Dirs]` crea `datos/` y `Library/` **vacias**. Se
deja escrito para no volver a dudarlo: los proyectos que aparecian en una
instalacion nueva los creaba `aplicacion.py` en el primer arranque, no el
instalador. Al retirar esa siembra, una instalacion existente **conserva** sus
proyectos —`instalar.py` no toca `datos/` a proposito—; quitarlos de ahi es cosa
del menu contextual de la barra lateral.

### Migracion desde StudyHub

Renombrar la aplicacion cambio la carpeta de instalacion, y con ella la ruta de
la base de datos. Sin hacer nada, el cambio de nombre habria equivalido a
empezar de cero. `instalar.py::_migrar_desde_studyhub` detecta la carpeta
`Programs\StudyHub` y **copia** `datos/`, `Library/` y `logs/` a la nueva.

Se copia y no se mueve: la carpeta antigua queda intacta por si algo fallara.
Solo se copia lo que aun no existe en el destino, asi que repetirlo no pisa nada.

El instalador de Inno **no** hace esta migracion: lleva un `AppId` nuevo y trata
Mukuwareru como un producto distinto. La migracion solo tiene sentido en la
maquina donde estaba la instalacion vieja, y ahi se usa `instalar.py`.

**El `.exe` no se regenera solo.** Cambiar el codigo no cambia la aplicacion
instalada: hay que volver a compilar e instalar. Se cae en esta trampa con
facilidad, porque la app sigue abriendose y funcionando con la version anterior.

### Instalador distribuible

```powershell
python herramientas/construir.py       # compila
python herramientas/empaquetar.py      # produce Mukuwareru-Setup-X.Y.Z.exe
```

`herramientas/mukuwareru.iss` es el guion de **Inno Setup 6**
(`winget install --id JRSoftware.InnoSetup`). No se compila a mano:
`empaquetar.py` le pasa version, origen, salida e icono con `/D`, de modo que la
version vive solo en `mukuwareru/__init__.py`.

El instalador sale a `%USERPROFILE%\Mukuwareru-Instalador\` — fuera de OneDrive,
pero en una ruta que se encuentra sin buscar, porque es un archivo para llevarse.
Comprime los 144 MB de la carpeta a **41 MB**.

Decisiones del guion:

- **Por usuario** (`PrivilegesRequired=lowest`), a `%LOCALAPPDATA%\Programs\Mukuwareru`:
  la misma carpeta que usa `instalar.py`, asi que ambos caminos conviven sin
  duplicar los datos. Ademas no pide administrador ni muestra el aviso de UAC.
- **`AppId` fijo.** Cambiarlo haria que una version nueva se instalase al lado de
  la vieja en vez de reemplazarla.
- **`[InstallDelete]` vacia `_internal`** antes de copiar, para que no queden
  archivos huerfanos de compilaciones anteriores. `datos`, `Library` y `logs` no
  aparecen en ninguna seccion del guion, y esa omision es deliberada: Inno solo
  borra lo que instalo, y solo elimina un directorio si quedo vacio.

El paquete lleva Python y Qt dentro, asi que el equipo de destino no necesita
nada previo: cualquier Windows 10 u 11 de 64 bits.

### Cifras medidas

| Metrica | Valor |
|---|---|
| Tamano de la carpeta | 145 MB |
| Tamano del instalador | 42 MB |
| Primer arranque (en frio) | ~3 s |
| Arranques siguientes | **~620 ms** |
| Memoria en reposo | ~100 MB |
| Ventana de consola | ninguna |


`mukuwareru/utilidades/rutas.py` resuelve la raiz una sola vez:

- **Desarrollo** -> `./datos/` en la raiz del repositorio.
- **Congelado** -> junto al `.exe`; si esa carpeta no es escribible (por ejemplo
  en *Program Files*), cae a `%LOCALAPPDATA%\Mukuwareru`.

```
%LOCALAPPDATA%\Programs\Mukuwareru\
|-- Mukuwareru.exe        <- lo reemplaza una actualizacion
|-- _internal/          <- lo reemplaza una actualizacion (Qt y Python)
|-- datos/              <- del usuario, nunca se toca
|   |-- basedatos.db
|   \-- ajustes.json    solo lo previo a abrir la BD (geometria de ventana)
|-- Library/            <- del usuario, nunca se toca
\-- logs/               rotativos, 5 archivos x 1 MB
```

**PyInstaller en modo `onedir`, no `onefile`:** `onefile` descomprime todo Qt en
`%TEMP%` en cada arranque (2-5 s), lo que contradice el requisito de apertura
rapida. Se excluyen QtWebEngine, QtQuick, QtMultimedia, pandas y numpy.

---

## 8. Convenciones

- Nombres en espanol en todo el codigo, el esquema SQL y la documentacion. Los
  identificadores de Qt y de la biblioteca estandar se conservan tal cual.
- Anotaciones de tipo en todas las funciones publicas. `mypy` estricto sobre
  `mukuwareru.nucleo`.
- Docstrings en espanol en clases y metodos publicos.
- `ruff` para formato y linting, linea de 100.
- Ninguna consulta SQL fuera de `repositorios/`.
- Un widget por archivo cuando supere unas 150 lineas.
- Los sobrescritos de la API de Qt (`showEvent`, `closeEvent`, `paintEvent`)
  llevan `# noqa: N802`, porque su nombre lo impone el framework.
- **Todo widget que solo aloje una disposicion se crea con
  `widgets.contenedor()`.** Un `QWidget` plano hereda `FONDO` de la regla global
  del QSS y, dentro de una tarjeta, dibuja un rectangulo mas oscuro. El
  contenedor lleva `objectName = "Transparente"`, que el QSS deja sin fondo.
- Tests: `nucleo/` con pytest sobre SQLite en memoria. La UI se prueba a mano.

---

## 9. Importacion del Excel (una sola vez)

Fuente: **`CFA.xlsx`, en la raiz del proyecto.** Ojo: existe otra copia mas
antigua en `OneDrive - Ikalon\CFA.xlsx` que **no** se usa.

| Hoja | Uso |
|---|---|
| `Modulos` | `Tema \| Modulo / Reading \| Completado`. **75 modulos en 10 temas.** Se descarta la fila `Total completados / total modulos`, que es un artefacto. |
| `Registro Diario` | `Fecha \| Horas`. Genera una `sesion` con `origen='importada'` por fila con datos. Se descarta la fila `TOTAL HORAS`. |
| `Dashboard` | Se ignora: son formulas derivadas que la aplicacion recalcula. |

Las cabeceras se localizan **por su texto**, no por numero de fila, asi que el
importador tolera que la hoja se reorganice.

### Idempotencia

Reimportar el mismo archivo nunca duplica nada:

- **Modulos:** identificados por `(proyecto, materia, nombre)`. Si ya existen y
  cambio su estado, se actualizan; si no, se dejan igual.
- **Sesiones:** identificadas por su **fecha local** entre las de
  `origen='importada'`. El registro diario trae una fila por dia, de modo que la
  fecha basta como clave.

`ServicioImportacion` se divide en `analizar()` -> `aplicar()` para que la
interfaz pueda mostrar una vista previa antes de escribir. El asistente visual
llega en la Etapa 7; el servicio ya esta completo y probado.

Despues de importar, la aplicacion es la fuente oficial y el catalogo se edita
desde la vista Progreso. El proyecto MSc no necesita importador: sus materias se
crean a mano.

### El temario se corrige modulo a modulo

El curriculo del CFA se renumera cada ano: un LM cambia de nombre, o se parte en
tres. Antes, la vista Progreso solo sabia **anadir** un modulo, y al final de la
lista; corregir un nombre obligaba a reimportar el Excel o a entrar en el SQLite.

Ahora cada modulo tiene menu contextual —**renombrar, anadir debajo, subir, bajar
y eliminar**— apoyado en `RepositorioModulos.renombrar`, `mover`, `reordenar` e
`insertar_tras`.

Dos decisiones que importan:

- **Renombrar, no borrar y recrear.** El modulo conserva `completado` y
  `completado_en`. Un LM que cambia de nombre es el mismo LM.
- **`mover` reescribe el orden de toda la materia**, no intercambia dos valores.
  El importador crea los modulos con `orden` empatado, y ahi un intercambio de
  valores no cambiaria nada; `listar` desempata por nombre y el usuario veria que
  su clic no hace efecto.

Para partir un LM en varios: renombrar el original al primero de los nuevos —asi
se conserva su estado— y usar «Anadir modulo debajo» para el resto, en orden.
Cubierto en `tests/test_repositorio_modulos.py::test_partir_un_modulo_en_tres`.

### Corregir el temario entero de una vez

Para un cambio de curriculo completo, a mano seria inviable. Hay dos
herramientas, las dos con **simulacion por defecto** y respaldo antes de escribir:

| Herramienta | Que hace |
|---|---|
| `herramientas/temario_cfa.py` | **Datos, no codigo.** La lista de LM por tema, en su orden, mas `RENOMBRADOS`: los modulos que son el mismo con otro nombre. |
| `herramientas/sincronizar_temario.py` | Deja la base identica a esa lista: renombra, crea, borra y reordena, en ese orden y en una sola transaccion. |
| `herramientas/exportar_temario_excel.py` | Reescribe la hoja «Modulos» de `CFA.xlsx` desde la base. |

El temario vive en `herramientas/` y no dentro de `mukuwareru/` a proposito: la
aplicacion no trae ningun temario cableado, se lo da el usuario.

**Hay dos bases de datos, y es facil corregir la que no es.** `rutas.raiz_datos()`
devuelve la raiz del repositorio en desarrollo y la carpeta del ejecutable cuando
esta congelada, asi que la aplicacion instalada usa
`%LOCALAPPDATA%\Programs\Mukuwareru\datos\basedatos.db` — que `instalar.py` nunca
toca — y `python -m mukuwareru` usa `datos/basedatos.db` del repositorio. La del
usuario es **la instalada**. Ambas herramientas aceptan `--base` justo para esto:

```powershell
$base = "$env:LOCALAPPDATA\Programs\Mukuwareru\datos\basedatos.db"
python herramientas/sincronizar_temario.py --base $base            # simula
python herramientas/sincronizar_temario.py --base $base --aplicar
python herramientas/exportar_temario_excel.py --base $base --aplicar
```

Cinco cosas que costaron y conviene no volver a descubrir:

- **El orden de las operaciones importa.** Renombrar va primero para que el paso
  de borrado vea el nombre nuevo como «ya existe» y no lo elimine.
- **Se niega a borrar un modulo completado** salvo `--forzar`. Perder progreso por
  una errata en la lista seria caro y silencioso. Fue esta guardia la que atrapo
  que «Applications of Financial Statement Analysis» estaba completado en la base
  real aunque no lo estuviera en la de desarrollo.
- **`TEMAS_COMPLETOS` marca como hechos los modulos nuevos de un tema terminado.**
  Si el curriculo parte en dos un LM ya estudiado, dejar el nuevo pendiente diria
  que falta algo que en realidad esta hecho. Solo afecta a lo que se **crea**: un
  modulo desmarcado a mano no se vuelve a marcar al repetir la herramienta.
- **Al Excel se escriben booleanos, no `=FALSE()`.** openpyxl no calcula formulas,
  asi que una celda de formula recien escrita no tiene valor cacheado y el
  importador —que lee con `data_only=True`— la veria vacia: todos los completados
  se perderian en la siguiente reimportacion.
- **La fila de totales se lee y se vacia antes de escribir los datos.** Al pasar
  de 75 a 93 modulos las filas nuevas la pisan; capturarla despues guardaba un
  nombre de tema como etiqueta del total y dejaba una fila rota en medio.

La prueba de que el circulo cierra: reimportar el Excel regenerado sobre la base
ya sincronizada crea 0 materias, 0 modulos y actualiza 0.

La vista recuerda que materias estaban desplegadas (`VistaProgreso._desplegadas`):
cada edicion reconstruye la vista entera, y sin eso la seccion se cerraria en las
narices del usuario despues de cada renombrado.

### El peso de cada asignatura

Contar modulos trata igual una casilla de Ethics —17,5 % del examen— que una de
Derivatives. `materia.peso` (migracion 004) permite ponderar el avance por lo que
cada asignatura vale de verdad. Es **discrecional**: el CFA tiene sus pesos
publicados, el MSc los pone el usuario, y un proyecto sin pesos se comporta
exactamente como antes.

- **El peso es relativo, no un porcentaje.** Se normaliza dividiendo entre la
  suma del proyecto, asi que «3 / 2 / 1» y «50 / 33,3 / 16,7» dicen lo mismo.
  Cuadrar a 100 a mano seria un impuesto en cada materia que se anade.
- **Cero significa «sin peso»**, que es el valor de toda materia ya existente.
  `ResumenProgreso.porcentaje_ponderado` devuelve el porcentaje por modulos
  mientras nadie escriba un peso, para que quien lo pinte no pregunte antes.
- **Las dos cifras conviven con el mismo rango.** El conteo dice cuanto temario
  has tocado; el ponderado, cuanto del examen llevas. Ninguna sustituye a la otra:
  el Panel las ensena juntas (`_Cifras`) y Progreso las pone en la misma linea.
- **No hay peso por modulo.** Dentro de una asignatura los modulos se reparten su
  peso por igual. Ponderar tambien ahi convertiria marcar una casilla en un
  ejercicio de contabilidad.
- **Una materia con peso pero sin modulos queda fuera del calculo.** Contarla
  como un cero fijaria un techo permanente: un proyecto con todo hecho no llegaria
  nunca al 100 %. `ResumenProgreso.pesadas_sin_temario` las expone y el dialogo
  las avisa, porque un peso que no se usa suele ser un descuido.

`PESOS_CFA_NIVEL_I` (en `servicios/progreso.py`) trae el curriculo 2026 como
**propuesta**, nunca aplicada sola: el material oficial publica un rango por tema
y ahi esta el punto medio de cada uno, reescalado para sumar 100 sin salirse de
su rango. `pesos_cfa()` empareja por nombre normalizado con alias («Ethics»,
«FSA», «Equity»), que es como los llama el Excel. Es el unico temario cableado en
`mukuwareru/`, y solo como sugerencia editable de un boton del dialogo.

---

## 10. Roadmap

| Etapa | Entregable | Estado |
|---|---|---|
| 1 | Arquitectura, modelo de datos, navegacion, decisiones | **Completada** |
| 2 | Esqueleto, esquema + migraciones, tema, ventana, navegacion | **Completada** |
| 3 | Panel con datos reales + servicio de importacion | **Completada** |
| 4 | Progreso, Pomodoro, Ajustes y asistente de importacion | **Completada** |
| 5 | Biblioteca: escaneo, tarjetas, vigilancia, anadir PDFs | **Completada** |
| 6 | Visor PDF propio | **Completada** |
| 7 | Seleccion, notas, marcadores, resaltados | **Completada** |
| 8 | Estadisticas con QtCharts | **Completada** |
| 9 | Pulido, pruebas y generacion del `.exe` | **Completada** |
| 10 | Proyectos gestionables y barra lateral a medida | **Completada** |
| 11 | Notas sueltas: cuadernos, etiquetas y vinculos | **Completada** |
| 12 | Calendario, hitos y planificacion | **Completada** |
| 13 | Buscador global y plan de estudio opcional | **Completada** |
| 14 | Resultados de evaluaciones, pesos y temario editable (1.1.0) | **Completada** |

La Etapa 4 se reordeno respecto al plan original: Progreso venia en la Etapa 7,
pero es la pieza que libera del Excel y su servicio ya estaba listo, asi que se
adelanto y se entrego junto al Pomodoro. La Etapa 7 conserva las anotaciones.

En cada etapa: **disenar -> implementar -> documentar aqui.**

---

## 11. Implementado hasta ahora

**Etapa 2 · Esqueleto**

- Paquete `mukuwareru` ejecutable con `python -m mukuwareru`.
- Base de datos SQLite con esquema completo (9 tablas) y migrador con respaldo
  automatico.
- Modelos del dominio y `RepositorioProyectos`.
- Tema oscuro por tokens, paleta Fusion y 10 iconos SVG tintables.
- Ventana unica: barra lateral con proyectos y siete secciones, conmutador de
  vistas con recarga perezosa, tarjeta de cuenta atras y barra de estado.
- Creacion de proyectos desde la interfaz. (La siembra inicial de CFA Level I y
  MSc Financial Engineering que hubo aqui se retiro en la Etapa 10.)
- Persistencia de la geometria de la ventana en `datos/ajustes.json`.
- Registro rotativo en `logs/`.
- Especificacion de PyInstaller y script de construccion.

**Etapa 3 · Panel**

- Repositorios de materias, modulos, sesiones y documentos, con las
  agregaciones de tiempo resueltas en SQL.
- `ServicioProgreso`: avance global y por materia. Manual, sin ninguna relacion
  con el tiempo estudiado.
- `ServicioEstadisticas`: horas de hoy, de la semana (desde el lunes) y totales,
  pomodoros del dia y racha. `calcular_racha` es una funcion pura: acepta que el
  ultimo dia registrado sea ayer, para que la racha no se rompa por no haber
  estudiado aun esta manana.
- `ServicioImportacion` completo (`analizar` + `aplicar`), idempotente y
  probado contra el `CFA.xlsx` real.
- Vista Panel: seis tarjetas de metricas, anillo de progreso, barras por
  materia, ultimos PDFs y ultimas sesiones, con estados vacios explicativos.
- Widgets nuevos: `AnilloProgreso`, `BarraMateria`, `TarjetaMetrica`,
  `ListaResumen` y `contenedor()`.

**Etapa 4 · Progreso, Pomodoro y Ajustes**

- `RelojPomodoro`: maquina de estados en Python puro, sin Qt. El `QTimer` vive
  en la vista y llama a `avanzar(segundos)`, de modo que un test simula un ciclo
  entero en microsegundos. Al completarse una fase el reloj pasa a la siguiente
  y **se detiene**: encadenar descansos sin querer es peor que pulsar un boton.
- `RepositorioAjustes` (clave/valor) y `ServicioPreferencias`, que le pone tipos,
  valores por defecto y limites de cordura. Las duraciones del Pomodoro son
  globales; la fecha objetivo y la ruta de biblioteca son columnas de
  `proyecto`.
- Vista **Progreso**: materias plegables con casilla por modulo, y creacion,
  renombrado y borrado de materias y modulos. Es lo que hace innecesario un
  importador para el proyecto MSc.
- Vista **Pomodoro**: anillo de cuenta atras, iniciar/pausar/reiniciar/saltar,
  ciclo visible y registro automatico de cada fase terminada.
- `DialogoEtiquetar`: al terminar una sesion de trabajo pregunta que materias se
  estudiaron. Multi-seleccion, omitible y desactivable. Sin el no existiria el
  dato de «tiempo por materia»; con el, no obliga a nada.
- `DialogoImportar`: asistente con vista previa en arbol (materias, modulos,
  sesiones y filas descartadas) antes de escribir nada.
- Vista **Ajustes**: duraciones, sesiones por ciclo, pregunta de materias, fecha
  objetivo y ruta de biblioteca.
- `Contexto.notificar_cambio(origen)`: cuando una vista escribe, las demas se
  marcan como sucias. Se excluye la vista de origen para que no se reconstruya
  a si misma y pierda el scroll o las secciones desplegadas.

**Datos reales cargados:** CFA Level I con 10 materias, 75 modulos,
**32 completados (43 %)** y 6 h en 3 sesiones importadas.

**Etapas 5 a 9 · Biblioteca, visor, anotaciones, estadisticas y release**

- `ServicioBiblioteca`: escaneo recursivo que reconcilia disco y base de datos.
  Identifica por **huella** (tamano + MD5 parcial), de modo que renombrar o
  mover un PDF conserva su posicion de lectura y sus anotaciones.
- Vista **Biblioteca**: rejilla de tarjetas, buscador, vigilancia de la carpeta
  con `QFileSystemWatcher` y boton **Anadir PDFs**, que copia los archivos
  elegidos a la carpeta del proyecto.
- **Visor propio** (`mukuwareru/ui/lector/`): `Disposicion` (mapeo lienzo <->
  puntos PDF), `CachePaginas` (LRU por pagina y zoom), `VistaPaginas`
  (`QAbstractScrollArea` con scroll continuo, zoom, seleccion y capas),
  `PanelLateral` (miniaturas perezosas, indice y busqueda) y `VistaLector`.
- Anotaciones sobre la seleccion: destacar, nota, marcador y copiar. Los
  resaltados guardados se repintan sobre la pagina.
- Vista **Anotaciones**: lista filtrable por tipo y texto que devuelve a la
  pagina exacta del PDF.
- Vista **Estadisticas**: metricas y tres graficos de barras con QtCharts
  (dia, semana, mes), mas tiempo por materia y por proyecto.
- **El tiempo por materia es un reparto, no una comparacion**: una sesion
  etiquetada con varias materias divide su duracion a partes iguales entre
  ellas, y el porcentaje se mide contra el tiempo total de estudio (incluido lo
  «Sin clasificar»). Antes se sumaba la sesion completa a cada etiqueta y el
  porcentaje se media contra la materia mayor: la primera salia siempre al
  100 %, las partes sumaban mas que el todo y una sesion marcada con cinco
  materias de golpe inflaba a las cuatro que apenas se habian tocado.
- **Configuracion del Pomodoro movida a su propia vista**: cada sesion de
  estudio es distinta y cambiar las duraciones debe costar un clic. Con el
  reloj corriendo los cambios quedan pendientes y se aplican al parar, para no
  reiniciar la fase en curso sin avisar.
- Icono propio, ejecutable compilado e instalador.

- **120 tests**, incluida la comprobacion automatica de la regla arquitectonica.
- **`herramientas/humo.py`**: prueba de humo que arranca la aplicacion completa
  contra una base de datos temporal y ejercita todas las vistas de extremo a
  extremo. Cubre lo que pytest no puede cubrir sin un arnes de UI.
- **`herramientas/pdf_de_prueba.py`**: genera PDFs con texto extraible para
  desarrollar el visor sin depender de material con derechos de autor.

**Etapa 10 · Proyectos gestionables y barra lateral a medida**

- **Fuera la siembra.** `aplicacion.py` ya no crea proyectos. `PanelBienvenida`
  (en el conmutador, no un modal) cubre el arranque en frio y el «borre el
  ultimo», e `ir_a` y `abrir_lector` pasan por `_hay_proyecto()`.
- **Un agujero cerrado por el camino:** el Pomodoro corria sin proyecto y
  descartaba el tiempo en silencio, porque `_registrar` salia con `None`. La
  guardia esta en `_alternar` —que es por donde entra tambien la mini ventana— y
  el boton sale deshabilitado. La conexion a `proyecto_cambiado` es propia y no
  se apoya en `recargar`: sin proyecto la vista no se muestra, asi que la recarga
  perezosa nunca correria.
- **`ServicioProyectos`**: crear, guardar, renombrar (con el movimiento de la
  carpeta y su plan B), archivar, reordenar, `resumen_borrado` y eliminar. Es la
  pieza que impide que un renombrado borre anotaciones; ver §4.
- **`DialogoProyecto`**, uno solo para crear y editar: nombre, icono entre los 9
  SVG (retintados con el color elegido, para ver como quedara en la barra),
  color entre los 8 de `tokens.SERIE` —sin `QColorDialog`—, fecha objetivo que
  ahora **si** se puede dejar vacia, y carpeta de PDFs. Devuelve `DatosProyecto`
  y no persiste nada.
- **Menu contextual en la barra lateral**: editar, subir, bajar, archivar y
  eliminar. La barra solo emite senales; sigue sin tocar la base de datos.
  Ajustes ya no duplica los campos de fecha y ruta: abre el mismo dialogo.
- **Barra lateral a medida**: orden y visibilidad por arrastre en Ajustes con un
  `QListWidget` en `InternalMove`, que da el arrastre y el ocultado hechos. Se
  descarto arrastrar los propios botones de la barra: cuatro manejadores de
  raton, un indicador de insercion y perder las reglas `#ElementoNav` del QSS,
  el `QButtonGroup` exclusivo y el `checked` de la seccion activa. Guarda al
  soltar y al marcar, y la aplicacion abre en la primera seccion visible.
- Tests nuevos: `test_servicio_proyectos.py` (el renombrado, incluido el fallo
  de `rename`) y la disposicion en `test_preferencias.py`. En `humo.py`, tres
  bloques nuevos: `_estado_vacio`, `_crud_proyectos` y `_disposicion_secciones`;
  `_navegacion` recorre ahora `SECCIONES` y no una lista escrita a mano.

**Etapa 11 · Notas**

- **Migracion 002**: `cuaderno`, `seccion`, `nota`, `etiqueta`, `nota_etiqueta` y
  `nota_vinculo`. Solo `CREATE`: ni una fila existente se toca. Las decisiones
  estan en §4.
- **Tres ejes de clasificacion ortogonales**: la **estructura** dice donde vive
  una nota (cuaderno → seccion, exactamente una, con `seccion_id NOT NULL` para
  que una nota rapida no obligue a decidir nada); las **etiquetas** dicen de que
  trata (N a N, transversales); los **vinculos** son el interlinkado.
- **Una sola seccion «Notas»**, que absorbio el lugar de «Anotaciones» en la
  barra lateral. La clave `anotaciones` que quedara en las preferencias de
  alguna instalacion la descarta sola `reconciliar_orden` (§3), sin migracion.
  **El arbol solo tiene cuadernos y secciones reales** — nada de un cuaderno
  virtual «En PDF» con marcadores y resaltados: eso era mezclar dos cosas
  distintas (una nota con subsecciones que se puede ligar, y un resaltado
  atado a una pagina) en el mismo arbol, y confundia mas de lo que ayudaba. Los
  marcadores y resaltados siguen viviendo en el lector, con su propia edicion
  y borrado; lo unico que cruza hacia Notas es "Llevar a un cuaderno…", que
  crea una nota de verdad ya ligada al resaltado.
- **«Relacionado con»**, bajo el editor: liga la nota a una materia, un modulo o
  un PDF y una pagina *despues* de haberla escrito, que es el caso que las
  anotaciones no cubren. Sin ese panel esto seria un bloc de notas.
- **El interlinkado se lee en las dos direcciones.** Nueva pestana
  **Relacionadas** en el lector (`por_documento(doc, pagina)`, que incluye las
  notas del documento entero porque son relevantes en cualquier pagina),
  insignia con el numero de notas en las tarjetas de la Biblioteca, y salto de
  vuelta del PDF a la nota con `VentanaPrincipal.abrir_nota`.
- **Del resaltado a la nota**: «Llevar a un cuaderno…» en el menu del lector crea
  el resaltado *y* una nota suelta ya ligada a el. La anotacion **no se borra**:
  sigue pintada en su pagina; la nota es donde desarrollar la idea.
- **Guardado perezoso** en el editor, como el de la posicion de lectura: un
  temporizador de 1,5 s mas un volcado forzado al cambiar de nota, de nodo, al
  recargar y al salir de la vista. Ni escribir en cada tecla ni perder texto.
- El titulo se deduce de la primera linea si se deja vacio: pedirlo antes de
  escribir corta el impulso de apuntar algo, y una lista de «(sin titulo)»
  tampoco sirve.
- `_crear` del lector pasa a **devolver** la anotacion creada. Buscar «la ultima»
  en `self._anotaciones` daria otra: esa lista se reordena por pagina al recargar.
- Tests nuevos: `test_texto.py` y `test_notas.py`, con el `CHECK` de
  exclusividad, el indice con `COALESCE`, la busqueda que **no** encuentra dentro
  del base64 y el caso que justifica la tabla aparte —borrar el PDF no borra la
  nota—. En `humo.py`, el bloque `_notas` recorre todo ese camino de extremo a
  extremo.

**Etapa 12 · Calendario y planificacion**

- **Migracion 003**: `hito`, `bloque_plan` y `bloque_materia`, con un
  `INSERT … SELECT` que convierte la `fecha_objetivo` de cada proyecto en su
  hito principal. Las decisiones estan en §4.
- `repartir_cumplimiento`, funcion pura con sus catorce tests: el solape de
  horas, el reparto sin duplicar, las sesiones sin etiquetar, `sesion.fin` en
  NULL y el umbral del 80 % —levantarse cinco minutos antes de un bloque de una
  hora no es fallarlo—.
- `ServicioCalendario.rango()` compone un mes con **tres consultas** y el
  reparto en memoria. Nunca una consulta por dia: serian 93 viajes por mes.
- Vista **Calendario**: rejilla con mapa de calor de horas reales, borde
  punteado en los dias planificados y estrella en las fechas clave; panel del
  dia con los bloques y su **porcentaje** —no un aprobado/suspenso, para que se
  vea de donde sale el reparto—, las sesiones reales y los hitos.
- `formato.fecha_larga` para las cabeceras del calendario.

**Ajuste posterior · Notas mejor integradas**

Tres correcciones despues de usar la Etapa 11 de verdad:

- **Una sola lista en el lector.** Las pestanas «Notas» y «Relacionadas» eran
  dos sitios para la misma pregunta —«¿que tengo escrito sobre esto?»—. Ahora
  las anotaciones ancladas y las notas de cuaderno conviven ordenadas por
  pagina, cada fila con su tipo por color y su ubicacion. `PanelRelacionadas`
  desaparecio.
- **Cada nota lleva su ruta.** `NotaListada` gana `destinos`, resueltos a nombres
  con **una sola consulta** (`_DESTINOS`, un UNION cuyo `CASE` fija el orden:
  materia, modulo, PDF). `ruta()` compone
  `Cuaderno -> Seccion -> Nota -> destinos`, que va en la fila y no en un
  tooltip: saber donde vive una nota y de que habla es lo que uno busca al
  recorrer la lista.
- **La materia filtra los modulos.** `DialogoVincular` sustituye a los tres
  caminos separados de antes, donde la lista de modulos era plana y salian los
  75 del proyecto juntos: era facil ligar una nota de Ethics a un modulo de
  Corporate Issuers sin notarlo. La materia ya relacionada se ofrece como filtro
  inicial. Lo alimenta `ServicioNotas.catalogo_para_vincular`, que agrupa los
  modulos **por materia** en lugar de aplanarlos.
- **Desde el PDF se hace todo**: crear una nota de cuaderno ligada a la pagina
  (escribiendola **sin salir del documento**; saltar a la vista Notas cerraria
  el lector y perderia la pagina, que es justo lo que hace util anotar desde
  dentro), relacionar una nota que ya existe, quitar la relacion y abrir la nota
  completa con doble clic.

**Recordatorio de incumplimiento y % de incumplimiento en Estadisticas**

- `ServicioCalendario.ultimo_incumplimiento(proyecto_id, hoy)` mira los ultimos 7
  dias **hacia atras** (nunca hoy ni manana: un bloque que aun no paso no es un
  incumplimiento) y devuelve el bloque planeado mas reciente cuyo
  `Cumplimiento.cumplido` es falso. El Panel lo pinta en una tarjeta «No
  cumpliste», visible solo si hay algo que avisar.
- `ResumenCumplimiento` (en `servicios/calendario.py`) agrega, sobre un rango de
  dias, cuantos tuvieron plan, cuantos se cumplieron del todo y cuantos
  segundos planeados quedaron sin estudiar; expone `pct_dias_incumplidos` y
  `pct_horas_incumplidas`. Estadisticas anade dos tarjetas —«Dias incumplidos» y
  «Horas incumplidas»— sobre la misma ventana de 30 dias que ya usa el grafico
  diario. Sin bloques planeados en el rango, las tarjetas muestran «—» en lugar
  de un 0 % que insinuaria un cumplimiento perfecto que nadie planeo.
- Ambas cifras se calculan sobre `rango()`, igual que todo el calendario: nada
  nuevo que guardar ni que desincronizar.

**Etapa 13 · Buscador global y plan de estudio**

- **Ctrl+K** (`ui/paleta.py` + `ServicioBusqueda`): un campo que busca a la vez
  en notas, anotaciones, materias, modulos, PDFs y hitos, agrupa por familia y
  salta al sitio exacto. La navegacion se apoya **entera** en lo que ya existe
  —`ir_a`, `abrir_lector`, `abrir_nota`—: la paleta no aprende caminos nuevos.
  Las flechas y el Enter se redirigen del campo a la lista con un `eventFilter`,
  para no tener que bajar la mano al raton, y los separadores de familia se
  saltan al moverse. Tope de 8 por familia: construir lo que no se va a ver es
  trabajo tirado.
- **Plan de estudio opcional** (`ServicioPlan`): minutos por dia de la semana,
  guardados en `ajuste` **por proyecto** (`plan.minutos_por_dia`, `plan.activo`).
  Si no se activa, no aparece nada; un plan que nadie pidio no deberia ponerse a
  dar cuentas en la pantalla principal.
- `diagnostico()` compara el ritmo necesario para llegar al proximo hito con el
  real de las **ultimas cuatro semanas** —lo que importa es si el ritmo de ahora
  llega, no el de hace seis meses—, estimando el coste por modulo con el
  historial del propio proyecto.
- `prever()` + `generar()`: vista previa antes de escribir, como el asistente de
  importacion, e **idempotente** gracias a `RepositorioBloques.existe_en`.
- **Repaso activo calculado, no repeticion espaciada.** Dos preguntas sobre los
  datos que ya hay —modulos completados hace mas de tres semanas y notas sin
  releer en un mes—. Sin cola, sin intervalos, sin estado: ignorarlas durante un
  mes no deja nada roto, y un test comprueba que pedirlas no escribe ni una fila.

**Cierre de la 1.0.0 · Trabajo indefinido**

Lo ultimo que entro en la version. El detalle esta en §6 quater; en una linea:
una sesion de estudio sin duracion fijada, con su cronometro de Python puro
(`nucleo/servicios/cronometro.py`), su sitio en el calendario y su pregunta de
tema al terminar. El reloj flotante y el de la barra lateral aprendieron a
contar hacia arriba, y `formato.duracion_reloj` gano el campo de horas.

Con esto la aplicacion cubre las dos formas de cronometrar que se usan de
verdad: el recorrido de bloques cuando se sabe cuanto se va a estudiar, y el
cronometro libre cuando no.

---

## 11 bis. La 1.1.0 · Resultados, pesos y temario editable

La 1.0.0 respondia a dos preguntas: **cuanto temario llevo** (Progreso) y
**cuanto he estudiado** (Estadisticas). Faltaba la tercera, que es la que predice
el aprobado: **cuanto se**. Un simulacro era solo una fecha en `hito`; no habia
donde anotar que sacaste 38/50 y que Derivatives se te hundio.

**Restriccion transversal de esta version:** la aplicacion no es solo para el
CFA. Todo lo que entro sirve igual para un master, una carrera, un curso o una
certificacion. De ahi dos decisiones que se notan en todo el codigo: la entidad
se llama `Evaluacion` y no «mock», y la escala es **puntos obtenidos sobre
puntos posibles**, de modo que 38/50, 8,5/10, 4,2/5 y 61/100 caben sin convertir
nada. El porcentaje se calcula y no se guarda, como toda estadistica de la casa.

### Seccion Resultados

Tres niveles, cada uno ponderado por el de abajo. Es el mismo patron de
`materia.peso`, aplicado dos veces:

| Nivel | Como sale |
|---|---|
| Evaluacion | puntos obtenidos / posibles |
| Asignatura | media de sus evaluaciones ponderada por `evaluacion.peso` |
| Proyecto | media de las asignaturas ponderada por `materia.peso` |

Decisiones que costaron y conviene no volver a discutir:

- **`evaluacion.peso` por defecto es 1, y `materia.peso` es 0.** La asimetria es
  deliberada. En la materia, cero significaba «sin ponderar, vuelve al conteo de
  modulos», porque habia un modo anterior al que volver. En las evaluaciones no
  lo hay: la media natural de tres simulacros es la aritmetica, que es
  exactamente «todos con peso 1». Con el defecto a cero, el primer usuario veria
  «—» en todas las notas hasta escribir pesos a mano.
- **El peso vive en la evaluacion, no en cada linea del desglose.** Un examen que
  pesara distinto en cada asignatura no cabe hoy. La valvula de escape es
  aditiva: `evaluacion_materia.peso REAL` y `COALESCE(em.peso, e.peso)`.
- **El desglose es opcional y no tiene que cuadrar con la nota global.** No hay
  CHECK que lo exija: los simulacros redondean por tema, y un desglose parcial
  («de Ethics saque 14/18, del resto no me lo dieron») es informacion util que un
  CHECK tiraria. El dialogo **avisa** del descuadre y ofrece «Usar la suma del
  desglose»; no lo impide.
- **`hito_id` es `ON DELETE SET NULL`, no CASCADE.** Borrar la fecha prevista del
  calendario no puede llevarse por delante la nota que sacaste. Un indice unico
  parcial garantiza como maximo un resultado por hito.
- **Resultados no toca `ServicioProgreso`.** Progreso mide temario cubierto;
  Resultados mide rendimiento. Son dos ejes y mezclarlos en un porcentaje seria
  mentir: se puede llevar el 30 % del temario y sacar un 70 % en un simulacro.
  Comparten `materia.peso` y nada mas, y un test lo comprueba explicitamente.
- **Una asignatura con peso y sin ninguna nota queda fuera del calculo**, igual
  que `pesadas_sin_temario` en el progreso y por la misma razon: contarla como un
  cero fijaria un techo permanente. `ResumenResultados.sin_desglose` expone el
  caso simetrico —evaluaciones que cuentan para la media pero no para ninguna
  asignatura—, porque callarlo haria que las dos cifras discreparan sin
  explicacion.

### Atencion por materia

Estadisticas medía solo tiempo, y desde la 004 se sabe lo que cada asignatura
pesa; nadie cruzaba las dos cosas. `ResumenProgreso.desvio_atencion` lo hace, y
vive en el nucleo justamente para poder probarse sin abrir una ventana.

El denominador del reparto real es **solo el tiempo clasificado**. Incluir
`segundos_sin_clasificar` haria que la suma nunca llegara a 100 y que **todas**
las materias salieran desatendidas a la vez: la tarjeta acusaria de no etiquetar
las sesiones, no de desatender un tema. Lo no clasificado se dice en el pie.

El umbral de «desatendida» son **5 puntos porcentuales**, no un ratio: con cuotas
pequenas como Derivatives (6,3 %) un ratio relativo marcaria cualquier variacion
de media hora.

`BarraAtencion` es un widget aparte y no un tercer modo de `BarraMateria`: aquella
pinta una magnitud y aqui hacen falta dos comparables en el mismo eje. De
`BarraMateria` dependen a la vez el Panel, Progreso y Resultados.

### Temario editable

Cuatro asimetrias que llevaban desde el principio:

- **Reordenar materias.** Los modulos tenian `mover`/`reordenar` y las materias
  no. Se copia el patron exacto, incluido reescribir el orden entero en vez de
  intercambiar dos valores: lo importado comparte `orden = 0`.
- **Mover un modulo a otra materia** conservando `completado` y `completado_en`.
  Antes habia que borrar y recrear, que es justo lo que `renombrar` evita. Ante
  una colision con el `UNIQUE (materia_id, nombre)` devuelve `False` en vez de
  dejar subir el `IntegrityError`.
- **Marcado masivo.** `UPDATE ... WHERE materia_id = ? AND completado <> ?`. Ese
  `AND` no es una optimizacion: sin el, volver a marcar una materia reescribiria
  `completado_en` de lo ya hecho y reiniciaria en silencio las sugerencias de
  repaso.
- **Color propio de materia.** `materia.color` existia desde 001 y era una
  columna muerta: nadie la escribia y las vistas pintaban por posicion, asi que
  el color de una materia cambiaba solo al renombrarla. El respaldo vive en un
  unico sitio (`tokens.color_o_serie`), y `conteo_por_materia` devuelve el color
  para que el Panel no necesite otra consulta. **Invariante:** esa consulta y
  `RepositorioMaterias.listar` ordenan igual (`orden, nombre`); si divergen, el
  respaldo por posicion pinta distinto en cada vista.

Ademas, marcar una casilla ya no reconstruye la vista entera. `SeccionMateria`
distingue `cambiada` (estructural: anadir, renombrar, mover, borrar, color) de
`marcado`, que solo reescribe el resumen y repinta su propia barra. Marcar los
nueve modulos de un tema eran nueve reconstrucciones, con su perdida de scroll.

### Manual de atajos en Ajustes

`mukuwareru/ui/atajos.py` es a los atajos lo que `SECCIONES` a las vistas: **la
unica declaracion**. Quien crea el `QShortcut` pide ahi la combinacion
(`atajos.secuencia("buscar")`), y la tarjeta de Ajustes se pinta recorriendo esa
misma lista. Cambiar una tecla cambia la ayuda sola, porque no hay dos sitios que
cuadrar — que es exactamente como se desincroniza siempre una documentacion.

Las combinaciones se ensenan preguntandoselas a Qt en formato nativo, no con un
texto escrito a mano, de modo que lo que se lee es literalmente lo que esta
enganchado. Las entradas sin `tecla` —las flechas del buscador, el Esc que cierra
un dialogo— son solo documentacion: no se enganchan con un `QShortcut` sino en un
`eventFilter` o por el comportamiento normal de Qt, pero al usuario le da igual
como esten hechas y el objeto de la lista es que sepa que existen.

La prueba de humo comprueba las dos direcciones: que la tarjeta lista los trece
atajos del catalogo, y que **la ventana no engancha ninguno que no este
declarado**.

Ajustes paso a vivir dentro de un `QScrollArea`, como las demas vistas: con cinco
tarjetas ya no cabe entera en una ventana pequena.

### Copia de seguridad, y por que no es una funcion de la aplicacion

`herramientas/respaldar.py` (con `Respaldar.cmd` para el doble clic). Vive fuera
igual que `sincronizar_temario.py`: la aplicacion se dedica a estudiar.

La distincion que sostiene todo esto: la base **no** puede vivir en OneDrive
—sincronizar un SQLite abierto puede corromperlo, porque el archivo y su WAL
cambian a la vez y el sincronizador puede subir uno sin el otro— pero un
**respaldo** si, porque es un archivo cerrado, consolidado y que nadie vuelve a
abrir. Por eso el destino por defecto es `OneDrive/Mukuwareru-Respaldos`.

- Copia con `sqlite3.backup()`, no con un `copy`: consolida el WAL y el destino
  queda consistente aunque la aplicacion estuviera abierta.
- La copia se pasa a `journal_mode = DELETE` antes de cerrarla. Si no, hereda el
  WAL del original y deja un `-wal` y un `-shm` al lado que OneDrive
  sincronizaria como si fueran respaldos; un respaldo tiene que ser **un**
  archivo que se pueda copiar solo.
- Se **verifica** antes de darla por buena (`PRAGMA integrity_check` y un
  recuento de filas) y, si falla, se borra: una copia mala es peor que ninguna,
  porque cuenta como respaldo y no lo es. Una copia sin proyectos se rechaza
  tambien, porque casi siempre significa que se respaldo la base equivocada.
- El origen por defecto es la base **instalada**, no la del repositorio. Hay dos
  y respaldar la que no es seria el fallo silencioso mas facil de cometer aqui.
- Conserva las catorce ultimas y poda el resto.

Lo unico que respaldaba algo hasta ahora era el migrador, que vuelca una copia al
subir de version de esquema **en la misma carpeta que el original**: sirve para
deshacer una migracion, no para sobrevivir a un disco que falla.

### Dos arreglos de paso

- `ServicioPlan.sugerencias` ordenaba por la **cadena** del motivo, asi que «hace
  25 dias» iba antes que «hace 9 dias» y el corte a cinco se quedaba con las
  equivocadas. Ahora ordena por la antiguedad real.
- El docstring de `RepositorioMaterias.fijar_pesos` citaba un `reordenar` que no
  existia. Ahora existe.

---

## 11 ter. La 1.2.0 · Carga declarada, calculadora de notas y grafo

Tres capacidades que se apoyan **en las entidades que ya existian**. Ninguna crea
un segundo planificador, un segundo sistema de progreso ni una segunda copia de
las materias. La regla que goberno toda la version:

> Antes de crear algo nuevo, buscar como conectarlo con algo que ya existe.

Lo que **no** hubo que crear, porque ya estaba: la disponibilidad por dia de la
semana (`PlanSemanal`, desde la 1.0), los deadlines (`hito`), las evaluaciones
con peso relativo y peso cero (`evaluacion`, migracion 005), el progreso
(`Modulo.completado`) y el peso por asignatura (migracion 004).

### Migracion 006 · Carga de estudio

`materia` gana `horas_estimadas`, `horas_restantes_manual`, `prioridad`
(0 a 3, por defecto 1 = Media) y `fecha_limite`; `modulo` gana
`horas_estimadas`. Todo opcional salvo la prioridad, que tiene valor neutro: un
proyecto que no rellene nada se planifica **exactamente** como en la 1.1.0.
Mismo criterio que el peso de la 004.

`ServicioCarga` cruza tres fuentes que ya existian: las horas declaradas, el
tiempo real de `RepositorioSesiones.segundos_por_materia` —que ya repartia la
duracion de una sesion entre las materias con que se etiqueto— y el conteo de
modulos. El desglose por modulos manda sobre la estimacion de la materia: es el
dato mas fino y quien se molesto en escribirlo no espera que se ignore.

La sobrescritura manual de las horas restantes existe porque la resta
«estimadas menos dedicadas» se equivoca a menudo —se estudio sin cronometro, o
el tema se entendio en la mitad de tiempo— y corregir el **resultado** no puede
obligar a falsear ni la estimacion ni el historial de sesiones.

La integracion con el planificador es **una bifurcacion de tres lineas** en
`ServicioPlan.diagnostico`: si hay horas declaradas se usan, si no se sigue
extrapolando del historial como siempre. `prever` y `generar` no se tocaron.

`fecha_limite` de una materia **no** es un `hito` y no llena el calendario: un
hito es una fecha que existe por si misma (el examen es el dia 10 lo mire quien
lo mire), esto es una meta propia de la asignatura.

### Migracion 006 tambien · Evaluaciones pendientes

`evaluacion.puntos_obtenidos` pierde el `NOT NULL`. Una evaluacion **sin nota**
es una evaluacion **pendiente**: declarada con su peso y su fecha, todavia sin
corregir. Es lo unico que hacia falta para poder preguntar «que necesito en el
final» antes de hacerlo.

SQLite no sabe quitar un `NOT NULL` con `ALTER`, asi que la tabla se recrea con
el procedimiento estandar. Recrear una tabla es la operacion que mas facilmente
pierde datos, y por eso hay un test dedicado que migra una base parada en la 005
con una evaluacion y su desglose, aplica el resto y comprueba que todo sigue ahi
con el mismo id.

Una pendiente **no entra en ninguna media** ni en la curva de evolucion: un cero
en un examen que nadie ha hecho diria «vas fatal» cuando lo cierto es «aun no lo
has hecho».

### Calculadora de notas y escala

La escala es **presentacion, no almacenamiento**. Las notas se siguen guardando
como puntos obtenidos sobre posibles, que es como vienen los examenes; la escala
(`minimo`, `maximo`, `aprobado`) solo decide como se leen y vive en la tabla
`ajuste` por proyecto, igual que `plan.minutos_por_dia`. Cambiarla de 0-100 a
0-5 no reescribe ni una nota, y el CFA se queda en porcentaje mientras el MSc se
ve en 0-5 con aprobado 3,0. **Ninguna tabla nueva.**

`calcular(evaluaciones, escala, supuestos)` es una **funcion pura**:

```
necesaria = (aprobado * peso_total - aporte_actual) / peso_pendiente
```

Que sea pura es lo que garantiza el requisito de que un escenario no modifique
una nota real: `simular()` lee, sustituye en memoria y devuelve; no tiene por
donde escribir. Las evaluaciones de **peso cero** —los mocks del CFA— siguen en
la lista y en las medias sin ponderar, pero no aportan peso: no mueven la nota
final porque no vale nada, que es justo lo que declara un peso de cero.

Un detalle de aritmetica: el enunciado de la version pedia «2,10 acumulado sobre
el 50 % evaluado, aprobado 3,0, necesario 3,80». La cuenta da **3,90**, y manda
la cuenta. Queda anotado en el test para que no se «arregle» al reves.

### Migracion 007 · Grafo de dependencias

Un `grafo_nodo` **no es un objeto de estudio**: es un puntero a uno que ya
existe —materia, modulo, hito o evaluacion— mas su posicion en el lienzo. Cuatro
claves foraneas excluyentes con `CHECK`, calcando `nota_vinculo` y por la misma
razon: un par generico `(tipo, objeto_id)` tira la integridad referencial y deja
nodos apuntando a materias borradas. Con FK reales, borrar una materia se lleva
su nodo y sus aristas gratis.

No hay nombre, ni color, ni horas, ni **estado** guardados. «Bloqueado /
Disponible / En curso / Completado» se **calcula** en `ServicioGrafo` cruzando
las aristas con el progreso real. Guardarlo seria el segundo sistema de progreso
que esta aplicacion no tiene: marcar un modulo en Progreso dejaria el grafo
mintiendo. Por eso `ServicioGrafo` **no tiene `marcar()`**.

«Arrastrar no duplica» es un invariante **de la base de datos**, no una
comprobacion de la interfaz: cuatro indices unicos parciales, uno por destino.
Soltar dos veces la misma materia mueve su nodo.

**Y/O en una sola columna entera.** Dentro del mismo `grupo` las aristas son
alternativas (O); entre grupos son todas obligatorias (Y). «Calculo Y
(Probabilidad O Estadistica)» son tres filas. Es forma normal conjuntiva y cubre
ramificacion, convergencia y caminos alternativos. Lo que evita: **nodos
operador** —un segundo tipo de nodo sin entidad detras, que habria que dibujar,
mover y derivarle un estado, o sea el clon de n8n que no se queria— y una tabla
`grafo_grupo` cuya unica columna util seria su id.

Los ciclos **no** se impiden con un trigger: un `CHECK` no puede recorrer una
tabla, y una CTE recursiva en un trigger meteria reglas de negocio dentro del
esquema, que es peor que SQL fuera de un repositorio. Los impide
`ServicioGrafo.conectar` con un recorrido sobre las aristas ya cargadas, que son
decenas de filas.

`estado_de` y `cierra_ciclo` son funciones **puras de modulo**, como
`repartir_cumplimiento`: la tabla de verdad del Y/O y el diamante que **no** es
un ciclo se prueban sin abrir una base.

### El lienzo: `QGraphicsView`, al contrario que el lector

El visor de PDF es custom porque `QPdfView` esconde el mapeo viewport-pagina
(§5). Aqui no se da esa razon: `mapToScene` es publico, y con `QGraphicsView`
vienen resueltos el zoom bajo el cursor, el paneo, la deteccion de clics, la
seleccion por rectangulo y el orden Z. Cuando Qt da el mapeo, se usa Qt.

**Aviso que cuesta una tarde descubrir:** un `QGraphicsItem` no es un widget y
**el QSS no lo alcanza**. Los colores de los nodos y las aristas salen
directamente de `ui/tema/tokens.py` dentro de `paint()`, igual que en
`widgets/anillo.py`. Una regla en `oscuro.qss` para `ItemNodo` no haria nada.

Las posiciones se guardan en coordenadas de **escena**, no en pixeles del
viewport —misma decision que los rectangulos de las anotaciones en puntos del
PDF—, y se persisten en `mouseReleaseEvent`, no en cada `itemChange`: un
arrastre dispara decenas de eventos y serian decenas de `UPDATE` para mover una
tarjeta diez pixeles.

Doble clic en un nodo **navega** a la seccion donde esa informacion ya vive
—Progreso, Calendario o Resultados—, con el mismo patron que
`biblioteca.abrir_documento`. El grafo no edita la entidad y no tiene casilla de
«completado»: ese es el punto entero del diseno.

El panel lateral ofrece solo lo que **no** esta colocado, asi que la
no-duplicacion se nota antes de intentarla; por debajo los indices unicos la
rematan.

### Lo que se dejo fuera a proposito

Guias, minimapa, autoorganizacion del grafo, deshacer, y una integracion
profunda entre Pomodoro y planificador. Manda §1: funcionalidad por encima de
complejidad visual.

Tambien se decidio **no** rellenar por codigo el MSc Financial Engineering. El
proyecto existe vacio y sus materias se crean a mano desde Progreso, como estaba
previsto; el grafo se dibuja despues. Sembrar un temario inventado seria
exactamente el tipo de dato que luego nadie sabe de donde salio.

---

## 12. Pendientes de decision

- Ubicacion real de los PDFs, para fijar la ruta por defecto de `Library/`.
- Estructura de materias del MSc Financial Engineering, que se creara a mano
  desde la vista Progreso.

**Resuelto en la 1.2.0 por otra via:** que el plan deje de contar casillas
crudas. En vez de derivar «modulos equivalentes» del peso del examen —el diseno
que estaba apuntado aqui—, la 1.2.0 deja **declarar las horas** de cada
asignatura, que es un dato y no una extrapolacion, y `ServicioPlan.diagnostico`
las usa cuando existen. Sin horas declaradas el comportamiento es exactamente el
de la 1.1.0. Ver §11 ter.

**Resuelto fuera de la aplicacion:** la copia de seguridad, con
`herramientas/respaldar.py` (ver §11 bis). Se decidio a proposito que **no** sea
una funcion de la aplicacion.

**Descartado a proposito:** distinguir dos tipos de proyecto (examen frente a
carrera). Bifurcaria Panel, Progreso y Ajustes, y obligaria a pensar dos veces
cada funcion futura. Lo unico que difiere de verdad es que una carrera tiene
varias fechas y un examen una sola, y esa valvula de escape se abre en la
Etapa 12: una tabla `hito`, sin modos, con `proyecto.fecha_objetivo` espejada en
el hito principal.

**Descartado en la Etapa 10:** el Pomodoro con contexto (`sesion.modulo_id` y
`sesion.documento_id`, para iniciar una sesion desde un modulo o desde el PDF
abierto y que quede etiquetada sola) y un sistema completo de repaso espaciado.
El etiquetado a posteriori con `DialogoEtiquetar` cubre el dato de «tiempo por
materia» sin obligar a nada, y el repaso llegara como sugerencias calculadas en
la Etapa 13, sin tablas de estado que mantener.

---

## 13. Comandos

```powershell
python -m pip install -r requirements-dev.txt   # entorno de desarrollo
python -m mukuwareru                              # ejecutar
python -m pytest -q                             # tests del nucleo
python herramientas/humo.py                     # prueba de humo de la interfaz
python -m mypy mukuwareru/nucleo                  # tipado del nucleo
python -m ruff check .                          # linting

python herramientas/actualizar.py               # OBLIGATORIO tras cualquier cambio
python herramientas/actualizar.py --rapido      # igual, sin regenerar el instalador

python herramientas/construir.py                # compilar el .exe
python herramientas/instalar.py                 # instalar / actualizar esta maquina
python herramientas/empaquetar.py               # instalador para otras maquinas
python herramientas/copiar_datos.py <destino>   # llevar datos a una instalacion
python herramientas/respaldar.py                # copia verificada en OneDrive
herramientas\Respaldar.cmd                      # lo mismo, con doble clic
python herramientas/generar_icono.py            # regenerar mukuwareru.ico
```

Los tres ultimos pasos de compilacion los encadena `actualizar.py`; se listan
sueltos solo para poder repetir uno concreto. Ver la **regla de publicacion**
al principio de este documento.
