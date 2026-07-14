"""Dump a nivel agente de la corrida final del paper (insumo Sección 7).

Re-corre las 5 semillas de corrida_final_paper.py con configuración
IDÉNTICA (100,000 agentes, heterogénea 5 estados, escenario base, insumos
con fallback estático) y persiste el pooled agente-semilla de los
retirados 2026+ — el archivo a nivel agente que la corrida final usó en
memoria pero nunca escribió a disco.

Columnas: las de ResultadoSimulacion.agentes (agente_id, semilla, genero,
escolaridad, cohorte_retiro, densidad_cotizacion, semanas_cotizadas,
tasa_reemplazo, saldo_final, pension_mensual, requiere_PG, requiere_FPB,
anios_formal, estado_final, …) más `via_de_pension`, derivada con la MISMA
clasificación de cobertura.csv (clasifica() de corrida_final_paper.py).

Verificación integrada (falla el script si no pasa):
  - masa en cero por semilla y denominador == tabla_maestra_masa_cero.csv
    publicada (redondeo a 2 decimales), y n pooled por denominador.
  - total de retirados pooled == metadata_corrida.csv (391,487).

Salida: motor/outputs/agentes_nivel_agente_final.csv.gz (NO versionado —
motor/outputs/ está en .gitignore; el artefacto es reproducible con este
script, determinista por semillas).

Uso: .venv/bin/python dump_nivel_agente.py
"""

from __future__ import annotations

import contextlib
import io
import logging
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
from motor.motor import simular

N_AGENTES = 100_000
N_SEMILLAS = 5
OUT_DIR = REPO / "motor" / "outputs"
RES = REPO / "analisis" / "matrices" / "resultados_finales"
SALIDA = OUT_DIR / "agentes_nivel_agente_final.csv.gz"


def via_de_pension(d: pd.DataFrame) -> pd.Series:
    """Clasificación idéntica a clasifica() de corrida_final_paper.py."""
    cat = pd.Series("", index=d.index)
    cat[d["anios_formal"] == 0] = "nunca_cotizo"
    cat[(d["anios_formal"] > 0) & (d["pension_mensual"] == 0)] = \
        "sin_pension_saldo_en_exhibicion"
    cat[(d["pension_mensual"] > 0) & d["requiere_PG"]] = "pension_garantizada"
    cat[(d["pension_mensual"] > 0) & ~d["requiere_PG"] & d["requiere_FPB"]] = \
        "contributiva_con_complemento_FPB"
    cat[(d["pension_mensual"] > 0) & ~d["requiere_PG"] & ~d["requiere_FPB"]] = \
        "contributiva_plena"
    return cat


def main() -> int:
    t0 = time.time()
    cfg0 = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
    semillas = [cfg0["semilla"] + k for k in range(N_SEMILLAS)]

    print(f"[1/3] Insumos (fallback estático)… n_agentes={N_AGENTES:,}, "
          f"semillas={semillas}")
    conapo = cargar_conapo()
    qx = qx_por_sexo(cargar_mortalidad())
    part = participaciones_enoe(usar_api=False)
    r_hist = cargar_rendimientos_reales()
    ind_sal = cargar_indice_salarial_real()

    print("[2/3] 5 corridas completas 1997-2070…")
    frames = []
    for sem in semillas:
        cfg = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
        cfg["simulacion"]["n_agentes"] = N_AGENTES
        with contextlib.redirect_stdout(io.StringIO()):
            r = simular(
                cfg, conapo, qx, part, escenario="base", semilla=sem,
                r_historico=r_hist, indice_salarial=ind_sal,
                matriz_heterogenea=True,
            )
        ret = r.agentes[r.agentes["cohorte_retiro"] >= 2026].copy()
        assert ret.index.max() < N_AGENTES  # retirados == stock inicial
        frames.append(ret)
        print(f"      semilla {sem}: {len(ret):,} retirados 2026+")
    pooled = pd.concat(frames, ignore_index=True)
    pooled["via_de_pension"] = via_de_pension(pooled)

    # ------------------------------------------------ verificación obligatoria
    print("[3/3] Verificación contra artefactos publicados…")
    meta = pd.read_csv(RES / "metadata_corrida.csv").set_index("clave")["valor"]
    n_meta = int(meta["retirados_2026plus_pooled"])
    assert len(pooled) == n_meta, \
        f"retirados pooled {len(pooled):,} != metadata {n_meta:,}"

    tabla = pd.read_csv(RES / "tabla_maestra_masa_cero.csv")
    DENOMS = {
        "a_anios_formal_gt0": lambda d: d["anios_formal"] > 0,
        "c_anios_formal_ge10": lambda d: d["anios_formal"] >= 10,
    }
    for _, fila in tabla.iterrows():
        f = DENOMS[fila["denominador"]]
        sub_all = pooled[f(pooled)]
        assert len(sub_all) == fila["n_agentes_pooled"], (
            f"{fila['denominador']}: n pooled {len(sub_all):,} != "
            f"{fila['n_agentes_pooled']:,}"
        )
        for sem in semillas:
            d = pooled[pooled["semilla"] == sem]
            masa = round(100 * (d[f(d)]["tasa_reemplazo"] == 0).mean(), 2)
            pub = fila[f"semilla_{sem}"]
            assert masa == pub, (
                f"{fila['denominador']} semilla {sem}: {masa} != {pub}"
            )
    print("      masa en cero por semilla y denominador: IDÉNTICA a "
          "tabla_maestra_masa_cero.csv (10/10 celdas)")

    OUT_DIR.mkdir(exist_ok=True)
    pooled.to_csv(SALIDA, index=False, compression="gzip")
    mb = SALIDA.stat().st_size / 1e6
    print(f"OK → {SALIDA.relative_to(REPO)} ({len(pooled):,} filas, "
          f"{mb:.1f} MB, {time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
