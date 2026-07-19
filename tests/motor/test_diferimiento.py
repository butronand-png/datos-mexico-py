"""Tests del nodo de diferimiento 60 vs 65 — SPEC fondo FPB §8.2 y §8.6.

Cohorte sintética controlada: todos los agentes tienen 59 años en 2025
(cumplen 60 en 2026, primer año de proyección), mortalidad cero (la
decisión no se contamina con muertes) y formalidad casi segura (llegan a
los 60 con semanas de sobra). Sobre esa población se verifica que:

  - difiere ⟺ la regla activa lo dicta (umbral y vpn, recomputadas
    ex-post desde b60_hipotetica/b65_esperada);
  - retiro a 60 ⇒ requiere_FPB=False (la cesantía excluye el complemento
    por ley) y edad_retiro=60;
  - tasa_forzada ∈ {0.0, 1.0} fuerza la decisión en bloque;
  - la conciliación contable global sigue cerrando con el flag activo
    (§8.6: el retiro a 60 alimenta salida_retiro).
"""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from motor.motor import simular
from motor.reglas_sar import factor_anualidad

N_SINTETICO = 400


@pytest.fixture(scope="module")
def cfg_sintetico(cfg) -> dict:
    c = copy.deepcopy(cfg)
    c["simulacion"]["n_agentes"] = N_SINTETICO
    # formalidad casi segura: la cohorte llega a 60 con semanas de sobra
    c["mercado_laboral"]["persistencia_formal"] = 0.999
    c["diferimiento"] = {
        "activo": True, "regla": "umbral", "umbral": 2.0, "tasa_forzada": None
    }
    return c


@pytest.fixture(scope="module")
def conapo_sintetico() -> pd.DataFrame:
    """Población: solo 59 años en 2025; entrantes 2026+ con población 0."""
    filas = [
        {"anio": 2025, "edad": 59, "sexo": s, "poblacion": 1000.0}
        for s in ("H", "M")
    ]
    filas += [
        {"anio": a, "edad": 15, "sexo": "H", "poblacion": 0.0}
        for a in range(2026, 2071)
    ]
    return pd.DataFrame(filas)


@pytest.fixture(scope="module")
def qx_cero() -> dict[str, np.ndarray]:
    return {"H": np.zeros(110), "M": np.zeros(110)}


PART_FORMAL = {"formal": 0.97, "informal": 0.01, "desempleado": 0.01, "fuera": 0.01}


def _corre(cfg_s, conapo_s, qx_s, **dif) -> pd.DataFrame:
    c = copy.deepcopy(cfg_s)
    c["diferimiento"].update(dif)
    r = simular(
        c, conapo_s, qx_s, PART_FORMAL,
        escenario="base", semilla=c["semilla"],
    )
    return r.agentes, r.ledger


def test_regla_umbral(cfg_sintetico, conapo_sintetico, qx_cero):
    """difiere ⟺ b65_esperada >= umbral·b60, agente por agente."""
    d, _ = _corre(cfg_sintetico, conapo_sintetico, qx_cero, regla="umbral")
    dec = d[d["b60_hipotetica"].notna()]
    assert len(dec) > 0, "ningún agente llegó al nodo de decisión"
    esperado = dec["b65_esperada"] >= 2.0 * dec["b60_hipotetica"]
    assert (dec["difirio"] == esperado).all()


def test_regla_vpn(cfg_sintetico, conapo_sintetico, qx_cero, cfg):
    """difiere ⟺ VPN_esperar >= VPN_ya, recomputado con ä y kp60 de la tabla."""
    d, _ = _corre(cfg_sintetico, conapo_sintetico, qx_cero, regla="vpn")
    dec = d[d["b60_hipotetica"].notna()]
    assert len(dec) > 0
    i_tec = cfg["economia"]["tasa_tecnica_anualidad"]
    a60 = factor_anualidad(qx_cero["H"], 60, i_tec)
    a65 = factor_anualidad(qx_cero["H"], 65, i_tec)
    v5 = (1.0 / (1.0 + i_tec)) ** 5
    kp60 = 1.0  # mortalidad cero
    esperado = (
        dec["b65_esperada"] * a65 * v5 * kp60 >= dec["b60_hipotetica"] * a60
    )
    assert (dec["difirio"] == esperado).all()


