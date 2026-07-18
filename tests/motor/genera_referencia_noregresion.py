"""Genera la línea base del test de no-regresión (SPEC fondo FPB §8.1).

Corre la simulación canónica homogénea (flags nuevos apagados, semilla de
config) y persiste `agentes` y `anual` serializados con float %.17g —
la misma precisión del fingerprint de test_motor.py, suficiente para
roundtrip exacto de float64.

DEBE ejecutarse UNA sola vez, sobre el código de la rama base
(feat/insumos-seccion7), ANTES de cualquier cambio al motor. El test
compara contra estos archivos con pd.testing.assert_frame_equal.

Uso: .venv/bin/python tests/motor/genera_referencia_noregresion.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from motor.datos import (
    cargar_conapo,
    cargar_indice_salarial_real,
    cargar_mortalidad,
    cargar_rendimientos_reales,
    participaciones_enoe,
    qx_por_sexo,
)
from motor.motor import simular

DESTINO = REPO / "tests" / "motor" / "fixtures"


def main() -> int:
    DESTINO.mkdir(exist_ok=True)
    cfg = yaml.safe_load((REPO / "motor" / "config.yaml").read_text())
    r = simular(
        cfg,
        cargar_conapo(),
        qx_por_sexo(cargar_mortalidad()),
        participaciones_enoe(usar_api=False),
        escenario="base",
        semilla=cfg["semilla"],
        r_historico=cargar_rendimientos_reales(),
        indice_salarial=cargar_indice_salarial_real(),
        matriz_heterogenea=False,
    )
    for nombre, df in [("agentes", r.agentes), ("anual", r.anual)]:
        ruta = DESTINO / f"referencia_noregresion_{nombre}.csv.gz"
        df.to_csv(ruta, index=False, float_format="%.17g", compression="gzip")
        print(f"{ruta.relative_to(REPO)}: {len(df)} filas, {len(df.columns)} cols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
