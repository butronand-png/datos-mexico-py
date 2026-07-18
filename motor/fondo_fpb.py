"""Recursión del Fondo de Pensiones para el Bienestar (SPEC fondo FPB §5.2 y §6).

Post-proceso PURO sobre el DataFrame ``anual`` de ``simular()`` — no toca
el core del motor. Todo en millones de pesos (mdp) REALES DE 2025.

Recursión anual del patrimonio del fideicomiso:

    R_t = (1 + r_fpb)·R_{t-1} + I_t - D_t - G_t - Gop_t,   t = 2026…2070

con rendimiento sobre el saldo inicial del año (⚠️ SUPUESTO) y:
    I_t   aportaciones de cuentas inactivas (70+/75+ no reclamadas)
    D_t   devoluciones a cuentahabientes
    G_t   gasto en complementos FPB = motor (costo_FPB_total_mm, media
          entre semillas) + cola exógena del stock 2024-2025 (§5.2)
    Gop_t gastos operativos del fiduciario

Dos especificaciones coherentes (evitan doble conteo de la reserva de
devoluciones de 17,416 mdp — Nota 7, EF 2T-2025):

    Escenario A (bruto, reporte principal): R_0 = patrimonio contable
      jun-2025 (53,105 mdp [V]); devoluciones y aportaciones explícitas
      (flujos observados anualizados) con decaimiento [S].
    Escenario B (neto, comparable Actuarius): R_0 = patrimonio NO
      reservado (35,689 mdp [V] = 53,105 - 17,416); D_t = 0 (la reserva
      ya pre-fondea las devoluciones) e I_t neto.

Los flujos de los EF 2T-2025 son nominales 2025 = pesos reales 2025 en el
año base [V]; el decaimiento se aplica en términos reales [S].

Fuente primaria: fpbienestar.org.mx/d/Estadosfinancieros2T2025.pdf
(Banxico fiduciario, NIF B-16), extracción 2026-07-18 en
specs/REF_estados_financieros_FPB_2T2025.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ANIO_BASE = 2025  # año del patrimonio inicial (EF 2T-2025) y de los pesos reales


def supervivencia_stock(
    anios: np.ndarray, qx: dict[str, np.ndarray], edad_cohorte: int
) -> np.ndarray:
    """S(t) del stock de beneficiarios 2024-2025 (§5.2): 0.5·ₖp_H + 0.5·ₖp_M.

    La cohorte del stock tiene ``edad_cohorte`` años en 2025 (⚠️ SUPUESTO:
    66 — beneficiarios que cumplieron 65 en 2024-2025); k = t - 2025 años
    de supervivencia con EMSSA-09 por sexo, mezcla 50/50 [S].
    """
    horizonte = int(anios.max() - ANIO_BASE)
    s_por_sexo = []
    for sexo in ("H", "M"):
        q = qx[sexo]
        kpx = np.ones(horizonte + 1)
        for k in range(1, horizonte + 1):
            edad = min(edad_cohorte + k - 1, len(q) - 1)
            kpx[k] = kpx[k - 1] * (1.0 - q[edad])
        s_por_sexo.append(kpx)
    mezcla = 0.5 * s_por_sexo[0] + 0.5 * s_por_sexo[1]
    return mezcla[(anios - ANIO_BASE).astype(int)]


def gasto_stock_mdp(
    anios: np.ndarray, qx: dict[str, np.ndarray], cfg_stock: dict
) -> np.ndarray:
    """G_t del stock pre-2026 (§5.2): gasto_anual_mdp · S(t), cola exógena.

    ``gasto_anual_mdp`` (⚠️ PROVISIONAL: 193 = 289.61 mdp acumulados en
    ~18 meses a cierre 2025 [V, CONSAR]) NO sale del loop del motor: el
    stock 2024-2025 está excluido de la población por diseño.
    """
    s = supervivencia_stock(anios, qx, int(cfg_stock["edad_cohorte"]))
    return float(cfg_stock["gasto_anual_mdp"]) * s


def trayectoria_fondo(
    gasto_fpb_mdp: pd.Series,
    cfg_fondo: dict,
    escenario: str = "escenario_a",
    qx: dict[str, np.ndarray] | None = None,
) -> pd.DataFrame:
    """Trayectoria anual del patrimonio del fondo, 2025 (base) → 2070.

    Args:
        gasto_fpb_mdp: G_t del motor (``anual.costo_FPB_total_mm``, media
            entre semillas), indexada por año; se toman 2026+.
        cfg_fondo: sección ``fpb_fondo`` de config (parámetros y escenarios).
        escenario: ``"escenario_a"`` (bruto) | ``"escenario_b"`` (neto).
        qx: tablas EMSSA por sexo para la cola del stock (§5.2); ``None``
            omite el stock (útil en tests analíticos).

    Returns:
        DataFrame con ``anio, ingresos_mdp, devoluciones_mdp,
        gasto_fpb_mdp, gasto_stock_mdp, gastos_operativos_mdp,
        rendimiento_mdp, patrimonio_mdp``. La fila 2025 es el año base
        (solo patrimonio inicial). La recursión continúa mecánicamente
        aunque el patrimonio sea negativo (el déficit acumulado devenga
        el mismo r — convención para leer la magnitud del faltante).
    """
    esc = cfg_fondo[escenario]
    r_fpb = float(cfg_fondo["rendimiento_real"])
    gastos_op = float(cfg_fondo["gastos_operativos_mdp"])
    decaimiento = float(cfg_fondo["factor_decaimiento_flujos"])

    anios = np.array(sorted(a for a in gasto_fpb_mdp.index if a > ANIO_BASE))
    g_motor = gasto_fpb_mdp.loc[anios].to_numpy(dtype=float)
    g_stock = (
        gasto_stock_mdp(anios, qx, cfg_fondo["stock_inicial"])
        if qx is not None
        else np.zeros(len(anios))
    )
    decay = decaimiento ** (anios - anios[0])
    ingresos = float(esc["ingresos_anuales_mdp"]) * decay
    devoluciones = float(esc["devoluciones_anuales_mdp"]) * decay

    filas = [{
        "anio": ANIO_BASE,
        "ingresos_mdp": 0.0,
        "devoluciones_mdp": 0.0,
        "gasto_fpb_mdp": 0.0,
        "gasto_stock_mdp": 0.0,
        "gastos_operativos_mdp": 0.0,
        "rendimiento_mdp": 0.0,
        "patrimonio_mdp": float(esc["patrimonio_inicial_mdp"]),
    }]
    patrimonio = float(esc["patrimonio_inicial_mdp"])
    for i, anio in enumerate(anios):
        rendimiento = r_fpb * patrimonio  # sobre saldo inicial del año [S]
        patrimonio = (
            patrimonio
            + rendimiento
            + ingresos[i]
            - devoluciones[i]
            - (g_motor[i] + g_stock[i])
            - gastos_op
        )
        filas.append({
            "anio": int(anio),
            "ingresos_mdp": float(ingresos[i]),
            "devoluciones_mdp": float(devoluciones[i]),
            "gasto_fpb_mdp": float(g_motor[i]),
            "gasto_stock_mdp": float(g_stock[i]),
            "gastos_operativos_mdp": gastos_op,
            "rendimiento_mdp": float(rendimiento),
            "patrimonio_mdp": float(patrimonio),
        })
    return pd.DataFrame(filas)


def anio_suficiencia(trayectoria: pd.DataFrame) -> int | None:
    """Primer año con patrimonio negativo (T*); None si no se agota a 2070."""
    negativos = trayectoria.loc[
        (trayectoria["anio"] > ANIO_BASE) & (trayectoria["patrimonio_mdp"] < 0),
        "anio",
    ]
    return int(negativos.iloc[0]) if len(negativos) else None


def balance_vp(trayectoria: pd.DataFrame, r: float) -> float:
    """Balance actuarial en valor presente, truncado al horizonte (2070).

    B = R_0 + Σ_t (I_t - D_t - G_t - Gop_t) / (1+r)^(t-2025)

    Los gastos operativos entran al flujo neto (coherencia con la
    recursión; el spec §6 los omite en la fórmula pero son ~54 mdp/año,
    inmateriales frente a G_t).
    """
    base = trayectoria.loc[trayectoria["anio"] == ANIO_BASE, "patrimonio_mdp"]
    r_0 = float(base.iloc[0])
    flujos = trayectoria[trayectoria["anio"] > ANIO_BASE]
    neto = (
        flujos["ingresos_mdp"]
        - flujos["devoluciones_mdp"]
        - flujos["gasto_fpb_mdp"]
        - flujos["gasto_stock_mdp"]
        - flujos["gastos_operativos_mdp"]
    ).to_numpy()
    descuento = (1.0 + r) ** (flujos["anio"].to_numpy() - ANIO_BASE)
    return r_0 + float((neto / descuento).sum())