def test_b65_incluye_aportaciones(cfg_sintetico, conapo_sintetico, qx_cero, cfg):
    """F1-bis (bitácora #29): b65_esperada proyecta CON aportaciones.

    Cota: la versión saldo-solo es b60·(1+r)⁵·ä60/ä65; con densidad y
    último salario positivos (toda la cohorte sintética cotiza), la
    proyección con aportaciones debe quedar ESTRICTAMENTE encima.
    """
    d, _ = _corre(cfg_sintetico, conapo_sintetico, qx_cero, regla="umbral")
    dec = d[d["b60_hipotetica"].notna()]
    assert len(dec) > 0
    i_tec = cfg["economia"]["tasa_tecnica_anualidad"]
    r_esp = cfg["economia"]["rendimiento_real_anual"]
    a60 = factor_anualidad(qx_cero["H"], 60, i_tec)
    a65 = factor_anualidad(qx_cero["H"], 65, i_tec)
    b65_saldo_solo = dec["b60_hipotetica"] * (1.0 + r_esp) ** 5 * (a60 / a65)
    assert (dec["b65_esperada"] > b65_saldo_solo).all(), (
        "b65_esperada no incorpora aportaciones esperadas"
    )


def test_cesantia_sin_fpb(cfg_sintetico, conapo_sintetico, qx_cero):
    """Retiro a 60 ⇒ requiere_FPB=False y edad_retiro=60 (es ley, F2)."""
    d, _ = _corre(cfg_sintetico, conapo_sintetico, qx_cero, tasa_forzada=0.0)
    ces = d[d["via_de_pension"] == "cesantia_60"]
    assert len(ces) > 0
    assert not ces["requiere_FPB"].any()
    assert (ces["edad_retiro"] == 60).all()
    assert (ces["pension_mensual"] > 0).all()


def test_tasa_forzada_extremos(cfg_sintetico, conapo_sintetico, qx_cero):
    """tasa_forzada 0.0 ⇒ nadie difiere; 1.0 ⇒ todos difieren y retiran a 65."""
    d0, _ = _corre(cfg_sintetico, conapo_sintetico, qx_cero, tasa_forzada=0.0)
    dec0 = d0[d0["b60_hipotetica"].notna()]
    assert len(dec0) > 0 and not dec0["difirio"].any()
    assert (dec0["via_de_pension"] == "cesantia_60").all()

    d1, _ = _corre(cfg_sintetico, conapo_sintetico, qx_cero, tasa_forzada=1.0)
    dec1 = d1[d1["b60_hipotetica"].notna()]
    assert len(dec1) > 0 and dec1["difirio"].all()
    # mortalidad cero: todos los que difieren llegan a 65 por vejez
    assert (dec1["via_de_pension"] == "vejez_65").all()
    assert (dec1["edad_retiro"] == 65).all()
    assert not dec1["murio_difiriendo"].any()


def test_contabilidad_con_diferimiento(cfg, datos):
    """§8.6: la conciliación agregada del ledger cierra con el flag activo
    y la población real (el retiro a 60 alimenta salida_retiro)."""
    # tasa_forzada=0.5 garantiza que AMBOS canales se ejercitan (cesantía a
    # 60 y diferimiento a 65) sin depender de qué dicte la regla endógena
    c = copy.deepcopy(cfg)
    c["diferimiento"] = {
        "activo": True, "regla": "vpn", "umbral": 2.0, "tasa_forzada": 0.5
    }
    r = simular(
        c, datos["conapo"], datos["qx"], datos["part"],
        escenario="base", semilla=c["semilla"],
        r_historico=datos["r_hist"], indice_salarial=datos["ind_sal"],
    )
    ledger = r.ledger
    assert (ledger["check_contable"] == "OK").all()
    saldo = ledger["saldo_total_mm"].to_numpy()
    flujo = (
        ledger["aportaciones_mm"]
        + ledger["rendimientos_mm"]
        - ledger["comisiones_mm"]
        - ledger["salidas_retiro_mm"]
        - ledger["salidas_muerte_mm"]
    ).to_numpy()
    np.testing.assert_allclose(np.diff(saldo, prepend=0.0), flujo,
                               rtol=1e-9, atol=1e-6)
    # ambos canales ejercitados: cesantías a 60 y diferimientos a 65
    assert (r.agentes["via_de_pension"] == "cesantia_60").sum() > 0
    assert r.agentes["difirio"].sum() > 0
