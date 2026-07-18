"""Tests de la recursión del fondo FPB — SPEC fondo FPB §8.3, §8.4 y §8.5.

§8.3 recursión analítica: con I=D=G=Gop=0, R_t = R_0·(1+r)^(t-2025) exacto;
     con G constante y r=0, T* tiene forma cerrada.
§8.4 unidades: el G_2026 del módulo == costo_FPB_total_mm 2026 del motor
     + cola del stock (tol 1e-6) — todo en mdp reales 2025.
§8.5 sanity observado: G_2026 simulado vs ~193 mdp/año observados [V,
     CONSAR: 289.61 mdp acumulados a cierre 2025 en ~18 meses]. Se espera
     simulado >> observado (acceso pleno vs rampa administrativa); la cota
     de 100x obliga a investigar antes de reportar si se rebasa.
"""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from motor.fondo_fpb import (
    anio_suficiencia,
    balance_vp,
    gasto_stock_mdp,
    trayectoria_fondo,
)

CFG_ANALITICO = {
    "rendimiento_real": 0.042,
    "gastos_operativos_mdp": 0.0,
    "factor_decaimiento_flujos": 1.0,
    "escenario_a": {
        "patrimonio_inicial_mdp": 50_000.0,
        "ingresos_anuales_mdp": 0.0,
        "devoluciones_anuales_mdp": 0.0,
    },
    "stock_inicial": {"gasto_anual_mdp": 193.0, "edad_cohorte": 66},
}


def _gasto_cero() -> pd.Series:
    return pd.Series(0.0, index=range(2026, 2071))


def test_recursion_solo_rendimiento():
    """I=D=G=Gop=0 ⇒ R_t = R_0·(1+r)^(t-2025), exacto (§8.3)."""
    tray = trayectoria_fondo(_gasto_cero(), CFG_ANALITICO, "escenario_a")
    r_0, r = 50_000.0, 0.042
    esperado = r_0 * (1.0 + r) ** (tray["anio"].to_numpy() - 2025)
    np.testing.assert_allclose(tray["patrimonio_mdp"].to_numpy(), esperado,
                               rtol=1e-12)
    assert anio_suficiencia(tray) is None
    # sin flujos, el balance VP es exactamente R_0
    assert balance_vp(tray, r) == pytest.approx(r_0, rel=1e-12)


def test_suficiencia_forma_cerrada():
    """G constante y r=0 ⇒ T* = 2025 + ceil(R_0/G) (primer R_t < 0) (§8.3)."""
    cfg = copy.deepcopy(CFG_ANALITICO)
    cfg["rendimiento_real"] = 0.0
    r_0, g = 50_000.0, 7_000.0
    gasto = pd.Series(g, index=range(2026, 2071))
    tray = trayectoria_fondo(gasto, cfg, "escenario_a")
    # R_t = R_0 - G·(t-2025) < 0  ⟺  t - 2025 > R_0/G
    t_esperado = 2025 + int(np.floor(r_0 / g)) + 1
    assert anio_suficiencia(tray) == t_esperado == 2033
    # balance VP con r=0: R_0 - 45·G
    assert balance_vp(tray, 0.0) == pytest.approx(r_0 - 45 * g, rel=1e-12)


def test_unidades_g2026(resultado_homogeneo, datos):
    """§8.4: G_2026 del módulo == costo_FPB_total_mm 2026 + stock (1e-6)."""
    anual = resultado_homogeneo.anual.set_index("anio")
    gasto = anual["costo_FPB_total_mm"]
    cfg = copy.deepcopy(CFG_ANALITICO)
    tray = trayectoria_fondo(gasto, cfg, "escenario_a", qx=datos["qx"])
    fila26 = tray[tray["anio"] == 2026].iloc[0]
    stock26 = gasto_stock_mdp(
        np.array([2026]), datos["qx"], cfg["stock_inicial"]
    )[0]
    g_modulo = fila26["gasto_fpb_mdp"] + fila26["gasto_stock_mdp"]
    assert g_modulo == pytest.approx(gasto.loc[2026] + stock26, abs=1e-6)
    # la cola del stock decae con supervivencia: S(2026) < 1, S monótona ↓
    stocks = tray[tray["anio"] > 2025]["gasto_stock_mdp"].to_numpy()
    assert 0 < stocks[0] < 193.0
    assert (np.diff(stocks) <= 0).all()


def test_sanity_gasto_observado(resultado_homogeneo):
    """§8.5: G_2026 simulado > ~193 mdp observados, pero < 100x (si no,
    investigar antes de reportar)."""
    g_2026 = resultado_homogeneo.anual.set_index("anio")["costo_FPB_total_mm"][2026]
    obs = 193.0
    assert g_2026 > obs, "el simulado debería exceder la rampa administrativa"
    assert g_2026 < 100 * obs, (
        f"G_2026 simulado {g_2026:.0f} mdp rebasa 100x el observado "
        f"({obs} mdp): investigar antes de reportar (SPEC §8.5)"
    )
