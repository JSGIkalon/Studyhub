"""Recorrido de bloques: generacion, edicion y cola infinita.

El recorrido es la forma del ciclo, que antes estaba cableada en el reloj. Estas
pruebas cubren lo que el usuario puede hacerle desde el timeline sin que el reloj
quede contando sobre un bloque que ya no existe.
"""

from __future__ import annotations

from mukuwareru.nucleo.servicios import Configuracion, Estado, Fase, RelojPomodoro
from mukuwareru.nucleo.servicios.recorrido import Recorrido, fases_del_ciclo

BASE = Configuracion(
    trabajo_min=25, descanso_corto_min=5, descanso_largo_min=15, sesiones_por_ciclo=4
)


def nuevo() -> Recorrido:
    return Recorrido.desde_configuracion(BASE)


# --- Generacion ------------------------------------------------------------


def test_el_ciclo_alterna_y_cierra_con_descanso_largo() -> None:
    fases = fases_del_ciclo(BASE)
    assert len(fases) == 8
    assert fases[:2] == [Fase.TRABAJO, Fase.DESCANSO_CORTO]
    assert fases[-1] is Fase.DESCANSO_LARGO
    assert fases.count(Fase.DESCANSO_LARGO) == 1


def test_las_duraciones_salen_de_la_configuracion() -> None:
    recorrido = nuevo()
    assert recorrido.total == 8
    assert recorrido.actual.duracion_min == 25
    assert recorrido.bloques[1].duracion_min == 5
    assert recorrido.bloques[-1].duracion_min == 15
    assert recorrido.total_seg == 4 * 1500 + 3 * 300 + 900


def test_cada_bloque_tiene_un_id_propio() -> None:
    identificadores = [bloque.id for bloque in nuevo().bloques]
    assert len(set(identificadores)) == len(identificadores)


def test_un_recorrido_recien_generado_esta_intacto() -> None:
    assert not nuevo().tocado


# --- Edicion ---------------------------------------------------------------


def test_mover_reordena_y_deja_marca_de_mano() -> None:
    recorrido = nuevo()
    tercero = recorrido.bloques[2].id
    assert recorrido.mover(2, 0) == 0
    assert recorrido.bloques[0].id == tercero
    assert recorrido.tocado


def test_mover_al_mismo_hueco_no_cambia_nada() -> None:
    recorrido = nuevo()
    orden = [bloque.id for bloque in recorrido.bloques]
    assert recorrido.mover(3, 3) == 3
    assert recorrido.mover(3, 4) == 3
    assert [bloque.id for bloque in recorrido.bloques] == orden


def test_no_se_puede_mover_por_delante_de_lo_recorrido() -> None:
    recorrido = nuevo()
    recorrido.avanzar(contar=True)
    recorrido.avanzar(contar=True)
    assert recorrido.mover(5, 0) == 2  # se queda en el primer hueco disponible


def test_duplicar_copia_detras_del_original() -> None:
    recorrido = nuevo()
    original = recorrido.bloques[0]
    original.nombre = "Quant"
    assert recorrido.duplicar(0) == 1
    assert recorrido.bloques[1].nombre == "Quant"
    assert recorrido.bloques[1].id != original.id
    assert recorrido.total == 9


def test_eliminar_corrige_el_indice_si_borra_por_detras() -> None:
    recorrido = nuevo()
    recorrido.avanzar(contar=True)
    recorrido.avanzar(contar=True)
    assert recorrido.indice == 2
    assert recorrido.eliminar(0)
    assert recorrido.indice == 1


def test_eliminar_no_deja_el_recorrido_vacio() -> None:
    recorrido = Recorrido.desde_configuracion(BASE)
    while recorrido.total > 1:
        assert recorrido.eliminar(recorrido.total - 1)
    assert not recorrido.eliminar(0)
    assert recorrido.total == 1


def test_insertar_nunca_cae_en_el_pasado() -> None:
    recorrido = nuevo()
    recorrido.avanzar(contar=True)
    recorrido.avanzar(contar=True)
    assert recorrido.nuevo(Fase.TRABAJO, en=0) is recorrido.bloques[2]


# --- Reconfiguracion -------------------------------------------------------


def test_reconfigurar_refresca_los_bloques_intactos() -> None:
    recorrido = nuevo()
    recorrido.reconfigurar(Configuracion(trabajo_min=45))
    assert recorrido.bloques[0].duracion_min == 45


