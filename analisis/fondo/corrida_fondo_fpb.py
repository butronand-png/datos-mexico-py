"""Corrida citable del fondo FPB con diferimiento endógeno (SPEC §9.6, Sección 8).

Motor heterogéneo definitivo (5 estados, matrices anuales ENOE 2015-2024),
escenario base, 100,000 agentes x 5 semillas, con los flags de la Sección 8
ENCENDIDOS (a diferencia de las corridas de Secciones 6-7):

    diferimiento.activo = true   (ambas reglas: "umbral" y "vpn")
    fpb.regla_tope      = "real_constante"   (bitácora #26)
    fpb.definicion_piso = "ultimo_anio"      (regla legal, §5.1)

Produce en analisis/fondo/:
  a) tasa_diferimiento.csv       — tasa endógena por regla (media ± IC95
                                   entre semillas, t de Student 4 gl),
                                   desagregada por sexo, escolaridad y
                                   decil de densidad realizada — la
                                   granularidad que Actuarius (3 estratos
                                   fijos) no tiene (§4.4)
  b) gasto_fpb_anual.csv         — G_t del motor por regla (media ± IC95)
  c) trayectoria_fondo_{a,b}.csv — recursión del fideicomiso (§6), G_t de
                                   la regla "umbral" (default de reporte)
  d) resumen_fondo.csv           — T* y balance VP por escenario y regla
  e) fig_patrimonio_fondo.png    — patrimonio vs año, T* propio y la
                                   referencia 2042 de Actuarius
  metadata_corrida_fondo.csv     — parámetros, insumos y runtime

Uso: .venv/bin/python analisis/fondo/corrida_fondo_fpb.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import subprocess
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

# ---------------------------------------------------------------- parámetros
N_AGENTES = 100_000
N_SEMILLAS = 5
REGLAS = ["umbral", "vpn"]
REGLA_REPORTE = "umbral"  # default de reporte (réplica Actuarius, §4.2)
ANIO_SUFICIENCIA_ACTUARIUS = 2042
OUT = REPO / "analisis" / "fondo"

# Paleta de referencia validada (skill dataviz, modo claro) — misma que
# corrida_final_paper.py
INK, SEC, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURF = "#e1e0d9", "#c3c2b7", "#fcfcfb"
AZUL, AQUA, AZUL_OSCURO = "#2a78d6", "#1baf7a", "#104281"
ROJO = "#c43d3d"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "text.color": INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": SEC,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlecolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.facecolor": SURF,
    "axes.facecolor": SURF,
    "savefig.facecolor": SURF,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

T_4GL = 2.7764  # t de Student al 95%, 4 grados de libertad (5 semillas)

ORDEN_ESC = ["basica-", "media_sup", "superior"]
ETIQ_ESC = {"basica-": "Básica o menos", "media_sup": "Media superior",
            "superior": "Superior"}
ETIQ_SEXO = {"H": "Hombres", "M": "Mujeres"}


def ic95(vals: list[float]) -> tuple[float, float, float]:
    """(media, semiancho IC95 con t de 4 gl, sd) entre semillas."""
    a = np.asarray(vals, dtype=float)
    sd = a.std(ddof=1)
    return float(a.mean()), float(T_4GL * sd / np.sqrt(len(a))), float(sd)


def cfg_seccion8(regla: str) -> dict:
    """Config con los flags de la Sección 8 encendidos."""
    cfg = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
    cfg["simulacion"]["n_agentes"] = N_AGENTES
    cfg["fpb"]["regla_tope"] = "real_constante"
    cfg["fpb"]["definicion_piso"] = "ultimo_anio"
    cfg["diferimiento"]["activo"] = True
    cfg["diferimiento"]["regla"] = regla
    return cfg


def main() -> int:
    t_total = time.time()
    cfg0 = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
    semillas = [cfg0["semilla"] + k for k in range(N_SEMILLAS)]

    print(f"[1/5] Insumos (fallback estático)… n_agentes={N_AGENTES:,}, "
          f"semillas={semillas}, reglas={REGLAS}")
    conapo = cargar_conapo()
    qx = qx_por_sexo(cargar_mortalidad())
    part = participaciones_enoe(usar_api=False)
    r_hist = cargar_rendimientos_reales()
    ind_sal = cargar_indice_salarial_real()

    # ----------------------------------------- corridas por regla x semilla
    print(f"[2/5] {len(REGLAS)}x{N_SEMILLAS} corridas completas 1997-2070…")
    decisores: dict[tuple[str, int], pd.DataFrame] = {}
    gasto: dict[tuple[str, int], pd.Series] = {}
    runtimes = {}
    for regla in REGLAS:
        for sem in semillas:
            t0 = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                r = simular(
                    cfg_seccion8(regla), conapo, qx, part, escenario="base",
                    semilla=sem, r_historico=r_hist, indice_salarial=ind_sal,
                    matriz_heterogenea=True,
                )
            d = r.agentes
            dec = d[d["b60_hipotetica"].notna()].copy()
            dec["semilla"] = sem
            decisores[(regla, sem)] = dec
            gasto[(regla, sem)] = r.anual.set_index("anio")["costo_FPB_total_mm"]
            runtimes[(regla, sem)] = time.time() - t0
            print(f"      {regla} · semilla {sem}: {len(dec):,} decisores, "
                  f"tasa {dec['difirio'].mean():.3f} "
                  f"({runtimes[(regla, sem)]:.0f}s)")

    # ----------------------------------------- a) tasa de diferimiento
    print("[3/5] Tablas…")
    filas = []

    def agrega(regla: str, dimension: str, categoria: str, filtro) -> None:
        vals, ns = [], []
        for sem in semillas:
            d = decisores[(regla, sem)]
            sub = d[filtro(d)]
            if len(sub):
                vals.append(100 * sub["difirio"].mean())
                ns.append(len(sub))
        if not vals:
            print(f"      ⚠️ celda vacía omitida: {regla}/{dimension}/{categoria}")
            return
        m, ic, sd = ic95(vals)
        filas.append({
            "regla": regla, "dimension": dimension, "categoria": categoria,
            "tasa_diferimiento_pct": round(m, 2), "ic95_semiancho": round(ic, 2),
            "sd_entre_semillas": round(sd, 3), "n_decisores_pooled": int(sum(ns)),
            **{f"semilla_{s}": round(v, 2)
               for s, v in zip(semillas, vals, strict=False)},
        })

    for regla in REGLAS:
        agrega(regla, "total", "total", lambda d: pd.Series(True, index=d.index))
        for sexo in ("H", "M"):
            agrega(regla, "sexo", ETIQ_SEXO[sexo],
                   lambda d, sx=sexo: d["genero"] == sx)
        for esc in ORDEN_ESC:
            agrega(regla, "escolaridad", ETIQ_ESC[esc],
                   lambda d, e=esc: d["escolaridad"] == e)
        # deciles de densidad realizada (def. a): cortes calculados UNA
        # sola vez sobre el pooled de las 5 semillas (convención del
        # insumo 7.4, tr_por_decil_densidad.py) — cortes por semilla
        # colapsan bins con los empates y desestabilizan el IC
        pooled = pd.concat([decisores[(regla, s)] for s in semillas])
        _, cortes = pd.qcut(pooled["densidad_cotizacion"], 10, labels=False,
                            retbins=True, duplicates="drop")
        if len(cortes) < 11:
            print(f"      ⚠️ {regla}: qcut pooled produjo {len(cortes) - 1} "
                  "grupos (empates de densidad)")
        cortes[0], cortes[-1] = -np.inf, np.inf
        for dec_i in range(len(cortes) - 1):
            def filtro_decil(d, k=dec_i, c=cortes):
                bins = pd.cut(d["densidad_cotizacion"], c, labels=False,
                              include_lowest=True)
                return bins == k
            agrega(regla, "decil_densidad", f"D{dec_i + 1}", filtro_decil)
        # costo de esperar: % de los que difirieron que murieron antes de 65
        vals = []
        for sem in semillas:
            d = decisores[(regla, sem)]
            dif = d[d["difirio"]]
            vals.append(100 * dif["murio_difiriendo"].mean() if len(dif) else 0.0)
        m, ic, sd = ic95(vals)
        filas.append({
            "regla": regla, "dimension": "murio_difiriendo",
            "categoria": "% de difirientes muertos antes de 65",
            "tasa_diferimiento_pct": round(m, 2), "ic95_semiancho": round(ic, 2),
            "sd_entre_semillas": round(sd, 3),
            "n_decisores_pooled": int(sum(
                decisores[(regla, s)]["difirio"].sum() for s in semillas)),
            **{f"semilla_{s}": round(v, 2)
               for s, v in zip(semillas, vals, strict=False)},
        })
    pd.DataFrame(filas).to_csv(OUT / "tasa_diferimiento.csv", index=False)

    # ----------------------------------------- b) G_t por regla
    filas = []
    anios = sorted(gasto[(REGLAS[0], semillas[0])].index)
    for regla in REGLAS:
        for anio in anios:
            if anio <= 2025:
                continue
            vals = [float(gasto[(regla, s)][anio]) for s in semillas]
            m, ic, _ = ic95(vals)
            filas.append({"regla": regla, "anio": anio,
                          "gasto_fpb_mdp": round(m, 3),
                          "ic95_semiancho": round(ic, 3)})
    pd.DataFrame(filas).to_csv(OUT / "gasto_fpb_anual.csv", index=False)

    # ----------------------------------------- c/d) recursión del fondo
    print("[4/5] Recursión del fondo + figura…")
    resumen = []
    trayectorias = {}
    for regla in REGLAS:
        g_media = pd.concat(
            [gasto[(regla, s)] for s in semillas], axis=1
        ).mean(axis=1)
        for esc_id, nombre in [("escenario_a", "a"), ("escenario_b", "b")]:
            tray = trayectoria_fondo(g_media, cfg0["fpb_fondo"], esc_id, qx=qx)
            t_star = anio_suficiencia(tray)
            b_vp = balance_vp(tray, cfg0["fpb_fondo"]["rendimiento_real"])
            resumen.append({
                "regla": regla, "escenario": esc_id,
                "patrimonio_inicial_mdp":
                    cfg0["fpb_fondo"][esc_id]["patrimonio_inicial_mdp"],
                "anio_suficiencia": t_star if t_star is not None else "no se agota",
                "balance_vp_mdp": round(b_vp, 1),
                "gasto_fpb_2026_mdp": round(float(g_media.loc[2026]), 1),
                "gasto_fpb_2070_mdp": round(float(g_media.loc[2070]), 1),
            })
            if regla == REGLA_REPORTE:
                trayectorias[nombre] = tray
                tray.to_csv(OUT / f"trayectoria_fondo_{nombre}.csv", index=False)
    pd.DataFrame(resumen).to_csv(OUT / "resumen_fondo.csv", index=False)

    # ----------------------------------------- e) figura patrimonio vs año
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    etiquetas = {
        "a": "Escenario A (bruto: R₀ = 53,105 mdp, devoluciones explícitas)",
        "b": "Escenario B (neto de reserva: R₀ = 35,689 mdp — comparable Actuarius)",
    }
    for nombre, color in [("a", AZUL), ("b", AQUA)]:
        tray = trayectorias[nombre]
        ax.plot(tray["anio"], tray["patrimonio_mdp"] / 1e3, color=color,
                lw=2, zorder=3, label=etiquetas[nombre])
        t_star = anio_suficiencia(tray)
        if t_star is not None:
            ax.axvline(t_star, color=color, lw=0.8, ls=":", zorder=2)
            ax.annotate(f"T* = {t_star}", xy=(t_star, 0),
                        xytext=(t_star + 0.6, 18), color=color, fontsize=9,
                        fontweight="bold")
    ax.axhline(0, color=INK, lw=0.8, zorder=2)
    ax.axvline(ANIO_SUFICIENCIA_ACTUARIUS, color=ROJO, lw=1.0, ls="--",
               zorder=2)
    ax.annotate("Actuarius: 2042", xy=(ANIO_SUFICIENCIA_ACTUARIUS, 0),
                xytext=(ANIO_SUFICIENCIA_ACTUARIUS + 0.6, -28), color=ROJO,
                fontsize=9)
    ax.set_xlabel("Año")
    ax.set_ylabel("Patrimonio del fideicomiso (miles de mdp, reales 2025)")
    ax.set_title("Patrimonio del Fondo de Pensiones para el Bienestar, 2025-2070")
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    fig.text(0.01, -0.06,
             f"Motor heterogéneo, {N_AGENTES:,} agentes x {N_SEMILLAS} semillas "
             f"(G_t = media), diferimiento endógeno regla «{REGLA_REPORTE}», "
             f"piso = último salario, tope FPB real constante. "
             f"r = {cfg0['fpb_fondo']['rendimiento_real']:.1%} real.",
             fontsize=7.5, color=MUTED)
    fig.savefig(OUT / "fig_patrimonio_fondo.png")
    plt.close(fig)

    # ----------------------------------------- metadata
    print("[5/5] Metadata…")
    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True).stdout.strip()
    meta = pd.DataFrame([
        {"clave": "n_agentes", "valor": N_AGENTES},
        {"clave": "semillas", "valor": ";".join(map(str, semillas))},
        {"clave": "reglas_diferimiento", "valor": ";".join(REGLAS)},
        {"clave": "regla_reporte_fondo", "valor": REGLA_REPORTE},
        {"clave": "motor", "valor": "heterogéneo 5 estados, matrices anuales "
                                    "ENOE 2015-2024 (matriz_heterogenea=True)"},
        {"clave": "flags_seccion8",
         "valor": "diferimiento.activo=true; fpb.regla_tope=real_constante; "
                  "fpb.definicion_piso=ultimo_anio"},
        {"clave": "fpb_fondo",
         "valor": "; ".join(
             f"{k}={v}" for k, v in cfg0["fpb_fondo"].items()
             if not isinstance(v, dict))},
        {"clave": "ic95_metodo",
         "valor": f"t de Student 4 gl ({T_4GL}) x sd/sqrt(5), entre semillas"},
        {"clave": "commit_codigo", "valor": commit},
        {"clave": "runtime_total_s", "valor": round(time.time() - t_total, 1)},
    ])
    meta.to_csv(OUT / "metadata_corrida_fondo.csv", index=False)
    print(f"\nRUNTIME TOTAL: {time.time() - t_total:.1f}s — artefactos en {OUT}/")
    for p in sorted(OUT.glob("*.csv")) + sorted(OUT.glob("*.png")):
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
