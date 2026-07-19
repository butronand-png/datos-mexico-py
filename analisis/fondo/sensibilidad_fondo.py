"""Sensibilidad del fondo FPB + tabla comparativa Actuarius (SPEC §7 — F4).

Seis ejes sobre la recursión de motor/fondo_fpb.py (T* y balance VP por
escenario A/B). Los ejes 1 y 3 requieren corridas nuevas del motor (100k x
5 semillas por punto); los ejes 2, 4, 5 y 6 son post-proceso puro sobre el
G_t endógeno de la corrida citable (gasto_fpb_anual.csv — correr antes
corrida_fondo_fpb.py).

  1. tasa_forzada ∈ {0.10, 0.20, 0.40, 0.60, 0.80, 1.00} + endógenas
     (umbral, vpn) — eje #1 de Actuarius
  2. r_fpb ∈ {0.032, 0.042, 0.062}
  3. definicion_piso: ultimo_anio vs promedio_carrera (eje propio)
  4. I_t = 0 (¿mueve el balance <1%?)
  5. R_0 ∈ {35,689 [V, neto]; 53,105 [V, jun-25]; 60,000 [I, cierre 2025
     extrapolado]}
  6. decaimiento de flujos ∈ {0.90, 0.95, 1.00} — solo escenario A

Benchmarks Actuarius (PDF dic-2025, SPEC §11): base 40% espera, T*=2042,
balance 100 años −3,520,904 mdp; cobertura 50 años −2,683,873 mdp (nuestro
comparable — el horizonte propio trunca en 2070, 45 años); espera 100% →
−6,766,133 / 2036; espera 10% → −935,038 / 2048.

Salidas: sensibilidad_fondo.csv, tabla_comparativa_actuarius.md
Uso: .venv/bin/python analisis/fondo/sensibilidad_fondo.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "analisis" / "matrices"))
logging.disable(logging.WARNING)

from motor.datos import (
    cargar_conapo,
    cargar_indice_salarial_real,
    cargar_mortalidad,
    cargar_rendimientos_reales,
    participaciones_enoe,
    qx_por_sexo,
)
from motor.fondo_fpb import anio_suficiencia, balance_vp, trayectoria_fondo
from motor.motor import simular

N_AGENTES = 100_000
N_SEMILLAS = 5
OUT = REPO / "analisis" / "fondo"

TASAS_FORZADAS = [0.10, 0.20, 0.40, 0.60, 0.80, 1.00]
R_FPB_GRID = [0.032, 0.042, 0.062]
R0_GRID = [
    ("35689_neto_V", "escenario_b", None),
    ("53105_jun25_V", "escenario_a", None),
    ("60000_cierre25_I", "escenario_a", 60_000.0),
]
DECAIMIENTO_GRID = [0.90, 0.95, 1.00]

# Benchmarks Actuarius [V, PDF dic-2025] — comparables al escenario B (neto)
ACTUARIUS = {
    "base_40pct": {"balance_mdp": -2_683_873, "anio": 2042,
                   "nota": "cobertura 50 años (comparable); base 100 años: -3,520,904"},
    "forzada_0.10": {"balance_mdp": -935_038, "anio": 2048, "nota": "espera 10%"},
    "forzada_1.00": {"balance_mdp": -6_766_133, "anio": 2036, "nota": "espera 100%"},
}


def main() -> int:
    t_total = time.time()
    cfg0 = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
    semillas = [cfg0["semilla"] + k for k in range(N_SEMILLAS)]
    cfg_fondo = cfg0["fpb_fondo"]
    r_base = cfg_fondo["rendimiento_real"]

    print(f"[1/4] Insumos… n={N_AGENTES:,}, semillas={semillas}")
    conapo = cargar_conapo()
    qx = qx_por_sexo(cargar_mortalidad())
    part = participaciones_enoe(usar_api=False)
    r_hist = cargar_rendimientos_reales()
    ind_sal = cargar_indice_salarial_real()

    # G_t endógeno de la corrida citable (media entre semillas, por regla)
    ruta_gasto = OUT / "gasto_fpb_anual.csv"
    if not ruta_gasto.exists():
        raise FileNotFoundError(
            "gasto_fpb_anual.csv no existe: correr corrida_fondo_fpb.py primero"
        )
    g_endo = pd.read_csv(ruta_gasto)
    g_por_regla = {
        regla: g_endo[g_endo["regla"] == regla].set_index("anio")["gasto_fpb_mdp"]
        for regla in g_endo["regla"].unique()
    }
    g_umbral = g_por_regla["umbral"]

    def corre_g(overrides_dif: dict, piso: str = "ultimo_anio") -> pd.Series:
        """G_t media entre semillas con los flags Sección 8 + overrides."""
        series = []
        for sem in semillas:
            cfg = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
            cfg["simulacion"]["n_agentes"] = N_AGENTES
            cfg["fpb"]["regla_tope"] = "real_constante"
            cfg["fpb"]["definicion_piso"] = piso
            cfg["diferimiento"]["activo"] = True
            cfg["diferimiento"].update(overrides_dif)
            with contextlib.redirect_stdout(io.StringIO()):
                r = simular(
                    cfg, conapo, qx, part, escenario="base", semilla=sem,
                    r_historico=r_hist, indice_salarial=ind_sal,
                    matriz_heterogenea=True,
                )
            series.append(r.anual.set_index("anio")["costo_FPB_total_mm"])
        return pd.concat(series, axis=1).mean(axis=1)

    def evalua(g: pd.Series, escenario: str, r_fpb: float | None = None,
               cfg_mod: dict | None = None) -> tuple[int | str, float]:
        cf = {k: (dict(v) if isinstance(v, dict) else v)
              for k, v in cfg_fondo.items()}
        if r_fpb is not None:
            cf["rendimiento_real"] = r_fpb
        if cfg_mod:
            for k, v in cfg_mod.items():
                if isinstance(v, dict):
                    cf[k].update(v)
                else:
                    cf[k] = v
        tray = trayectoria_fondo(g, cf, escenario, qx=qx)
        t_star = anio_suficiencia(tray)
        b = balance_vp(tray, cf["rendimiento_real"])
        return (t_star if t_star is not None else "no se agota"), b

    filas = []

    def registra(eje, punto, escenario, t_star, b, comparable=None, nota=""):
        fila = {"eje": eje, "punto": punto, "escenario": escenario,
                "anio_suficiencia": t_star, "balance_vp_mdp": round(b, 1),
                "actuarius_balance_mdp": None, "actuarius_anio": None,
                "delta_balance_mdp": None, "nota": nota}
        if comparable and comparable in ACTUARIUS and escenario == "escenario_b":
            ref = ACTUARIUS[comparable]
            fila["actuarius_balance_mdp"] = ref["balance_mdp"]
            fila["actuarius_anio"] = ref["anio"]
            fila["delta_balance_mdp"] = round(b - ref["balance_mdp"], 1)
            fila["nota"] = (fila["nota"] + " | " if fila["nota"] else "") + ref["nota"]
        filas.append(fila)

    # tasas endógenas observadas (corrida citable) para las notas
    tasa = pd.read_csv(OUT / "tasa_diferimiento.csv")
    tasa_total = {
        regla: tasa[(tasa["regla"] == regla)
                    & (tasa["dimension"] == "total")].iloc[0]
        for regla in g_por_regla
    }

    # ------------------------------------------------ eje 1: tasa de espera
    print("[2/4] Eje 1 (tasa de diferimiento): 6 puntos x 5 semillas…")
    for regla, g in g_por_regla.items():
        t = tasa_total[regla]
        for esc in ("escenario_a", "escenario_b"):
            t_star, b = evalua(g, esc)
            registra("tasa_diferimiento", f"endogena_{regla}", esc, t_star, b,
                     nota=f"tasa endógena {regla}: "
                          f"{t['tasa_diferimiento_pct']:.1f}% ± "
                          f"{t['ic95_semiancho']:.1f}")
    for tf in TASAS_FORZADAS:
        t0 = time.time()
        g = corre_g({"tasa_forzada": tf})
        for esc in ("escenario_a", "escenario_b"):
            t_star, b = evalua(g, esc)
            registra("tasa_diferimiento", f"forzada_{tf:.2f}", esc, t_star, b,
                     comparable=f"forzada_{tf:.2f}"
                     if f"forzada_{tf:.2f}" in ACTUARIUS
                     else ("base_40pct" if tf == 0.40 else None))
        print(f"      forzada={tf:.2f}: {time.time() - t0:.0f}s")

    # ------------------------------------------------ eje 2: r_fpb
    print("[3/4] Ejes 2 y 4-6 (post-proceso) + eje 3 (piso, 5 semillas)…")
    for r_fpb in R_FPB_GRID:
        for esc in ("escenario_a", "escenario_b"):
            t_star, b = evalua(g_umbral, esc, r_fpb=r_fpb)
            registra("r_fpb", f"{r_fpb:.3f}", esc, t_star, b,
                     nota="G_t endógeno regla umbral")

    # ------------------------------------------------ eje 3: piso
    g_piso = corre_g({}, piso="promedio_carrera")
    for esc in ("escenario_a", "escenario_b"):
        t_star, b = evalua(g_umbral, esc)
        registra("definicion_piso", "ultimo_anio", esc, t_star, b,
                 nota="regla legal (base Sección 8)")
        t_star, b = evalua(g_piso, esc)
        registra("definicion_piso", "promedio_carrera", esc, t_star, b,
                 nota="regla original Secciones 6-7")

    # ------------------------------------------------ eje 4: I_t = 0
    for esc in ("escenario_a", "escenario_b"):
        _, b_base = evalua(g_umbral, esc)
        t_star, b_sin = evalua(g_umbral, esc,
                               cfg_mod={esc: {"ingresos_anuales_mdp": 0.0}})
        delta_pct = 100.0 * abs(b_sin - b_base) / abs(b_base)
        registra("ingresos_cero", "I_t=0", esc, t_star, b_sin,
                 nota=f"|ΔB| = {delta_pct:.2f}% del balance base")

    # ------------------------------------------------ eje 5: R_0
    for etiqueta, esc, override in R0_GRID:
        cfg_mod = ({esc: {"patrimonio_inicial_mdp": override}}
                   if override is not None else None)
        t_star, b = evalua(g_umbral, esc, cfg_mod=cfg_mod)
        registra("patrimonio_inicial", etiqueta, esc, t_star, b)

    # ------------------------------------------------ eje 6: decaimiento (A)
    for dec in DECAIMIENTO_GRID:
        t_star, b = evalua(g_umbral, "escenario_a",
                           cfg_mod={"factor_decaimiento_flujos": dec})
        registra("decaimiento_flujos", f"{dec:.2f}", "escenario_a", t_star, b)

    df = pd.DataFrame(filas)
    df.to_csv(OUT / "sensibilidad_fondo.csv", index=False)

    # ------------------------------------------------ tabla comparativa md
    print("[4/4] Tabla comparativa…")
    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True).stdout.strip()

    def fmt(v):
        return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)

    lineas = [
        "# Comparativa Datos México vs Actuarius — fondo FPB",
        "",
        f"Corrida: motor heterogéneo, {N_AGENTES:,} agentes x {N_SEMILLAS} "
        f"semillas, diferimiento endógeno, piso último salario, tope real "
        f"constante. Commit `{commit}`. Unidades: mdp reales 2025.",
        "",
        "**Advertencia de horizonte**: nuestro balance trunca en 2070 (45 "
        "años); el comparable de Actuarius es su cobertura a 50 años, NO su "
        "base a 100. El escenario B (patrimonio neto de reserva, R₀ = "
        "35,689) replica su especificación; el A (bruto, R₀ = 53,105, "
        "devoluciones explícitas) es nuestro reporte principal.",
        "",
        "| Métrica | Datos México | Actuarius | Delta / nota |",
        "|---|---|---|---|",
    ]
    t_umbral, t_vpn = tasa_total["umbral"], tasa_total["vpn"]
    lineas.append(
        f"| Tasa de diferimiento endógena | umbral: "
        f"{t_umbral['tasa_diferimiento_pct']:.1f}% ± "
        f"{t_umbral['ic95_semiancho']:.1f}; vpn: "
        f"{t_vpn['tasa_diferimiento_pct']:.1f}% ± {t_vpn['ic95_semiancho']:.1f} "
        f"| 40% (supuesto, b65 ≥ 2·b60) | b65 proyectada CON aportaciones "
        f"esperadas (densidad personal x último salario, bitácora #29); "
        f"desagregación por sexo/escolaridad/decil en tasa_diferimiento.csv |")
    resumen = pd.read_csv(OUT / "resumen_fondo.csv")
    for _, r in resumen[resumen["regla"] == "umbral"].iterrows():
        esc = "A (bruto)" if r["escenario"] == "escenario_a" else "B (neto)"
        comp = ("2042 / -2,683,873 (50 años)"
                if r["escenario"] == "escenario_b" else "—")
        lineas.append(
            f"| T* y balance VP, escenario {esc} | {r['anio_suficiencia']} / "
            f"{r['balance_vp_mdp']:,.0f} | {comp} | endógeno umbral |")
    sens_b = df[(df["eje"] == "tasa_diferimiento")
                & (df["escenario"] == "escenario_b")
                & df["actuarius_balance_mdp"].notna()]
    for _, r in sens_b.iterrows():
        lineas.append(
            f"| Espera {r['punto']} (esc. B) | {r['anio_suficiencia']} / "
            f"{r['balance_vp_mdp']:,.0f} | {r['actuarius_anio']} / "
            f"{r['actuarius_balance_mdp']:,.0f} | Δ balance "
            f"{r['delta_balance_mdp']:,.0f} |")
    ing = df[df["eje"] == "ingresos_cero"].set_index("escenario")
    lineas += [
        f"| Rendimiento del fondo | {r_base:.1%} real (± en eje r_fpb) | "
        f"4.2% real | mismo supuesto [S] |",
        "| Patrimonio inicial | A: 53,105 [V] / B: 35,689 [V] | ~35,000 | "
        "B replica su neto de reserva (53,105 − 17,416, Nota 7 EF 2T-2025) |",
        f"| Sensibilidad a I_t = 0 | {ing.loc['escenario_a', 'nota']} (A); "
        f"{ing.loc['escenario_b', 'nota']} (B) | ingresos netos VP = 0.57% "
        f"del gasto | ⚠️ el spec §7.4 esperaba <1%: NO se cumple — nuestro "
        f"balance es ~18x menor en magnitud que el de Actuarius, así que el "
        f"mismo I_t deja de ser despreciable. Hallazgo, no error |",
        "",
        "## Jerarquía de sensibilidad (rango del balance VP por eje, esc. A)",
        "",
        "| Eje | B mínimo | B máximo | Rango |",
        "|---|---|---|---|",
    ]
    for eje, g_ in df[df["escenario"] == "escenario_a"].groupby("eje"):
        b_min, b_max = g_["balance_vp_mdp"].min(), g_["balance_vp_mdp"].max()
        lineas.append(f"| {eje} | {b_min:,.0f} | {b_max:,.0f} | "
                      f"{b_max - b_min:,.0f} |")
    (OUT / "tabla_comparativa_actuarius.md").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8")

    print(f"\nRUNTIME TOTAL: {time.time() - t_total:.1f}s")
    print(f"  {OUT / 'sensibilidad_fondo.csv'}")
    print(f"  {OUT / 'tabla_comparativa_actuarius.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
