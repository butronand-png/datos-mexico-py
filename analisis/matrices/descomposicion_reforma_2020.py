"""Aislar el efecto de la reforma 2020 por década de retiro (Sección 7.5).

Separa, en la mejora por década del % sin pensión (95.6% en 2026-2035 →
78.1% en 2066-2070), cuánto es efecto mecánico de ventana de acumulación
(sistema nacido en 1997) y cuánto es la reforma DOF 16-dic-2020.

Contrafactual "sin reforma 2020" con el mecanismo PoliticaSAR existente
(cero código nuevo en el motor):

    PoliticaSAR(desde=2021, tasa_aportacion_total=0.065,
                semanas_requeridas_fijas=1250)

  - aportación patronal fija en 6.5% (sin calendario 2023-2030 a 15%);
    el `desde=2021` es inocuo para 2021-2022 (la tasa vigente ahí también
    es 6.5%), y PoliticaSAR garantiza backcast 1997-2020 idéntico.
  - semanas requeridas en el nivel pre-2020 (1250 fijas, sin transitorio
    750+25/año → 1000).

⚠️ ALCANCE DECLARADO: este contrafactual aísla tasa de aportación +
semanas requeridas. NO aísla la cuota social 2020: el motor modela la CS
como constante provisional (8 $/día, ≤4 UMA) sin distinción pre/post
2020, así que la CS es idéntica en ambos lados por construcción
(decisión de alcance, checkpoint Fase 0). La columna
`alcance_contrafactual` del CSV lo deja registrado.

Métrica: % sin pensión == masa en cero def. (a) de la tabla maestra
(tasa_reemplazo == 0 entre retirados 2026+ con anios_formal > 0) — la
misma serie por década que publica decada_retiro.csv (95.59 → 78.12).

Sanidad previa (falla el script si no pasa): el lado "con reforma"
(politica por defecto) debe reproducir EXACTAMENTE decada_retiro.csv
publicado; si pasa, ese CSV publicado ES el lado con_reforma de la
comparación (no se re-simula nada extra: las corridas de la sanidad
aportan los valores por semilla para los deltas pareados).

  efecto_reforma_pp = pct_sin_pension(sin_reforma) - pct(con_reforma)
                      (negativo == la reforma REDUCE el % sin pensión)

IC95: t de Student 4 gl sobre los deltas pareados por semilla (mismas
semillas en ambos lados, números aleatorios comunes).

Salida: resultados_finales/descomposicion_reforma_2020_por_decada.csv
Uso: .venv/bin/python descomposicion_reforma_2020.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "analisis" / "matrices"))
logging.disable(logging.WARNING)

from motor import reglas_sar
from motor.datos import (
    cargar_conapo,
    cargar_indice_salarial_real,
    cargar_mortalidad,
    cargar_rendimientos_reales,
    participaciones_enoe,
    qx_por_sexo,
)
from motor.motor import simular

N_AGENTES = 100_000
N_SEMILLAS = 5
RES = REPO / "analisis" / "matrices" / "resultados_finales"
T_4GL = 2.7764
DECADAS = [(2026, 2035), (2036, 2045), (2046, 2055), (2056, 2065), (2066, 2070)]
ALCANCE = ("aisla tasa_aportacion (6.5% fija) + semanas requeridas (1250); "
           "NO cuota social (constante e idéntica en ambos lados)")

SIN_REFORMA = reglas_sar.PoliticaSAR(
    desde=2021, tasa_aportacion_total=0.065, semanas_requeridas_fijas=1250,
)


def ic95(vals: list[float]) -> tuple[float, float]:
    a = np.asarray(vals, dtype=float)
    return float(a.mean()), float(T_4GL * a.std(ddof=1) / np.sqrt(len(a)))


def masa_cero_decada(d: pd.DataFrame, lo: int, hi: int) -> float:
    g = d[d["cohorte_retiro"].between(lo, hi) & (d["anios_formal"] > 0)]
    return 100 * (g["tasa_reemplazo"] == 0).mean()


def sanidad_decadas(retirados: dict[int, pd.DataFrame], semillas: list[int]) -> None:
    """El lado con-reforma debe reproducir decada_retiro.csv publicado."""
    r_all = pd.concat(retirados.values(), ignore_index=True)
    filas = []
    for lo, hi in DECADAS:
        g = r_all[r_all["cohorte_retiro"].between(lo, hi)]
        cot = g[g["anios_formal"] > 0]
        pen = g[g["pension_mensual"] > 0]
        _, ic = ic95([masa_cero_decada(retirados[s], lo, hi) for s in semillas])
        et = f"{lo}-{hi}" + (" (parcial)" if hi == 2070 else "")
        filas.append({
            "decada_retiro": et,
            "n_pooled": len(g),
            "pct_nunca_cotizo": round(100 * (g["anios_formal"] == 0).mean(), 2),
            "masa_cero_pct_def_a": round(
                100 * (cot["tasa_reemplazo"] == 0).mean(), 2),
            "pct_con_pension": round(100 * (g["pension_mensual"] > 0).mean(), 2),
            "pct_FPB": round(100 * g["requiere_FPB"].mean(), 2),
            "pct_PG": round(100 * g["requiere_PG"].mean(), 2),
            "densidad_media_def_a": round(
                float(cot["densidad_cotizacion"].mean()), 4),
            "tr_mediana_pensionados": round(
                float(pen["tasa_reemplazo"].median()), 4),
            "tr_p25_pensionados": round(
                float(pen["tasa_reemplazo"].quantile(.25)), 4),
            "tr_p75_pensionados": round(
                float(pen["tasa_reemplazo"].quantile(.75)), 4),
            "masa_cero_ic95_semiancho": round(ic, 2),
        })
    calc = pd.DataFrame(filas)
    pub = pd.read_csv(RES / "decada_retiro.csv")
    pd.testing.assert_frame_equal(calc, pub, check_dtype=False)


def main() -> int:
    t0 = time.time()
    cfg0 = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
    semillas = [cfg0["semilla"] + k for k in range(N_SEMILLAS)]

    print(f"[1/4] Insumos… n_agentes={N_AGENTES:,}, semillas={semillas}")
    conapo = cargar_conapo()
    qx = qx_por_sexo(cargar_mortalidad())
    part = participaciones_enoe(usar_api=False)
    r_hist = cargar_rendimientos_reales()
    ind_sal = cargar_indice_salarial_real()

    def corre(sem: int, politica) -> pd.DataFrame:
        cfg = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
        cfg["simulacion"]["n_agentes"] = N_AGENTES
        with contextlib.redirect_stdout(io.StringIO()):
            r = simular(
                cfg, conapo, qx, part, escenario="base", semilla=sem,
                politica=politica, r_historico=r_hist,
                indice_salarial=ind_sal, matriz_heterogenea=True,
            )
        return r.agentes[r.agentes["cohorte_retiro"] >= 2026]

    print("[2/4] Lado con-reforma (politica por defecto) para sanidad…")
    con = {sem: corre(sem, None) for sem in semillas}
    sanidad_decadas(con, semillas)
    print("      decada_retiro.csv publicado: reproducción EXACTA — se usa "
          "como lado con_reforma")

    print("[3/4] Contrafactual sin reforma 2020 "
          f"({SIN_REFORMA!r})…")
    sin = {sem: corre(sem, SIN_REFORMA) for sem in semillas}

    print("[4/4] Efecto por década (deltas pareados por semilla)…")
    pub = pd.read_csv(RES / "decada_retiro.csv").set_index("decada_retiro")
    filas = []
    for lo, hi in DECADAS:
        et = f"{lo}-{hi}" + (" (parcial)" if hi == 2070 else "")
        v_con = [masa_cero_decada(con[s], lo, hi) for s in semillas]
        v_sin = [masa_cero_decada(sin[s], lo, hi) for s in semillas]
        deltas = np.array(v_sin) - np.array(v_con)
        med, ic = ic95(list(deltas))
        m_sin, _ = ic95(v_sin)
        filas.append({
            "decada": et,
            "pct_sin_pension_con_reforma": pub.loc[et, "masa_cero_pct_def_a"],
            "pct_sin_pension_sin_reforma": round(m_sin, 2),
            "efecto_reforma_pp": round(med, 2),
            "ic95": round(ic, 2),
            **{f"efecto_semilla_{s}": round(v, 2)
               for s, v in zip(semillas, deltas, strict=True)},
            "alcance_contrafactual": ALCANCE,
        })
    out = pd.DataFrame(filas)
    out.to_csv(RES / "descomposicion_reforma_2020_por_decada.csv", index=False)
    print(out.drop(columns="alcance_contrafactual").to_string(index=False))
    print(f"OK → resultados_finales/descomposicion_reforma_2020_por_decada.csv "
          f"({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
