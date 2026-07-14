"""Descomposición de la brecha de género en % sin pensión (Sección 7.3).

Mide cuánto de la brecha hombres/mujeres viene de cada canal, con swaps
PARALELOS contra un único baseline (no encadenados):

  Baseline        : tensor ENOE y mortalidad EMSSA-09 por sexo observados
                    (idéntico a la corrida final del paper, mismas semillas).
  Contrafactual A : las MUJERES transitan con las matrices de HOMBRES
                    (tensor[:, sexo=M] := tensor[:, sexo=H]); salarios y
                    mortalidad femeninos. Canal densidad/transiciones.
  Contrafactual B : canal salario. El proceso salarial del motor NO tiene
                    término de sexo (log_w = base + mu + perfil_edad +
                    nivel + secular; motor.py), así que el swap es la
                    identidad: la corrida se ejecuta de todos modos y se
                    VERIFICA que es bit-idéntica al baseline. Efecto = 0
                    por construcción — limitación declarada del modelo,
                    no un resultado empírico.
  Contrafactual C : las MUJERES mueren con la qx de HOMBRES (EMSSA-09
                    masculina), que también gobierna su factor de
                    anualidad. Canal longevidad completo.

Los efectos se miden sobre las MUJERES retiradas 2026+ (mismas semillas →
números aleatorios comunes; los deltas por semilla son pareados):

  efecto_canal = metrica(contrafactual) - metrica(baseline_mujeres)
  brecha_total = metrica(baseline_hombres) - metrica(baseline_mujeres)
  residual     = brecha_total - suma(efectos)   # ≠ 0 esperado (umbrales)

Dos métricas (mismas definiciones que los artefactos publicados):
  pct_sin_pension : % de retiradas 2026+ con pension_mensual == 0
                    (nunca cotizó + saldo en una exhibición; complemento
                    exacto de pct_con_pension en perfil_sexo_escolaridad).
  masa_cero_def_a : % con tasa_reemplazo == 0 entre quienes cotizaron
                    alguna vez (denominador (a) de la tabla maestra).

Sanidad integrada (falla el script si no pasa):
  1. El baseline reproduce EXACTAMENTE el perfil_sexo_escolaridad.csv
     publicado (todas las celdas, mismas semillas).
  2. El contrafactual B es bit-idéntico al baseline (frame completo).

IC95: t de Student 4 gl entre semillas, idéntico al protocolo Sección 6.

Salida: resultados_finales/descomposicion_brecha_genero.csv
Uso: .venv/bin/python descomposicion_brecha_genero.py
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

from asignacion_perfiles import construye_tensor
from carga_matrices import cargar_matrices_anuales

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

ORDEN_ESC = ["basica-", "media_sup", "superior"]
ETIQ_ESC = {"basica-": "Básica o menos", "media_sup": "Media superior",
            "superior": "Superior"}
ETIQ_SEXO = {"H": "Hombres", "M": "Mujeres"}


def ic95(vals: list[float]) -> tuple[float, float]:
    a = np.asarray(vals, dtype=float)
    return float(a.mean()), float(T_4GL * a.std(ddof=1) / np.sqrt(len(a)))


def pct_sin_pension(d: pd.DataFrame) -> float:
    return 100 * (d["pension_mensual"] == 0).mean()


def masa_cero_def_a(d: pd.DataFrame) -> float:
    cot = d[d["anios_formal"] > 0]
    return 100 * (cot["tasa_reemplazo"] == 0).mean()


METRICAS = {"pct_sin_pension": pct_sin_pension,
            "masa_cero_def_a": masa_cero_def_a}


def sanidad_perfil(retirados: dict[int, pd.DataFrame], semillas: list[int]) -> None:
    """El baseline debe reproducir perfil_sexo_escolaridad.csv publicado."""
    r_all = pd.concat(retirados.values(), ignore_index=True)

    def resumen_grupo(g: pd.DataFrame) -> dict:
        cot = g[g["anios_formal"] > 0]
        pen = g[g["pension_mensual"] > 0]
        return {
            "n_pooled": len(g),
            "pct_nunca_cotizo": round(100 * (g["anios_formal"] == 0).mean(), 2),
            "masa_cero_pct_def_a": round(
                100 * (cot["tasa_reemplazo"] == 0).mean(), 2) if len(cot) else np.nan,
            "pct_con_pension": round(100 * (g["pension_mensual"] > 0).mean(), 2),
            "pct_FPB": round(100 * g["requiere_FPB"].mean(), 2),
            "pct_PG": round(100 * g["requiere_PG"].mean(), 2),
            "densidad_media_def_a": round(
                float(cot["densidad_cotizacion"].mean()), 4) if len(cot) else np.nan,
            "tr_mediana_pensionados": round(
                float(pen["tasa_reemplazo"].median()), 4) if len(pen) else np.nan,
            "tr_p25_pensionados": round(
                float(pen["tasa_reemplazo"].quantile(.25)), 4) if len(pen) else np.nan,
            "tr_p75_pensionados": round(
                float(pen["tasa_reemplazo"].quantile(.75)), 4) if len(pen) else np.nan,
        }

    filas = []
    for sexo in ["H", "M"]:
        for esc in ORDEN_ESC:
            g = r_all[(r_all["genero"] == sexo) & (r_all["escolaridad"] == esc)]
            vals = []
            for s in semillas:
                d = retirados[s]
                cot = d[(d["genero"] == sexo) & (d["escolaridad"] == esc)
                        & (d["anios_formal"] > 0)]
                vals.append(100 * (cot["tasa_reemplazo"] == 0).mean())
            _, ic = ic95(vals)
            filas.append({"sexo": ETIQ_SEXO[sexo], "escolaridad": ETIQ_ESC[esc],
                          **resumen_grupo(g),
                          "masa_cero_ic95_semiancho": round(ic, 2)})
    calc = pd.DataFrame(filas)
    pub = pd.read_csv(RES / "perfil_sexo_escolaridad.csv")
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

    tensor_base = construye_tensor(cargar_matrices_anuales())
    tensor_swap = tensor_base.copy()
    tensor_swap[:, 1] = tensor_base[:, 0]  # mujeres ← matrices de hombres
    assert np.allclose(tensor_swap.sum(axis=-1), 1.0, atol=1e-9)
    qx_swap = {"H": qx["H"], "M": qx["H"]}  # mujeres ← qx de hombres

    ESCENARIOS = {
        "baseline": {},
        "A_densidad": {"tensor_transicion": tensor_swap},
        "B_salario": {},  # proceso salarial sin sexo: identidad deliberada
        "C_longevidad": {"qx_swap": True},
    }

    def corre(sem: int, extra: dict):
        cfg = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
        cfg["simulacion"]["n_agentes"] = N_AGENTES
        kwargs = dict(extra)
        qx_run = qx_swap if kwargs.pop("qx_swap", False) else qx
        with contextlib.redirect_stdout(io.StringIO()):
            return simular(
                cfg, conapo, qx_run, part, escenario="base", semilla=sem,
                r_historico=r_hist, indice_salarial=ind_sal,
                matriz_heterogenea=True, **kwargs,
            )

    print(f"[2/4] {len(ESCENARIOS)} escenarios x {N_SEMILLAS} semillas…")
    # metricas[escenario][metrica][sexo] = lista por semilla
    metricas: dict = {e: {m: {"H": [], "M": []} for m in METRICAS}
                      for e in ESCENARIOS}
    retirados_base: dict[int, pd.DataFrame] = {}
    for sem in semillas:
        frames = {}
        for esc, extra in ESCENARIOS.items():
            r = corre(sem, extra)
            frames[esc] = r.agentes
            ret = r.agentes[r.agentes["cohorte_retiro"] >= 2026]
            for m, fn in METRICAS.items():
                for sx in ["H", "M"]:
                    metricas[esc][m][sx].append(fn(ret[ret["genero"] == sx]))
        # B bit-idéntico al baseline (canal salario nulo por construcción)
        pd.testing.assert_frame_equal(frames["B_salario"], frames["baseline"])
        d = frames["baseline"]
        ret = d[d["cohorte_retiro"] >= 2026].copy()
        ret["semilla"] = sem
        retirados_base[sem] = ret
        print(f"      semilla {sem}: OK (B ≡ baseline verificado)")

    print("[3/4] Sanidad: baseline vs perfil_sexo_escolaridad.csv publicado…")
    sanidad_perfil(retirados_base, semillas)
    print("      reproducción EXACTA (todas las celdas)")

    print("[4/4] Efectos con deltas pareados por semilla…")
    filas = []
    for m in METRICAS:
        base_m = np.array(metricas["baseline"][m]["M"])
        base_h = np.array(metricas["baseline"][m]["H"])
        brecha = base_h - base_m  # por semilla, pareada
        efectos = {}
        for canal, esc in [("densidad_transiciones", "A_densidad"),
                           ("salario", "B_salario"),
                           ("longevidad", "C_longevidad")]:
            efectos[canal] = np.array(metricas[esc][m]["M"]) - base_m
        residual = brecha - sum(efectos.values())
        brecha_media = brecha.mean()

        def fila(canal: str, vals: np.ndarray, con_pct: bool = True,
                 m: str = m, brecha_media: float = brecha_media) -> dict:
            med, ic = ic95(list(vals))
            return {
                "metrica": m, "canal": canal,
                "efecto_pp": round(med, 2), "ic95_semiancho": round(ic, 2),
                "pct_del_total": round(100 * med / brecha_media, 1)
                if con_pct else np.nan,
                **{f"semilla_{s}": round(v, 2)
                   for s, v in zip(semillas, vals, strict=True)},
            }

        filas.append(fila("nivel_baseline_mujeres", base_m, con_pct=False))
        filas.append(fila("nivel_baseline_hombres", base_h, con_pct=False))
        for canal, vals in efectos.items():
            filas.append(fila(canal, vals))
        filas.append(fila("residual_interaccion", residual))
        filas.append(fila("brecha_total", brecha))

    out = pd.DataFrame(filas)
    out.to_csv(RES / "descomposicion_brecha_genero.csv", index=False)
    print(out.to_string(index=False))
    print(f"OK → resultados_finales/descomposicion_brecha_genero.csv "
          f"({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
