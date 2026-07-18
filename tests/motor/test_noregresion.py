"""No-regresión bit a bit — SPEC fondo FPB §8.1 (bloqueante para merge).

Con los flags nuevos APAGADOS (default de config: diferimiento.activo=false,
regla de tope legada, piso promedio_carrera), `simular()` debe producir
`agentes` y `anual` idénticos a la línea base capturada en la rama base
(feat/insumos-seccion7, 2026-07-18) con la misma semilla (20260701).

La referencia vive en fixtures/referencia_noregresion_*.csv.gz, generada
con genera_referencia_noregresion.py ANTES de tocar el motor. Ambos lados
se roundtripean por la MISMA serialización CSV (float %.17g — exacta para
float64), de modo que la comparación no depende de dtypes post-lectura.

Como el fingerprint de test_motor.py, la línea base se calculó en darwin;
en CI (flota heterogénea de CPUs) el mismo commit produce floats distintos
por dispatch SIMD de numpy, así que el contrato exacto no es portable.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _roundtrip(df: pd.DataFrame) -> pd.DataFrame:
    buf = io.StringIO()
    df.to_csv(buf, index=False, float_format="%.17g")
    buf.seek(0)
    return pd.read_csv(buf)


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="línea base calculada en darwin; floats no portables entre CPUs",
)
@pytest.mark.parametrize("frame", ["agentes", "anual"])
def test_noregresion_flags_apagados(resultado_homogeneo, frame):
    """agentes y anual idénticos a la rama base con flags default."""
    ref = pd.read_csv(FIXTURES / f"referencia_noregresion_{frame}.csv.gz")
    actual = _roundtrip(getattr(resultado_homogeneo, frame))
    pd.testing.assert_frame_equal(actual, ref, check_exact=True)
