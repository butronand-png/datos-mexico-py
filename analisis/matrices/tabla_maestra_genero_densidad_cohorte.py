"""Tabla maestra: TR por género × decil de densidad × década (Sección 7).

El deliverable formal de la Sección 7: cruce a TRES vías, distinto de las
tablas de una vía ya publicadas (perfil_sexo_escolaridad, decada_retiro,
tr_por_decil_densidad). Re-corte del dump a nivel agente — CERO
simulación nueva.

Protocolo:
  - Universo: cotizantes (anios_formal >= 1) entre los retirados 2026+,
    5 semillas pooled — idéntico a tr_por_decil_densidad.py.
  - Deciles de densidad con los MISMOS puntos de corte de la Tarea 2:
    qcut sobre el pooled completo (determinista sobre los mismos datos),
    verificados contra los publicados en tr_por_decil_densidad.csv.
    Los deciles NO se recalculan por celda: un agente cae en el mismo
    decil en toda la tabla.
  - Celdas: género (2) × decil (10) × década de retiro (5) = hasta 100.
  - Por celda: n, % sin pensión (TR == 0 dentro de cotizantes, def. (a)),
    TR p10/p25/p50/p75/p90.
  - Celdas con n < 500: baja_confiabilidad = True, EXPLÍCITO — se
    publican igual (no se esconden ni se completan con supuestos).

Insumo: motor/outputs/agentes_nivel_agente_final.csv.gz (generado y
verificado por dump_nivel_agente.py).

Salida: resultados_finales/tabla_maestra_genero_densidad_cohorte.csv
Uso: .venv/bin/python tabla_maestra_genero_densidad_cohorte.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DUMP = REPO / "motor" / "outputs" / "agentes_nivel_agente_final.csv.gz"
RES = REPO / "analisis" / "matrices" / "resultados_finales"

PCTS = [10, 25, 50, 75, 90]
N_MIN_CONFIABLE = 500
DECADAS = [(2026, 2035), (2036, 2045), (2046, 2055), (2056, 2065), (2066, 2070)]
ETIQ_SEXO = {"H": "Hombres", "M": "Mujeres"}


def main() -> int:
    if not DUMP.exists():
        print(f"FALTA el insumo {DUMP.relative_to(REPO)} — "
              "generarlo con dump_nivel_agente.py", file=sys.stderr)
        return 1
    d = pd.read_csv(DUMP)
    cot = d[d["anios_formal"] >= 1].copy()

    # Deciles idénticos a la Tarea 2: mismo universo pooled, mismo qcut.
    cot["decil"] = pd.qcut(
        cot["densidad_cotizacion"], 10, labels=False, duplicates="drop",
    )
    cot["decil"] = cot["decil"].astype(int) + 1
    # Verificación: los rangos por decil coinciden con los publicados.
    pub = pd.read_csv(RES / "tr_por_decil_densidad.csv")
    rangos = cot.groupby("decil")["densidad_cotizacion"].agg(["min", "max"])
    assert (rangos["min"].round(4).to_numpy() == pub["densidad_min"].to_numpy()).all()
    assert (rangos["max"].round(4).to_numpy() == pub["densidad_max"].to_numpy()).all()
    print(f"universo: {len(cot):,} cotizantes pooled; deciles verificados "
          "contra tr_por_decil_densidad.csv")

    cot["decada"] = ""
    for lo, hi in DECADAS:
        et = f"{lo}-{hi}" + (" (parcial)" if hi == 2070 else "")
        cot.loc[cot["cohorte_retiro"].between(lo, hi), "decada"] = et
    assert (cot["decada"] != "").all(), "cohortes fuera de las décadas"

    filas = []
    for (sexo, decil, decada), g in cot.groupby(
        ["genero", "decil", "decada"], sort=True
    ):
        tr = g["tasa_reemplazo"]
        filas.append({
            "genero": ETIQ_SEXO[sexo],
            "decil_densidad": decil,
            "decada_retiro": decada,
            "n_pooled": len(g),
            "baja_confiabilidad": len(g) < N_MIN_CONFIABLE,
            "densidad_media": round(float(g["densidad_cotizacion"].mean()), 4),
            "pct_sin_pension": round(100 * float((tr == 0).mean()), 2),
            **{f"tr_p{p}": round(float(tr.quantile(p / 100)), 4)
               for p in PCTS},
        })
    out = pd.DataFrame(filas).sort_values(
        ["genero", "decil_densidad", "decada_retiro"]
    ).reset_index(drop=True)
    assert out["n_pooled"].sum() == len(cot), "celdas no cubren el universo"

    n_baja = int(out["baja_confiabilidad"].sum())
    print(f"celdas: {len(out)} (de 100 posibles); con n<{N_MIN_CONFIABLE}: "
          f"{n_baja} (marcadas baja_confiabilidad=True)")
    if n_baja:
        peq = out[out["baja_confiabilidad"]]
        print(peq[["genero", "decil_densidad", "decada_retiro", "n_pooled"]]
              .to_string(index=False))

    out.to_csv(RES / "tabla_maestra_genero_densidad_cohorte.csv", index=False)
    print("OK → resultados_finales/tabla_maestra_genero_densidad_cohorte.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
