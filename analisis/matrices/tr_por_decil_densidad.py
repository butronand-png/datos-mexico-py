"""Tasa de reemplazo por decil de densidad de cotización (Sección 7.4).

Re-corte del dump a nivel agente de la corrida final — CERO simulación
nueva. La densidad es la variable CONTINUA (anios_formal/anios_activo,
def. (a) de la auditoría), no el corte por perfil demográfico que ya
existe en perfil_sexo_escolaridad.csv.

Protocolo:
  - Universo: cotizantes (anios_formal >= 1) entre los retirados 2026+.
  - Las 5 semillas AGRUPADAS (pooled) para deciles estables — los puntos
    de corte se calculan una sola vez sobre el pooled, NO por semilla.
  - Deciles con pd.qcut(densidad, 10, duplicates="drop"); si la masa de
    densidades bajas colapsa deciles, el script lo reporta y publica los
    puntos de corte reales.
  - Por decil: n, densidad media, % con TR == 0, percentiles de TR
    (p10, p25, p50, p75, p90).

Insumo: motor/outputs/agentes_nivel_agente_final.csv.gz (generado y
verificado por dump_nivel_agente.py; si no existe, correr ese script).

Salida: resultados_finales/tr_por_decil_densidad.csv
Uso: .venv/bin/python tr_por_decil_densidad.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DUMP = REPO / "motor" / "outputs" / "agentes_nivel_agente_final.csv.gz"
RES = REPO / "analisis" / "matrices" / "resultados_finales"

PCTS = [10, 25, 50, 75, 90]


def main() -> int:
    if not DUMP.exists():
        print(f"FALTA el insumo {DUMP.relative_to(REPO)} — "
              "generarlo con dump_nivel_agente.py", file=sys.stderr)
        return 1
    d = pd.read_csv(DUMP)
    cot = d[d["anios_formal"] >= 1].copy()
    print(f"universo: {len(cot):,} cotizantes (anios_formal >= 1) de "
          f"{len(d):,} retirados 2026+ pooled (5 semillas)")

    cot["decil"], cortes = pd.qcut(
        cot["densidad_cotizacion"], 10, labels=False,
        retbins=True, duplicates="drop",
    )
    n_deciles = cot["decil"].nunique()
    if n_deciles < 10:
        print(f"⚠️ COLAPSO: qcut produjo {n_deciles} grupos (masa de "
              "densidades bajas empata puntos de corte)")
    print("puntos de corte:", np.round(cortes, 4).tolist())

    filas = []
    for dec, g in cot.groupby("decil"):
        tr = g["tasa_reemplazo"]
        filas.append({
            "decil": int(dec) + 1,
            "densidad_min": round(float(g["densidad_cotizacion"].min()), 4),
            "densidad_max": round(float(g["densidad_cotizacion"].max()), 4),
            "n_pooled": len(g),
            "densidad_media": round(float(g["densidad_cotizacion"].mean()), 4),
            "pct_tr_cero": round(100 * float((tr == 0).mean()), 2),
            **{f"tr_p{p}": round(float(tr.quantile(p / 100)), 4)
               for p in PCTS},
        })
    out = pd.DataFrame(filas)
    assert out["n_pooled"].sum() == len(cot), "deciles no cubren el universo"
    out.to_csv(RES / "tr_por_decil_densidad.csv", index=False)
    print(out.to_string(index=False))
    print("OK → resultados_finales/tr_por_decil_densidad.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