def test_reconfigurar_respeta_los_bloques_editados() -> None:
    recorrido = nuevo()
    recorrido.bloques[0].duracion_min = 50
    recorrido.bloques[0].editado = True
    recorrido.reconfigurar(Configuracion(trabajo_min=45))
    assert recorrido.bloques[0].duracion_min == 50
    assert recorrido.bloques[2].duracion_min == 45


def test_cambiar_las_sesiones_por_ciclo_regenera_si_nadie_toco_nada() -> None:
    recorrido = nuevo()
    recorrido.reconfigurar(Configuracion(sesiones_por_ciclo=2))
    assert recorrido.total == 4
    assert recorrido.bloques[-1].tipo is Fase.DESCANSO_LARGO


def test_cambiar_las_sesiones_por_ciclo_no_borra_lo_armado_a_mano() -> None:
    recorrido = nuevo()
    recorrido.mover(2, 0)
    recorrido.reconfigurar(Configuracion(sesiones_por_ciclo=2))
    assert recorrido.total == 8


# --- Cola infinita ---------------------------------------------------------


def test_al_agotarse_se_anade_un_par_nuevo() -> None:
    recorrido = nuevo()
    for _ in range(8):
        recorrido.avanzar(contar=True)
    assert recorrido.total == 10
    assert recorrido.actual.tipo is Fase.TRABAJO
    assert recorrido.bloques[9].tipo is Fase.DESCANSO_CORTO


def test_el_descanso_largo_vuelve_a_cerrar_el_ciclo_siguiente() -> None:
    recorrido = nuevo()
    for _ in range(14):
        recorrido.avanzar(contar=True)
    assert recorrido.bloques[15].tipo is Fase.DESCANSO_LARGO


# --- El reloj sobre el recorrido -------------------------------------------


def test_ajustar_la_duracion_en_marcha_traslada_la_diferencia() -> None:
    reloj = RelojPomodoro(BASE)
    reloj.iniciar()
    reloj.avanzar(47)
    reloj.ajustar_duracion(0, 45)
    assert reloj.restante_seg == 45 * 60 - 47
    assert reloj.estado is Estado.CORRIENDO


def test_ajustar_la_duracion_parado_reinicia_el_bloque() -> None:
    reloj = RelojPomodoro(BASE)
    reloj.ajustar_duracion(0, 45)
    assert reloj.restante_seg == 2700


def test_el_bloque_en_marcha_no_se_puede_mover() -> None:
    reloj = RelojPomodoro(BASE)
    assert reloj.movible(0)
    reloj.iniciar()
    assert not reloj.movible(0)
    assert reloj.movible(1)


def test_lo_ya_recorrido_no_se_edita() -> None:
    reloj = RelojPomodoro(BASE)
    reloj.iniciar()
    reloj.avanzar(1500)
    assert not reloj.editable(0)
    assert not reloj.movible(0)
    assert reloj.editable(1)


def test_recolocar_recorta_el_restante_al_bloque_nuevo() -> None:
    reloj = RelojPomodoro(BASE)
    reloj.iniciar()
    reloj.avanzar(60)
    reloj.recorrido.mover(1, 0)
    reloj.recolocar()
    assert reloj.fase is Fase.DESCANSO_CORTO
    assert reloj.restante_seg == 300


def test_ir_a_coloca_el_reloj_en_otro_bloque() -> None:
    reloj = RelojPomodoro(BASE)
    reloj.ir_a(3)
    assert reloj.fase is Fase.DESCANSO_CORTO
    assert reloj.estado is Estado.DETENIDO
    assert reloj.completadas == 0


def test_el_restante_total_cuenta_lo_que_queda_por_delante() -> None:
    reloj = RelojPomodoro(BASE)
    reloj.iniciar()
    reloj.avanzar(500)
    assert reloj.restante_total_seg == reloj.recorrido.total_seg - 500


def test_la_fase_terminada_trae_su_bloque() -> None:
    reloj = RelojPomodoro(BASE)
    reloj.recorrido.bloques[0].nombre = "Quant"
    reloj.iniciar()
    terminada = reloj.avanzar(1500)
    assert terminada is not None
    assert terminada.bloque is not None
    assert terminada.bloque.nombre == "Quant"
