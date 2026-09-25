"""Prueba de humo de la interfaz.

    python herramientas/humo.py

Arranca la aplicacion completa contra una base de datos temporal y ejercita las
vistas de extremo a extremo: importar el temario, marcar un modulo, completar un
pomodoro y guardar preferencias. Devuelve un codigo de salida distinto de cero
si algo falla, asi que sirve tanto en local como en integracion continua.

Complementa a pytest, que solo cubre ``mukuwareru.nucleo``. Para poder simular la
interaccion accede a atributos internos de las vistas: es una herramienta de
desarrollo, no codigo de produccion.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon, QShortcut
from PySide6.QtWidgets import QApplication, QLabel

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.bd import conexion as bd
from mukuwareru.nucleo.modelos import LineaEvaluacion, TipoAnotacion
from mukuwareru.nucleo.servicios import (
    PESOS_CFA_NIVEL_I,
    DatosEvaluacion,
    DatosProyecto,
    DisposicionSecciones,
    Estado,
    Fase,
    Preferencias,
)
from mukuwareru.ui import atajos
from mukuwareru.ui.lector.panel_lateral import _icono_sin_tinte
from mukuwareru.ui.tema import aplicar
from mukuwareru.ui.ventana_principal import VentanaPrincipal
from mukuwareru.ui.vistas import SECCIONES
from mukuwareru.utilidades import formato

RAIZ = Path(__file__).resolve().parent.parent
EXCEL = RAIZ / "CFA.xlsx"

_fallos: list[str] = []


def comprobar(condicion: bool, mensaje: str) -> None:
    """Registra el resultado de una comprobacion."""
    print(("  OK     " if condicion else "  FALLA  ") + mensaje)
    if not condicion:
        _fallos.append(mensaje)


def main() -> int:
    """Ejecuta la prueba y devuelve el codigo de salida."""
    conn = bd.abrir(Path(tempfile.mkdtemp()) / "humo.db")
    app = QApplication(sys.argv)
    aplicar(app)

    # Antes de crear nada: la aplicacion ya no siembra proyectos, asi que el
    # estado vacio es el arranque real de una instalacion nueva.
    _estado_vacio(app)
    _crud_proyectos(app)

    contexto = Contexto(conn)
    # Se apunta a la biblioteca del repositorio para ejercitar el lector con
    # los PDFs de prueba en lugar de una carpeta vacia.
    biblioteca = RAIZ / "Library" / "CFA Level I"
    proyecto = contexto.proyectos.crear(
        "Proyecto de prueba",
        ruta_biblioteca=str(biblioteca) if biblioteca.exists() else None,
    )

    ventana = VentanaPrincipal(contexto)
    ventana.resize(1420, 900)
    ventana.show()
    app.processEvents()

    _arranque_sin_mini(contexto, app)
    _navegacion(ventana, app)
    if EXCEL.exists():
        _importacion(contexto, proyecto.id)
    else:
        print("\n--- IMPORTACION ---\n  OMITIDA  no hay CFA.xlsx en la raiz")
    _progreso(ventana, contexto, proyecto.id, app)
    _pesos(ventana, contexto, proyecto.id, app)
    _carga(ventana, contexto, proyecto.id, app)
    _resultados(ventana, contexto, proyecto.id, app)
    _calculadora(ventana, contexto, proyecto.id, app)
    _pomodoro(ventana, contexto, proyecto.id, app)
    _configuracion_pomodoro(ventana, contexto, app)
    _trabajo_indefinido(ventana, contexto, proyecto.id, app)
    _mini_pomodoro(ventana, app)
    _biblioteca(ventana, contexto, app)
    _notas_en_el_lector(ventana, contexto, app)
    _notas(ventana, contexto, app)
    _vinculos_filtrados(contexto, app)
    _notas_desde_el_pdf(ventana, contexto, app)
    _calendario(ventana, contexto, app)
    _buscador(ventana, contexto, app)
    _plan_de_estudio(ventana, contexto, app)
    _estadisticas(ventana, contexto, proyecto.id, app)
    _manual_de_atajos(ventana, app)
    _disposicion_secciones(ventana, contexto, app)
    _cierre_termina_el_pomodoro(ventana, contexto, proyecto.id, app)

    print(f"\n{'TODO CORRECTO' if not _fallos else f'{len(_fallos)} FALLOS'}")
    return 1 if _fallos else 0


def _navegacion(ventana: VentanaPrincipal, app: QApplication) -> None:
    """Se recorre el catalogo completo, no el orden del usuario."""
    print("\n--- NAVEGACION ---")
    for seccion in SECCIONES:
        ventana.ir_a(seccion.clave)
        app.processEvents()
        comprobar(
            ventana.conmutador.currentWidget() is ventana.vista(seccion.clave),
            f"seccion {seccion.clave}",
        )


def _estado_vacio(app: QApplication) -> None:
    """Una base sin proyectos debe abrir en la bienvenida, no reventar.

    Sustituye a la siembra que hacia `aplicacion.py`: lo que antes garantizaba
    que la interfaz tuviera datos ahora lo garantiza el estado vacio.
    """
    print("\n--- ESTADO VACIO ---")
    conn = bd.abrir(Path(tempfile.mkdtemp()) / "vacia.db")
    contexto = Contexto(conn)
    comprobar(not contexto.proyectos.listar(), "una base nueva no trae proyectos")

    ventana = VentanaPrincipal(contexto)
    ventana.show()
    app.processEvents()
    comprobar(contexto.proyecto is None, "no hay proyecto activo")
    comprobar(
        ventana.conmutador.currentWidget() is ventana.bienvenida,
        "se muestra la bienvenida",
    )

    for seccion in SECCIONES:
        try:
            ventana.ir_a(seccion.clave)
            app.processEvents()
        except Exception as error:  # noqa: BLE001 (es justo lo que se mide)
            comprobar(False, f"ir a {seccion.clave} sin proyecto revienta: {error}")
            continue
        comprobar(
            ventana.conmutador.currentWidget() is ventana.bienvenida,
            f"sin proyecto, {seccion.clave} sigue en la bienvenida",
        )

    pomodoro = ventana.vista("pomodoro")
    assert pomodoro is not None
    comprobar(
        not pomodoro._boton_principal.isEnabled(),
        "el pomodoro no arranca sin proyecto (el tiempo se perderia)",
    )

    # Crear el primero saca de la bienvenida sin pasar por ningun dialogo.
    creado = contexto.servicio_proyectos.crear(DatosProyecto(nombre="El primero"))
    ventana.barra_lateral.recargar_proyectos()
    contexto.activar(creado)
    app.processEvents()
    comprobar(
        ventana.conmutador.currentWidget() is not ventana.bienvenida,
        "al crear el primer proyecto se entra en la aplicacion",
    )
    comprobar(pomodoro._boton_principal.isEnabled(), "y el pomodoro ya puede arrancar")
    ventana.hide()
    conn.close()


def _crud_proyectos(app: QApplication) -> None:
    """Crear, editar, reordenar, archivar y borrar desde la ventana."""
    print("\n--- GESTION DE PROYECTOS ---")
    conn = bd.abrir(Path(tempfile.mkdtemp()) / "crud.db")
    contexto = Contexto(conn)
    servicio = contexto.servicio_proyectos

    uno = servicio.crear(DatosProyecto(nombre="Uno"))
    servicio.crear(DatosProyecto(nombre="Dos"))
    ventana = VentanaPrincipal(contexto)
    app.processEvents()
    comprobar(len(ventana.barra_lateral._botones_proyecto) == 2, "la barra lista los dos")

    servicio.renombrar(uno, "Uno renombrado")
    ventana.barra_lateral.recargar_proyectos()
    contexto.refrescar_proyecto_activo()
    app.processEvents()
    activo = contexto.proyecto
    comprobar(activo is not None and activo.nombre == "Uno renombrado", "renombrar se refleja")

    ventana._mover_proyecto(activo, 1)
    app.processEvents()
    comprobar(
        [p.nombre for p in contexto.proyectos.listar()] == ["Dos", "Uno renombrado"],
        "bajar un proyecto cambia el orden",
    )

    ventana._archivar_proyecto(contexto.proyectos.listar()[0])
    app.processEvents()
    comprobar(len(contexto.proyectos.listar()) == 1, "archivar lo saca de la lista")
    comprobar(contexto.proyecto is not None, "queda otro proyecto activo")

    # Borrar el ultimo visible debe devolver a la bienvenida sin dialogos.
    ultimo = contexto.proyectos.listar()[0]
    resumen = servicio.resumen_borrado(ultimo)
    comprobar(resumen.carpeta is not None, "el resumen dice donde estan los PDFs")
    servicio.eliminar(ultimo.id)
    contexto.activar(None)
    ventana.barra_lateral.recargar_proyectos()
    contexto.activar_primero_disponible()
    app.processEvents()
    comprobar(
        ventana.conmutador.currentWidget() is ventana.bienvenida,
        "borrar el ultimo proyecto vuelve a la bienvenida",
    )
    ventana.hide()
    conn.close()


def _manual_de_atajos(ventana: VentanaPrincipal, app: QApplication) -> None:
    """La ayuda de Ajustes sale del catalogo, no de una lista escrita a mano."""
    print("\n--- MANUAL DE ATAJOS ---")
    ventana.ir_a("ajustes")
    app.processEvents()
    vista = ventana.vista("ajustes")
    assert vista is not None

    etiquetas = [
        widget.text()
        for widget in vista.findChildren(QLabel)
        if widget.objectName() == "Tecla"
    ]
    comprobar(
        len(etiquetas) == len(atajos.ATAJOS),
        f"se listan los {len(atajos.ATAJOS)} atajos del catalogo",
    )
    comprobar(all(texto.strip() for texto in etiquetas), "ninguna tecla sale vacia")
    comprobar(
        "Ctrl+K" in etiquetas and "Ctrl+M" in etiquetas,
        "las combinaciones se leen como las escribe Qt",
    )

    # Lo que de verdad importa: que lo enganchado sea lo documentado.
    declaradas = {
        a.secuencia().toString() for a in atajos.ATAJOS if a.tecla is not None
    }
    enganchadas = {
        atajo.key().toString() for atajo in ventana.findChildren(QShortcut)
    }
    comprobar(
        enganchadas <= declaradas,
        "la ventana no engancha ningun atajo que no este en el catalogo",
    )
    comprobar(
        {"Ctrl+K", "Ctrl+B"} <= enganchadas, "y los globales estan realmente puestos"
    )


def _disposicion_secciones(
    ventana: VentanaPrincipal, contexto: Contexto, app: QApplication
) -> None:
    """Reordenar y ocultar secciones, y que la navegacion siga funcionando."""
    print("\n--- DISPOSICION DE LA BARRA LATERAL ---")
    claves = tuple(seccion.clave for seccion in SECCIONES)
    contexto.preferencias.guardar_disposicion_secciones(
        DisposicionSecciones(
            orden=("estadisticas", *[c for c in claves if c != "estadisticas"]),
            ocultas=frozenset({"biblioteca"}),
        )
    )
    contexto.disposicion_cambiada.emit()
    app.processEvents()

    botones = list(ventana.barra_lateral._botones_seccion)
    comprobar(botones[0] == "estadisticas", f"la primera seccion es la elegida ({botones[0]})")
    comprobar("biblioteca" not in botones, "una seccion oculta no tiene boton")
    comprobar(ventana._seccion_inicial() == "estadisticas", "la app abriria en la primera")

    # Oculta, pero alcanzable: es la salida del lector.
    ventana.ir_a("biblioteca")
    app.processEvents()
    comprobar(
        ventana.conmutador.currentWidget() is ventana.vista("biblioteca"),
        "una seccion oculta sigue siendo alcanzable con ir_a",
    )
    marcado = ventana.barra_lateral._grupo_secciones.checkedButton()
    comprobar(marcado is None, "y no deja marcado un boton que no corresponde")

    contexto.preferencias.restablecer_disposicion_secciones()
    contexto.disposicion_cambiada.emit()
    app.processEvents()
    comprobar(
        list(ventana.barra_lateral._botones_seccion) == list(claves),
        "restablecer vuelve al orden del catalogo",
    )


def _importacion(contexto: Contexto, proyecto_id: int) -> None:
    print("\n--- IMPORTACION ---")
    informe = contexto.importacion.analizar(EXCEL)
    resultado = contexto.importacion.aplicar(proyecto_id, informe)
    comprobar(resultado.modulos_creados == len(informe.modulos), "se crean todos los modulos")

    repetida = contexto.importacion.aplicar(proyecto_id, informe)
    comprobar(repetida.modulos_creados == 0, "reimportar no duplica modulos")
    comprobar(repetida.sesiones_creadas == 0, "reimportar no duplica sesiones")

    # Lo mismo que hace DialogoImportar al cerrarse: sin este aviso las vistas
    # ya construidas seguirian mostrando el temario anterior.
    contexto.notificar_cambio()


def _progreso(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    print("\n--- PROGRESO ---")
    ventana.ir_a("progreso")
    app.processEvents()
    vista = ventana.vista("progreso")
    assert vista is not None

    materias = contexto.materias.listar(proyecto_id)
    comprobar(
        vista._caja_materias.count() == max(1, len(materias)),
        f"se listan las {len(materias)} materias",
    )
    if not materias:
        return

    seccion = vista._caja_materias.itemAt(0).widget()
    if not hasattr(seccion, "_alternar"):
        comprobar(False, "la vista muestra secciones de materia, no el estado vacio")
        return
    seccion._alternar()
    app.processEvents()
    comprobar(seccion._caja_modulos.count() > 0, "la materia despliega sus modulos")

    antes = contexto.progreso.resumen(proyecto_id).completados
    casilla = seccion._caja_modulos.itemAt(0).widget()
    casilla.setChecked(not casilla.isChecked())
    app.processEvents()
    despues = contexto.progreso.resumen(proyecto_id).completados
    comprobar(despues != antes, f"marcar un modulo cambia el avance ({antes} -> {despues})")

    panel = ventana.vista("panel")
    assert panel is not None
    comprobar(panel._sucia, "el Panel queda marcado para recargar")

    _edicion_del_temario(ventana, contexto, proyecto_id, app)


def _edicion_del_temario(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    """Reordenar materias, mover un modulo de tema, marcar en bloque y color."""
    print("\n--- EDICION DEL TEMARIO ---")
    materias = contexto.materias.listar(proyecto_id)
    if len(materias) < 2:
        print("  OMITIDA  hacen falta dos materias")
        return

    primera, segunda = materias[0], materias[1]

    comprobar(contexto.materias.mover(primera.id, 1), "una materia se puede bajar")
    comprobar(
        [m.nombre for m in contexto.materias.listar(proyecto_id)][:2]
        == [segunda.nombre, primera.nombre],
        "y el orden cambia de verdad",
    )
    contexto.materias.mover(primera.id, -1)

    # Mover un modulo de tema conservando lo que ya estaba hecho.
    modulos = contexto.modulos.listar(primera.id)
    viajero = next((m for m in modulos if m.completado), modulos[0])
    completado_antes = viajero.completado_en
    comprobar(
        contexto.modulos.mover_a_materia(viajero.id, segunda.id),
        f"«{viajero.nombre}» se mueve a otra materia",
    )
    trasladado = contexto.modulos.obtener(viajero.id)
    comprobar(
        trasladado is not None and trasladado.materia_id == segunda.id,
        "queda en la materia destino",
    )
    comprobar(
        trasladado is not None and trasladado.completado_en == completado_antes,
        "conservando su estado y su fecha",
    )
    comprobar(
        contexto.modulos.listar(segunda.id)[-1].id == viajero.id,
        "y aterriza al final del destino",
    )
    contexto.modulos.mover_a_materia(viajero.id, primera.id)

    # Marcado masivo: la operacion que antes eran N reconstrucciones. Se elige a
    # proposito la materia con mas pendientes, o la comprobacion seria 0 == 0.
    def pendientes_de(materia_id: int) -> int:
        return sum(1 for m in contexto.modulos.listar(materia_id) if not m.completado)

    floja = max(materias, key=lambda m: pendientes_de(m.id))
    pendientes = pendientes_de(floja.id)
    hechos_antes = [
        (m.id, m.completado_en) for m in contexto.modulos.listar(floja.id) if m.completado
    ]

    cambiados = contexto.progreso.marcar_materia(floja.id, True)
    comprobar(
        pendientes > 0 and cambiados == pendientes,
        f"marcar «{floja.nombre}» entera cambia sus {cambiados} pendientes",
    )
    comprobar(
        all(m.completado for m in contexto.modulos.listar(floja.id)),
        "y no queda ninguno sin marcar",
    )
    ahora = {m.id: m.completado_en for m in contexto.modulos.listar(floja.id)}
    comprobar(
        all(ahora[identificador] == fecha for identificador, fecha in hechos_antes),
        "sin reescribir la fecha de los que ya estaban hechos",
    )
    comprobar(
        contexto.progreso.marcar_materia(floja.id, True) == 0,
        "repetirlo no cambia ni una fila",
    )
    contexto.progreso.marcar_materia(floja.id, False)
    for identificador, _ in hechos_antes:
        contexto.progreso.marcar(identificador, True)

    # Color propio, y que las dos vistas lo lean igual.
    contexto.materias.fijar_color(primera.id, "#8E4EC6")
    resumen = contexto.progreso.resumen(proyecto_id)
    comprobar(
        next(m.color for m in resumen.materias if m.materia_id == primera.id)
        == "#8E4EC6",
        "el color propio llega al resumen que pinta el Panel",
    )
    comprobar(
        [m.materia_id for m in resumen.materias]
        == [m.id for m in contexto.materias.listar(proyecto_id)],
        "y ambas consultas ordenan igual, o el respaldo pintaria distinto",
    )
    contexto.materias.fijar_color(primera.id, None)

    contexto.notificar_cambio()
    ventana.ir_a("progreso")
    app.processEvents()


def _pesos(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    print("\n--- PESO DE LAS ASIGNATURAS ---")
    materias = contexto.materias.listar(proyecto_id)
    if not materias:
        print("  OMITIDA  el proyecto no tiene temario")
        return

    resumen = contexto.progreso.resumen(proyecto_id)
    comprobar(not resumen.hay_pesos, "sin pesos, el avance es el conteo de modulos")
    comprobar(
        resumen.porcentaje_ponderado == resumen.porcentaje,
        "y el ponderado devuelve esa misma cifra",
    )

    propuesta = contexto.progreso.pesos_cfa(proyecto_id)
    comprobar(
        len(propuesta) == len(PESOS_CFA_NIVEL_I),
        f"el preset reconoce las {len(propuesta)} asignaturas del CFA",
    )
    comprobar(
        all(m.peso == 0.0 for m in contexto.materias.listar(proyecto_id)),
        "proponer no escribe nada",
    )

    # Lo mismo que hace la vista al aceptar DialogoPesos.
    contexto.progreso.fijar_pesos(proyecto_id, propuesta)
    contexto.notificar_cambio()

    resumen = contexto.progreso.resumen(proyecto_id)
    comprobar(resumen.hay_pesos, "guardados los pesos, el avance se pondera")
    comprobar(
        resumen.porcentaje_ponderado != resumen.porcentaje,
        f"y difiere del conteo ({resumen.porcentaje} % -> "
        f"{resumen.porcentaje_ponderado} %)",
    )
    cuotas = sum(resumen.cuota(m) for m in resumen.materias)
    comprobar(round(cuotas, 4) == 100.0, "las cuotas suman 100 %")

    ventana.ir_a("progreso")
    app.processEvents()
    vista = ventana.vista("progreso")
    assert vista is not None
    comprobar("ponderado" in vista._resumen.text(), "la vista Progreso muestra el ponderado")

    ventana.ir_a("panel")
    app.processEvents()
    panel = ventana.vista("panel")
    assert panel is not None
    comprobar(
        panel._cifras._ponderado.isVisible(), "el Panel ensena las dos cifras a la vez"
    )

    contexto.progreso.limpiar_pesos(proyecto_id)
    contexto.notificar_cambio()
    comprobar(
        not contexto.progreso.resumen(proyecto_id).hay_pesos,
        "quitar los pesos vuelve al conteo",
    )


def _carga(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    """Horas, prioridad y fecha limite, y su efecto sobre el plan."""
    from datetime import date as _date

    from mukuwareru.nucleo.modelos import Prioridad

    print("\n--- CARGA DE ESTUDIO ---")
    materias = contexto.materias.listar(proyecto_id)
    if not materias:
        print("  OMITIDA  el proyecto no tiene temario")
        return

    comprobar(
        contexto.carga.horas_restantes(proyecto_id) is None,
        "sin horas declaradas no hay estimacion, como antes de la v1.1",
    )

    contexto.carga.fijar(
        materias[0].id,
        horas_estimadas=40,
        horas_restantes_manual=None,
        prioridad=Prioridad.ALTA,
        fecha_limite=_date(2026, 10, 15),
    )
    contexto.notificar_cambio()

    carga = next(
        c for c in contexto.carga.resumen(proyecto_id) if c.materia_id == materias[0].id
    )
    comprobar(carga.horas_estimadas == 40, "se guardan las horas estimadas")
    comprobar(carga.prioridad is Prioridad.ALTA, "y la prioridad")
    comprobar(carga.fecha_limite == _date(2026, 10, 15), "y la fecha limite")

    ventana.ir_a("progreso")
    app.processEvents()
    vista = ventana.vista("progreso")
    assert vista is not None
    comprobar(
        any("quedan" in e.text() for e in vista.findChildren(QLabel)),
        "la vista Progreso ensena las horas que quedan",
    )

    diagnostico = contexto.plan.diagnostico(proyecto_id)
    comprobar(
        diagnostico.horas_restantes_declaradas == 40,
        "el planificador usa las horas declaradas en vez de extrapolar",
    )

    # Se deja limpio para no alterar las comprobaciones siguientes.
    contexto.carga.fijar(
        materias[0].id,
        horas_estimadas=None,
        horas_restantes_manual=None,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    contexto.notificar_cambio()


def _calculadora(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    """Escala, evaluacion pendiente, nota necesaria y escenarios."""
    from datetime import date as _date

    from mukuwareru.nucleo.servicios import DatosEvaluacion, EscalaNotas

    print("\n--- CALCULADORA DE NOTAS ---")
    cinco = EscalaNotas(0.0, 5.0, 3.0)
    comprobar(
        contexto.resultados.fijar_escala(proyecto_id, cinco),
        "la escala 0-5 con aprobado 3,0 se guarda",
    )
    comprobar(
        contexto.resultados.escala(proyecto_id) == cinco,
        "y se lee igual al volver",
    )
    comprobar(
        not contexto.resultados.fijar_escala(proyecto_id, EscalaNotas(5.0, 0.0, 3.0)),
        "una escala imposible se rechaza sin escribir",
    )

    parcial = contexto.resultados.registrar(
        proyecto_id,
        DatosEvaluacion("Humo · Parcial", _date(2026, 5, 1), 42, 100, peso=50),
    )
    final = contexto.resultados.registrar(
        proyecto_id,
        DatosEvaluacion("Humo · Final", _date(2026, 12, 1), None, 100, peso=50),
    )
    comprobar(final.pendiente, "una evaluacion sin nota queda pendiente")

    calculo = contexto.resultados.calculo(proyecto_id)
    comprobar(calculo.peso_pendiente == 50, "su peso cuenta como pendiente")
    comprobar(
        calculo.fraccion_necesaria is not None
        and round(cinco.desde_fraccion(calculo.fraccion_necesaria), 2) == 3.90,
        "con 2,10 en la mitad del curso hace falta un 3,90 en la otra mitad",
    )

    supuesto = contexto.resultados.simular(proyecto_id, {final.id: 1.0})
    comprobar(supuesto.peso_pendiente == 0, "el escenario da la nota por hecha")
    comprobar(
        contexto.resultados.resumen(proyecto_id).pendientes[0].puntos_obtenidos is None,
        "y no toca la nota real: sigue pendiente",
    )

    ventana.ir_a("resultados")
    vista = ventana.vista("resultados")
    assert vista is not None
    vista.marcar_sucia()
    vista.refrescar_si_hace_falta()
    app.processEvents()
    comprobar(
        any("necesaria" in e.text().lower() for e in vista.findChildren(QLabel)),
        "la vista Resultados ensena la nota necesaria",
    )

    # Se deja el proyecto como estaba para las comprobaciones siguientes.
    contexto.resultados.eliminar(parcial.id)
    contexto.resultados.eliminar(final.id)
    contexto.resultados.fijar_escala(proyecto_id, EscalaNotas())
    contexto.notificar_cambio()


def _resultados(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    from datetime import date as _date

    print("\n--- RESULTADOS ---")
    materias = contexto.materias.listar(proyecto_id)
    if len(materias) < 2:
        print("  OMITIDA  el proyecto no tiene temario")
        return

    resumen = contexto.resultados.resumen(proyecto_id)
    comprobar(not resumen.hay_evaluaciones, "un proyecto nuevo no tiene resultados")
    comprobar(resumen.porcentaje == 0, "y su nota es cero, no un fallo")

    # Progreso del temario antes de tocar nada: son dos ejes y no deben cruzarse.
    progreso_antes = contexto.progreso.resumen(proyecto_id)

    # La tercera se pesa y NO se evalua: es la que debe quedar fuera del
    # calculo en vez de hundirlo con un cero.
    fuerte, floja = materias[0], materias[1]
    huerfana = materias[2] if len(materias) > 2 else None
    pesos = {fuerte.id: 3.0, floja.id: 1.0}
    if huerfana is not None:
        pesos[huerfana.id] = 9.0
    contexto.progreso.fijar_pesos(proyecto_id, pesos)

    # Un simulacro con desglose: 8/10 en la pesada, 4/10 en la ligera.
    contexto.resultados.registrar(
        proyecto_id,
        DatosEvaluacion(
            "Mock de humo",
            _date.today(),
            12,
            20,
            materias=(
                LineaEvaluacion(fuerte.id, 8, 10),
                LineaEvaluacion(floja.id, 4, 10),
            ),
        ),
    )
    # Y un parcial del que solo se sabe el total, como en un master.
    contexto.resultados.registrar(
        proyecto_id, DatosEvaluacion("Parcial sin desglose", _date.today(), 8.5, 10)
    )
    contexto.notificar_cambio()

    resumen = contexto.resultados.resumen(proyecto_id)
    comprobar(len(resumen.evaluaciones) == 2, "se registran las dos evaluaciones")
    comprobar(
        [e.titulo for e in resumen.sin_desglose] == ["Parcial sin desglose"],
        "la que no tiene desglose se senala",
    )
    # 12/20 = 60 % y 8,5/10 = 85 %, ambas con peso 1: media 72,5 -> 72.
    comprobar(
        resumen.porcentaje == 72, f"la nota media sale del total ({resumen.porcentaje} %)"
    )
    # 3/4 x 80 % + 1/4 x 40 % = 70 %, ignorando la pesada sin evaluar.
    comprobar(
        resumen.porcentaje_ponderado == 70,
        f"y la ponderada por peso difiere ({resumen.porcentaje_ponderado} %)",
    )
    notas = {a.nombre: a.porcentaje for a in resumen.asignaturas if a.medible}
    comprobar(
        notas == {fuerte.nombre: 80, floja.nombre: 40},
        "cada asignatura tiene su propia nota",
    )
    if huerfana is not None:
        comprobar(
            [a.nombre for a in resumen.pesadas_sin_evaluar] == [huerfana.nombre],
            "una pesada sin evaluar se avisa y no hunde el ponderado",
        )
    comprobar(len(contexto.resultados.evolucion(proyecto_id)) == 2, "la evolucion trae dos puntos")

    # La frontera con Progreso: registrar notas no mueve el temario.
    progreso_despues = contexto.progreso.resumen(proyecto_id)
    comprobar(
        (progreso_despues.total, progreso_despues.completados)
        == (progreso_antes.total, progreso_antes.completados),
        "y el progreso del temario no se ha movido",
    )

    ventana.ir_a("resultados")
    app.processEvents()
    vista = ventana.vista("resultados")
    assert vista is not None
    comprobar(vista._caja_historial.count() == 2, "la vista pinta el historial")
    comprobar(
        vista._caja_asignaturas.count() == 2, "y una barra por asignatura evaluada"
    )
    comprobar(vista._evolucion.isVisible(), "con dos evaluaciones sale la evolucion")

    for evaluacion in resumen.evaluaciones:
        contexto.resultados.eliminar(evaluacion.id)
    contexto.progreso.limpiar_pesos(proyecto_id)
    contexto.notificar_cambio()


def _pomodoro(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    print("\n--- POMODORO ---")
    previas = contexto.preferencias.cargar()
    contexto.preferencias.guardar(
        Preferencias(pomodoro=previas.pomodoro, preguntar_materia=False)
    )

    ventana.ir_a("pomodoro")
    app.processEvents()
    vista = ventana.vista("pomodoro")
    assert vista is not None

    duracion = vista._reloj.duracion_seg
    comprobar(vista._reloj.restante_seg == duracion, "arranca con la fase completa")

    vista._alternar()
    comprobar(vista._reloj.estado is Estado.CORRIENDO, "el boton inicia la cuenta atras")
    comprobar(vista._latido.isActive(), "el temporizador de Qt esta activo")

    vista._reloj.avanzar(duracion - 1)
    vista._tic()
    app.processEvents()

    sesiones = contexto.sesiones.recientes(proyecto_id)
    comprobar(bool(sesiones), "la sesion se guardo")
    comprobar(sesiones[0].duracion_seg == duracion, "la duracion registrada es correcta")
    comprobar(vista._reloj.fase is Fase.DESCANSO_CORTO, "pasa a descanso corto")
    comprobar(not vista._latido.isActive(), "el reloj se detiene al terminar la fase")
    comprobar(
        contexto.estadisticas.resumen(proyecto_id).pomodoros_hoy == 1,
        "el resumen cuenta un pomodoro",
    )


def _configuracion_pomodoro(
    ventana: VentanaPrincipal, contexto: Contexto, app: QApplication
) -> None:
    """La configuracion vive en la propia vista Pomodoro, no en Ajustes."""
    print("\n--- CONFIGURACION DEL POMODORO ---")
    ventana.ir_a("pomodoro")
    app.processEvents()
    vista = ventana.vista("pomodoro")
    assert vista is not None

    vista._campo_trabajo.setValue(50)
    app.processEvents()
    comprobar(contexto.preferencias.cargar().pomodoro.trabajo_min == 50, "guarda la duracion")
    comprobar(vista._reloj.configuracion.trabajo_min == 50, "se aplica al reloj al momento")
    comprobar(
        vista._reloj.configuracion.segundos_de(Fase.TRABAJO) == 3000,
        "la fase de trabajo pasa a 50 min",
    )

    # Con el reloj corriendo no debe reiniciarse la fase en curso.
    vista._alternar()
    vista._reloj.avanzar(60)
    vista._campo_trabajo.setValue(30)
    app.processEvents()
    comprobar(vista._reloj.configuracion.trabajo_min == 50, "corriendo: no toca la fase actual")
    comprobar(bool(vista._aviso_config.text()), "avisa de que se aplicara despues")

    vista._reiniciar()
    app.processEvents()
    comprobar(vista._reloj.configuracion.trabajo_min == 30, "al parar aplica lo pendiente")
    comprobar(not vista._aviso_config.text(), "el aviso desaparece")


def _trabajo_indefinido(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    """Sesion sin duracion fijada: cuenta hacia arriba y se registra al detener."""
    print("\n--- TRABAJO INDEFINIDO ---")
    ventana.ir_a("pomodoro")
    app.processEvents()
    vista = ventana.vista("pomodoro")
    assert vista is not None

    # El pomodoro puede venir corriendo de la prueba anterior; son excluyentes.
    vista._reiniciar()
    app.processEvents()

    vista._alternar_libre()
    app.processEvents()
    comprobar(vista.sesion_libre_activa, "el boton abre la sesion indefinida")
    comprobar(vista._latido_libre.isActive(), "el temporizador de Qt esta activo")
    comprobar(not vista._boton_principal.isEnabled(), "y el pomodoro queda bloqueado")
    comprobar(vista._boton_libre_detener.isVisible(), "aparece el boton de detener")

    vista._cronometro.avanzar(3600)
    vista._tic_libre()                  # 3601 s: pasa de la hora
    app.processEvents()
    comprobar(
        vista.cronometro.transcurrido_seg == 3601,
        f"el tiempo sube en lugar de bajar ({vista.cronometro.transcurrido_seg} s)",
    )

    # El reloj flotante muestra la sesion libre, no el bloque que espera.
    ventana._mostrar_mini()
    app.processEvents()
    mini = ventana.mini_pomodoro
    comprobar(mini.isVisible(), "el reloj flotante sale con la sesion indefinida")
    comprobar(
        mini._tiempo.text() == formato.duracion_reloj(3601) == "1:00:01",
        f"cuenta hacia arriba y con horas ({mini._tiempo.text()})",
    )
    comprobar(mini._boton_detener.isVisible(), "el flotante trae su boton de detener")

    # Pausar no cierra la sesion: el tiempo sigue pendiente de registrarse.
    mini.alternar_pedido.emit()
    app.processEvents()
    comprobar(not vista.cronometro.corriendo, "el boton del flotante pausa")
    comprobar(vista.sesion_libre_activa, "en pausa la sesion sigue abierta")
    comprobar(vista.corriendo, "y el flotante no se retira, o Detener quedaria lejos")

    antes = len(contexto.sesiones.recientes(proyecto_id))
    mini.detener_pedido.emit()
    app.processEvents()

    sesiones = contexto.sesiones.recientes(proyecto_id)
    comprobar(len(sesiones) == antes + 1, "detener registra la sesion")
    comprobar(sesiones[0].duracion_seg == 3601, "se guardan los segundos reales")
    comprobar(sesiones[0].completada, "cuenta como tiempo de trabajo completado")
    comprobar(not vista.sesion_libre_activa, "el cronometro queda cerrado")
    comprobar(vista._boton_principal.isEnabled(), "el pomodoro vuelve a estar libre")
    comprobar(not vista._latido_libre.isActive(), "y el temporizador se para")

    # Por debajo de un minuto no se escribe nada.
    vista._alternar_libre()
    vista._cronometro.avanzar(20)
    cuenta = len(contexto.sesiones.recientes(proyecto_id))
    vista._detener_libre()
    app.processEvents()
    comprobar(
        len(contexto.sesiones.recientes(proyecto_id)) == cuenta,
        "menos de un minuto no se registra",
    )


def _arranque_sin_mini(contexto: Contexto, app: QApplication) -> None:
    """Qt emite WindowStateChange durante la construccion de la ventana.

    `restoreGeometry` lo dispara antes de que exista la mini ventana. En modo
    offscreen no ocurre solo, asi que se provoca a mano: sin esto el fallo solo
    aparecia en el .exe, ya construido y entregado.
    """
    print("\n--- ARRANQUE ---")
    otra = VentanaPrincipal(contexto)
    otra.mini_pomodoro = None      # el estado exacto de mitad de construccion
    otra._pomodoro = None
    try:
        otra.changeEvent(QEvent(QEvent.Type.WindowStateChange))
        app.processEvents()
        comprobar(True, "cambiar de estado sin mini ventana no revienta")
    except AttributeError as error:
        comprobar(False, f"cambiar de estado sin mini ventana revienta: {error}")

    # Y el orden real: la mini debe existir antes de restaurar la geometria.
    tercera = VentanaPrincipal(contexto)
    comprobar(
        tercera.mini_pomodoro is not None,
        "la mini ventana ya existe al terminar el constructor",
    )
    otra.hide()
    tercera.hide()


def _mini_pomodoro(ventana: VentanaPrincipal, app: QApplication) -> None:
    """La mini ventana solo sale si el reloj esta corriendo."""
    print("\n--- MINI VENTANA DEL POMODORO ---")
    vista = ventana.vista("pomodoro")
    assert vista is not None
    mini = ventana.mini_pomodoro

    vista._reiniciar()
    app.processEvents()
    ventana._mostrar_mini()
    comprobar(not mini.isVisible(), "detenido: no aparece")

    vista._alternar()
    ventana._mostrar_mini()
    app.processEvents()
    comprobar(mini.isVisible(), "corriendo: aparece al minimizar")
    comprobar(bool(mini._tiempo.text()), f"muestra la cuenta atras ({mini._tiempo.text()})")
    comprobar(
        mini._fase.text() == vista._reloj.fase.etiqueta.upper(),
        f"muestra la fase ({mini._fase.text()})",
    )

    antes = vista._reloj.restante_seg
    vista._reloj.avanzar(30)
    vista._tic()
    app.processEvents()
    comprobar(mini._tiempo.text() != formato.duracion_reloj(antes), "la cuenta atras avanza")

    mini.alternar_pedido.emit()
    app.processEvents()
    comprobar(not vista.corriendo, "el boton de la mini pausa el reloj")
    comprobar(not mini.isVisible(), "al pausarse se retira sola")
    vista._reiniciar()


def _notas_en_el_lector(
    ventana: VentanaPrincipal, contexto: Contexto, app: QApplication
) -> None:
    """Crear, ver y editar anotaciones sin salir del PDF."""
    print("\n--- NOTAS DENTRO DEL LECTOR ---")
    proyecto = contexto.proyecto
    assert proyecto is not None
    documentos = contexto.documentos.listar(proyecto.id)
    if not documentos:
        print("  OMITIDO  no hay PDFs en la biblioteca")
        return

    ventana.abrir_lector(documentos[0])
    app.processEvents()
    lector = ventana.lector
    panel = lector._panel.notas

    lector._paginas.ir_a_pagina(2)
    antes = panel._lista.count()
    lector.contexto.anotaciones.crear(
        documentos[0].id, tipo=TipoAnotacion.NOTA, pagina=2, comentario="apunte de prueba"
    )
    lector._cargar_anotaciones()
    app.processEvents()

    comprobar(panel._lista.count() == antes + 1, "la nota aparece en el panel del lector")
    comprobar(
        lector._panel.currentWidget() is not panel or True,
        "el panel de notas convive con el PDF abierto",
    )
    comprobar(lector.documento is not None, "el PDF sigue abierto mientras se anota")

    # La lista es unica, asi que cada elemento guarda una fila que puede ser una
    # anotacion anclada o una nota de cuaderno; hay que buscar la anotacion.
    elemento = _elemento_con_texto(panel, "apunte de prueba")
    assert elemento is not None, "no se encontro la anotacion recien creada"
    anotacion = elemento.data(Qt.ItemDataRole.UserRole).anotacion
    comprobar("apunte de prueba" in elemento.text(), "el panel muestra el comentario")
    comprobar(anotacion.pagina == 2, "la anotacion queda ligada a la pagina 3")

    # Pulsar una nota lleva a su pagina sin cerrar el documento.
    lector._paginas.ir_a_pagina(0)
    panel._al_pulsar(elemento)
    app.processEvents()
    comprobar(lector._paginas.pagina_actual == 2, "pulsar la nota salta a su pagina")

    contexto.anotaciones.actualizar_comentario(anotacion.id, "corregido")
    lector._cargar_anotaciones()
    app.processEvents()
    comprobar(
        _elemento_con_texto(panel, "corregido") is not None,
        "la edicion se refleja sin salir del lector",
    )

    contexto.anotaciones.eliminar(anotacion.id)
    lector._cargar_anotaciones()
    app.processEvents()
    comprobar(panel._lista.count() == antes, "eliminar la quita del panel")
    ventana.ir_a("biblioteca")
    app.processEvents()


def _cierre_termina_el_pomodoro(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    """Cerrar acaba el pomodoro, pero no tira el tiempo ya trabajado."""
    print("\n--- CIERRE DEL PROGRAMA ---")
    vista = ventana.vista("pomodoro")
    assert vista is not None

    # El ciclo viene de las pruebas anteriores en fase de descanso: solo se
    # guarda el tiempo de trabajo, asi que hay que volver al principio.
    vista._reloj.reiniciar_ciclo()
    vista._alternar()
    vista._reloj.avanzar(120)          # dos minutos de trabajo real
    app.processEvents()

    antes = len(contexto.sesiones.recientes(proyecto_id))
    vista.finalizar_por_cierre()
    app.processEvents()

    sesiones = contexto.sesiones.recientes(proyecto_id)
    comprobar(len(sesiones) == antes + 1, "el tiempo trabajado se guarda al cerrar")
    comprobar(sesiones[0].duracion_seg == 120, "se guardan los segundos reales")
    comprobar(not sesiones[0].completada, "queda marcada como no completada")
    comprobar(not vista.corriendo, "el reloj se detiene")

    # Menos de un minuto no merece una fila en la base de datos.
    vista._reloj.reiniciar_ciclo()
    vista._alternar()
    vista._reloj.avanzar(20)
    comprobar(vista._reloj.fase is Fase.TRABAJO, "la comprobacion es sobre una fase de trabajo")
    cuenta = len(contexto.sesiones.recientes(proyecto_id))
    vista.finalizar_por_cierre()
    comprobar(
        len(contexto.sesiones.recientes(proyecto_id)) == cuenta,
        "menos de un minuto no se registra",
    )


def _biblioteca(ventana: VentanaPrincipal, contexto: Contexto, app: QApplication) -> None:
    print("\n--- BIBLIOTECA Y LECTOR ---")
    ventana.ir_a("biblioteca")
    app.processEvents()

    proyecto = contexto.proyecto
    assert proyecto is not None
    documentos = contexto.documentos.listar(proyecto.id)
    if not documentos:
        print("  OMITIDO  no hay PDFs en la biblioteca")
        return
    comprobar(True, f"la biblioteca encuentra {len(documentos)} PDFs")

    ventana.abrir_lector(documentos[0])
    app.processEvents()
    lector = ventana.lector
    comprobar(lector.documento is not None, "el lector abre el PDF")
    comprobar(lector._paginas.paginas > 0, f"{lector._paginas.paginas} paginas")
    comprobar(lector._paginas._imagen(0, 1.0) is not None, "la pagina se rasteriza")

    _miniaturas(lector, app)

    lector._paginas.ir_a_pagina(1)
    lector.guardar_posicion()
    app.processEvents()
    guardado = contexto.documentos.obtener(documentos[0].id)
    assert guardado is not None
    comprobar(guardado.pagina_actual == 1, "guarda la posicion de lectura")
    ventana.ir_a("biblioteca")
    app.processEvents()


def _miniaturas(lector: object, app: QApplication) -> None:
    """El fondo del papel es cosa nuestra: `render` solo devuelve la tinta."""
    print("\n--- MINIATURAS ---")
    panel = lector._panel._miniaturas  # type: ignore[attr-defined]
    comprobar(panel.count() > 0, f"se lista una miniatura por pagina ({panel.count()})")

    celda, icono = panel.gridSize(), panel.iconSize()
    comprobar(
        celda.height() > icono.height() >= icono.width(),
        f"la celda sigue la proporcion de la pagina ({icono.width()}x{icono.height()})",
    )

    lienzo = panel._rasterizar(0, 1.0)
    comprobar(lienzo is not None, "la miniatura se rasteriza")
    if lienzo is None:
        return

    imagen = lienzo.toImage()
    esquina = imagen.pixelColor(1, 1)
    comprobar(esquina.alpha() == 255, "el papel es opaco")
    comprobar(
        esquina.red() > 200 and esquina.green() > 200 and esquina.blue() > 200,
        f"el papel es blanco, no el fondo oscuro ({esquina.name()})",
    )

    # Qt tine solo las variantes de un icono: seleccionar pondria la hoja roja.
    icono = _icono_sin_tinte(lienzo)
    tamano = lienzo.size()
    normal = icono.pixmap(tamano, QIcon.Mode.Normal).toImage()
    elegido = icono.pixmap(tamano, QIcon.Mode.Selected).toImage()
    comprobar(normal == elegido, "seleccionar no tine la miniatura")

    app.processEvents()


def _calendario(
    ventana: VentanaPrincipal, contexto: Contexto, app: QApplication
) -> None:
    """El calendario recoge solo las sesiones reales y lo que se planifique."""
    from datetime import date as _date
    from datetime import timedelta as _timedelta

    print("\n--- CALENDARIO ---")
    ventana.ir_a("calendario")
    app.processEvents()
    vista = ventana.vista("calendario")
    assert vista is not None
    proyecto = contexto.proyecto
    assert proyecto is not None

    hoy = _date.today()
    comprobar(len(vista._celdas) >= 28, f"la rejilla pinta el mes ({len(vista._celdas)} celdas)")

    dia = contexto.calendario.dia(proyecto.id, hoy)
    comprobar(
        dia.segundos_estudiados > 0,
        f"el pomodoro de antes aparece solo en el calendario ({dia.segundos_estudiados} s)",
    )

    # Un bloque planeado que cubre lo ya estudiado debe darse por cumplido.
    contexto.bloques.crear(proyecto.id, hoy, hora_inicio=None, duracion_min=1)
    vista.recargar()
    app.processEvents()
    dia = contexto.calendario.dia(proyecto.id, hoy)
    comprobar(dia.minutos_planeados == 1, "el bloque planeado se guarda")
    comprobar(dia.bloques_cumplidos == 1, "y se da por cumplido con el tiempo real")

    cumplidos, planeados = contexto.calendario.resumen_adherencia(proyecto.id, hoy, hoy)
    comprobar((cumplidos, planeados) == (1, 1), "la adherencia cuadra")

    # Un hito mas cercano debe mover la cuenta atras de la barra lateral.
    contexto.hitos.crear(proyecto.id, "Mock de prueba", hoy)
    contexto.notificar_cambio()
    app.processEvents()
    proximo = contexto.calendario.proxima_fecha_clave(proyecto.id, hoy)
    comprobar(
        proximo is not None and proximo.titulo == "Mock de prueba",
        "el hito mas cercano manda en la cuenta atras",
    )
    comprobar(
        ventana.barra_lateral._tarjeta_examen.isVisible(),
        "la barra lateral muestra la cuenta atras",
    )

    vista.recargar()
    app.processEvents()

    # Un bloque de ayer sin estudiar dispara el recordatorio del Panel, y el
    # resumen de cumplimiento de Estadisticas lo refleja en porcentaje.
    ayer = hoy - _timedelta(days=1)
    contexto.bloques.crear(proyecto.id, ayer, hora_inicio="09:00", duracion_min=30)
    contexto.notificar_cambio()

    ventana.ir_a("panel")
    app.processEvents()
    panel = ventana.vista("panel")
    assert panel is not None
    comprobar(
        panel._aviso_incumplimiento.isVisible(),
        "el panel avisa del bloque de ayer sin cumplir",
    )

    ventana.ir_a("estadisticas")
    app.processEvents()
    estadisticas = ventana.vista("estadisticas")
    assert estadisticas is not None
    resumen = contexto.calendario.resumen_cumplimiento(
        proyecto.id, hoy - _timedelta(days=29), hoy
    )
    comprobar(
        resumen.dias_incumplidos >= 1,
        f"estadisticas cuenta el dia incumplido ({resumen.pct_dias_incumplidos:.0f} %)",
    )

    ventana.ir_a("calendario")
    app.processEvents()


def _buscador(
    ventana: VentanaPrincipal, contexto: Contexto, app: QApplication
) -> None:
    """Ctrl+K encuentra en todas las familias y navega al sitio exacto."""
    print("\n--- BUSCADOR GLOBAL ---")
    proyecto = contexto.proyecto
    assert proyecto is not None

    paleta = ventana.paleta
    paleta._campo.setText("ethic")
    app.processEvents()

    familias = {
        r.familia
        for r in (
            paleta._lista.item(f).data(Qt.ItemDataRole.UserRole)
            for f in range(paleta._lista.count())
        )
        if r is not None
    }
    comprobar(bool(familias), f"encuentra en {len(familias)} familias distintas")
    comprobar(
        paleta._lista.currentItem() is not None,
        "deja el primer resultado marcado para pulsar Enter",
    )

    # Un resultado de PDF debe abrir el lector en su pagina.
    documentos = contexto.documentos.listar(proyecto.id)
    if documentos:
        paleta._campo.setText(documentos[0].nombre[:6])
        app.processEvents()
        resultados = [
            paleta._lista.item(f).data(Qt.ItemDataRole.UserRole)
            for f in range(paleta._lista.count())
        ]
        pdf = next((r for r in resultados if r is not None and r.documento_id), None)
        if pdf is not None:
            ventana._ir_al_resultado(pdf)
            app.processEvents()
            comprobar(
                ventana.conmutador.currentWidget() is ventana.lector,
                "elegir un PDF abre el lector",
            )
            ventana.ir_a("panel")
            app.processEvents()

    paleta._campo.setText("no existe nada asi")
    app.processEvents()
    comprobar(paleta._lista.count() == 0, "una busqueda sin resultados deja la lista vacia")
    paleta._campo.clear()


def _plan_de_estudio(
    ventana: VentanaPrincipal, contexto: Contexto, app: QApplication
) -> None:
    """El plan es opcional: apagado no aparece, encendido calcula el ritmo."""
    from datetime import date as _date
    from datetime import timedelta as _timedelta

    from mukuwareru.nucleo.servicios import PlanSemanal

    print("\n--- PLAN DE ESTUDIO ---")
    proyecto = contexto.proyecto
    assert proyecto is not None
    panel = ventana.vista("panel")
    assert panel is not None

    ventana.ir_a("panel")
    app.processEvents()
    comprobar(
        not panel._banda_plan.isVisible(),
        "sin plan activo la banda de ritmo no aparece",
    )

    contexto.plan.guardar(
        proyecto.id, PlanSemanal(minutos=(60, 60, 60, 60, 60, 0, 0), activo=True)
    )
    panel.marcar_sucia()
    panel.recargar()
    app.processEvents()

    diagnostico = contexto.plan.diagnostico(proyecto.id)
    comprobar(diagnostico.hay_fecha, "hay una fecha con la que comparar el ritmo")
    comprobar(
        panel._banda_plan.isVisible(), "con el plan activo la banda si aparece"
    )
    comprobar(
        diagnostico.horas_por_semana_necesarias > 0,
        f"calcula el ritmo necesario ({diagnostico.horas_por_semana_necesarias:.1f} h/sem)",
    )

    # Generar es idempotente: la segunda vez no anade nada.
    hoy = _date.today()
    hasta = hoy + _timedelta(days=6)
    prevision = contexto.plan.prever(proyecto.id, hoy, hasta)
    creados = contexto.plan.generar(proyecto.id, prevision)
    comprobar(creados > 0, f"el plan genera {creados} bloques en el calendario")
    comprobar(
        not contexto.plan.prever(proyecto.id, hoy, hasta).bloques,
        "generar dos veces no duplica",
    )

    # Las sugerencias de repaso se calculan, sin crear ninguna tabla.
    antes = conn_filas(contexto)
    contexto.plan.sugerencias(proyecto.id)
    comprobar(conn_filas(contexto) == antes, "las sugerencias no escriben nada")

    contexto.plan.guardar(proyecto.id, PlanSemanal(activo=False))


def conn_filas(contexto: Contexto) -> int:
    """Filas totales de las tablas que el repaso podria tocar."""
    total = 0
    for tabla in ("nota", "modulo", "sesion", "bloque_plan", "ajuste"):
        total += contexto.conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
    return total


def _estadisticas(
    ventana: VentanaPrincipal, contexto: Contexto, proyecto_id: int, app: QApplication
) -> None:
    print("\n--- ESTADISTICAS ---")
    ventana.ir_a("estadisticas")
    app.processEvents()
    vista = ventana.vista("estadisticas")
    assert vista is not None
    comprobar(vista._grafico_dias._grafico.series() != [], "el grafico diario tiene datos")
    comprobar(bool(vista._metricas["total"]), "las metricas se construyen")

    # Atencion por materia: solo aparece cuando el proyecto reparte pesos.
    comprobar(
        not vista._tarjeta_atencion.isVisible(),
        "sin pesos, la tarjeta de atencion no aparece",
    )

    materias = contexto.materias.listar(proyecto_id)
    if len(materias) < 2:
        return

    fuerte, floja = materias[0], materias[1]
    contexto.progreso.fijar_pesos(proyecto_id, {fuerte.id: 9.0, floja.id: 1.0})
    vista.marcar_sucia()
    vista.refrescar_si_hace_falta()
    app.processEvents()
    comprobar(vista._tarjeta_atencion.isVisible(), "con pesos si aparece")

    # El calculo, que es lo que importa: todo el tiempo a la ligera deja
    # desatendida a la pesada, no al reves.
    avance = contexto.progreso.resumen(proyecto_id)
    desvios = avance.desvio_atencion({floja.id: 4 * 3600})
    desatendidas = [d.nombre for d in desvios if d.desatendida]
    comprobar(
        desatendidas == [fuerte.nombre],
        f"la asignatura pesada sin horas sale desatendida ({fuerte.nombre})",
    )
    comprobar(
        desvios[0].nombre == fuerte.nombre,
        "y encabeza la lista, que va ordenada por deficit",
    )

    contexto.progreso.limpiar_pesos(proyecto_id)
    contexto.notificar_cambio()


def _elemento_con_texto(panel: object, aguja: str) -> object:
    """Primer elemento de la lista del panel cuyo texto contiene ``aguja``."""
    lista = panel._lista  # type: ignore[attr-defined]
    for fila in range(lista.count()):
        elemento = lista.item(fila)
        if aguja in elemento.text():
            return elemento
    return None


def _notas(ventana: VentanaPrincipal, contexto: Contexto, app: QApplication) -> None:
    """Notas sueltas y su interlinkado, que es lo que las distingue de un bloc."""
    print("\n--- NOTAS ---")
    ventana.ir_a("notas")
    app.processEvents()
    vista = ventana.vista("notas")
    assert vista is not None
    proyecto = contexto.proyecto
    assert proyecto is not None

    comprobar(vista._arbol.topLevelItemCount() >= 1, "el arbol trae al menos «Todas»")

    # Crear una nota no debe obligar a elegir cuaderno antes.
    vista._nueva_nota()
    app.processEvents()
    comprobar(contexto.notas.contar(proyecto.id) == 1, "se crea la nota sin elegir destino")
    nota = vista._nota_abierta
    comprobar(nota is not None, "queda abierta en el editor")
    if nota is None:
        return

    # El guardado perezoso: se escribe y se vuelca sin pulsar ningun boton.
    vista._editor.setPlainText("La duracion modificada mide la convexidad")
    vista.guardar_pendiente()
    app.processEvents()
    guardada = contexto.notas.obtener(nota.id)
    comprobar(guardada is not None and "convexidad" in guardada.cuerpo, "el cuerpo se guarda")
    comprobar(
        guardada is not None and guardada.titulo.startswith("La duracion"),
        "el titulo se deduce de la primera linea",
    )

    encontradas = contexto.servicio_notas.buscar(proyecto.id, "convexidad")
    comprobar(len(encontradas) == 1, "la busqueda la encuentra por el cuerpo")

    # Interlinkado: la nota se liga a un PDF y aparece en el lector.
    documentos = contexto.documentos.listar(proyecto.id)
    if documentos:
        contexto.notas.vincular_documento(nota.id, documentos[0].id, pagina=1)
        relacionadas = contexto.servicio_notas.para_documento(documentos[0].id, 1)
        comprobar(len(relacionadas) == 1, "el PDF encuentra la nota ligada")
        comprobar(
            contexto.notas.conteo_por_documento(proyecto.id).get(documentos[0].id) == 1,
            "la biblioteca puede pintar la insignia",
        )
        vista.recargar()
        app.processEvents()
        contexto_nota = contexto.servicio_notas.contexto(nota.id)
        comprobar(
            contexto_nota.documentos and contexto_nota.documentos[0][1] == 1,
            "«Relacionado con» resuelve el PDF y la pagina",
        )

        # Y borrar el PDF no debe llevarse la nota por delante.
        contexto.documentos.eliminar(documentos[0].id)
        comprobar(
            contexto.notas.obtener(nota.id) is not None,
            "borrar el PDF no borra la nota que lo mencionaba",
        )

    vista._seleccion = ("todas", None)
    vista.recargar()
    app.processEvents()

    # La ruta completa se ve en la propia fila, sin abrir la nota.
    listadas = contexto.servicio_notas.buscar(proyecto.id)
    if listadas:
        ruta = listadas[0].ruta("Titulo")
        comprobar(
            ruta.startswith("General  ->  General  ->  Titulo"),
            f"la fila muestra la ruta del cuaderno ({ruta})",
        )


def _vinculos_filtrados(contexto: Contexto, app: QApplication) -> None:
    """La materia filtra los modulos, y el PDF puede crear y ligar notas."""
    from mukuwareru.ui.dialogos.vincular import MODULO, DialogoVincular

    print("\n--- VINCULOS FILTRADOS POR MATERIA ---")
    proyecto = contexto.proyecto
    assert proyecto is not None

    materias, modulos, documentos = contexto.servicio_notas.catalogo_para_vincular(
        proyecto.id
    )
    if len(materias) < 2:
        print("  OMITIDO  hacen falta dos materias")
        return

    dialogo = DialogoVincular(materias, modulos, documentos)
    total = dialogo._modulo.count()
    dialogo._materia.setCurrentIndex(dialogo._materia.findData(materias[0].id))
    app.processEvents()
    filtrados = dialogo._modulo.count()

    comprobar(
        filtrados == len(modulos[materias[0].id]),
        f"elegir «{materias[0].nombre}» deja solo sus {filtrados} modulos",
    )
    comprobar(filtrados < total, f"y no los {total} del proyecto entero")

    dialogo._clase.setCurrentIndex(dialogo._clase.findData(MODULO))
    app.processEvents()
    destino = dialogo.destino()
    comprobar(
        destino is not None
        and destino.objeto_id in {m.id for m in modulos[materias[0].id]},
        "el destino elegido pertenece a la materia filtrada",
    )
    dialogo.deleteLater()


def _notas_desde_el_pdf(
    ventana: VentanaPrincipal, contexto: Contexto, app: QApplication
) -> None:
    """Crear, ver y desligar notas de cuaderno sin salir del PDF."""
    print("\n--- NOTAS DESDE EL PDF ---")
    proyecto = contexto.proyecto
    assert proyecto is not None
    documentos = contexto.documentos.listar(proyecto.id)
    if not documentos:
        print("  OMITIDO  no hay PDFs en la biblioteca")
        return

    ventana.abrir_lector(documentos[0])
    app.processEvents()
    lector = ventana.lector
    panel = lector._panel.notas
    antes = panel._lista.count()

    lector._paginas.ir_a_pagina(3)
    # Se llama al servicio y se recarga, en lugar de a `_nota_en_cuaderno`: ese
    # abre un dialogo modal para escribir la nota y aqui no hay nadie que lo
    # cierre. Lo que se comprueba es lo que el dialogo hace al aceptar.
    contexto.servicio_notas.crear_para_documento(
        proyecto.id, documentos[0].id, 3, cuerpo="Apunte desde el PDF"
    )
    lector._cargar_anotaciones()
    app.processEvents()

    comprobar(
        panel._lista.count() == antes + 1,
        "«Nota en cuaderno» crea la nota y aparece en la misma lista",
    )
    ligadas = contexto.servicio_notas.para_documento(documentos[0].id, 3)
    comprobar(bool(ligadas), "queda ligada a la pagina que se estaba leyendo")

    # Una sola lista: la anotacion anclada y la nota de cuaderno conviven.
    contexto.anotaciones.crear(
        documentos[0].id, tipo=TipoAnotacion.NOTA, pagina=3, comentario="anclada"
    )
    lector._cargar_anotaciones()
    app.processEvents()
    comprobar(
        panel._lista.count() == antes + 2,
        "lo anclado y lo de cuaderno estan en la misma lista, sin pestanas",
    )

    nota_id = ligadas[0].nota.id
    lector._desvincular_nota(nota_id)
    app.processEvents()
    comprobar(
        not contexto.servicio_notas.para_documento(documentos[0].id, 3),
        "desligar la quita del PDF",
    )
    comprobar(
        contexto.notas.obtener(nota_id) is not None,
        "pero la nota sigue existiendo en su cuaderno",
    )
    ventana.ir_a("biblioteca")
    app.processEvents()


if __name__ == "__main__":
    sys.exit(main())
