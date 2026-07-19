"""Test del piso legal del complemento FPB — SPEC fondo FPB §5.1 (F2).

Con ``fpb.definicion_piso: "ultimo_anio"`` (regla legal: piso = último
salario formal topado [V, Nota 1 EF 2T-2025]) el gasto FPB agregado debe
subir respecto de ``"promedio_carrera"`` (la regla original): con perfiles
salariales crecientes el promedio de carrera subestima el piso. El caso
default está cubierto por la no-regresión §8.1.
"""

from __future__ import annotations

import copy

from motor.motor import simular


def test_piso_ultimo_anio_sube_gasto(cfg, datos):
    def corre(piso: str):
        c = copy.deepcopy(cfg)
        c["fpb"]["definicion_piso"] = piso
        r = simular(
            c, datos["conapo"], datos["qx"], datos["part"],
            escenario="base", semilla=c["semilla"],
            r_historico=datos["r_hist"], indice_salarial=datos["ind_sal"],
        )
        return r.anual.set_index("anio")["costo_FPB_total_mm"]

    promedio = corre("promedio_carrera")
    ultimo = corre("ultimo_anio")
    # mismo stream aleatorio (el flag no consume rng): comparación pareada
    for anio in (2035, 2050, 2070):
        assert ultimo[anio] > promedio[anio], (
            f"piso ultimo_anio no subió el gasto FPB en {anio}: "
            f"{ultimo[anio]:.1f} vs {promedio[anio]:.1f} mm"
        )
