# Comparativa Datos México vs Actuarius — fondo FPB

Corrida: motor heterogéneo, 100,000 agentes x 5 semillas, diferimiento endógeno, piso último salario, tope real constante. Commit `a92b8aa`. Unidades: mdp reales 2025.

**Advertencia de horizonte**: nuestro balance trunca en 2070 (45 años); el comparable de Actuarius es su cobertura a 50 años, NO su base a 100. El escenario B (patrimonio neto de reserva, R₀ = 35,689) replica su especificación; el A (bruto, R₀ = 53,105, devoluciones explícitas) es nuestro reporte principal.

| Métrica | Datos México | Actuarius | Delta / nota |
|---|---|---|---|
| Tasa de diferimiento endógena | umbral: 0.0% ± 0.0; vpn: 24.4% ± 0.4 | 40% (supuesto, b65 ≥ 2·b60) | la regla umbral con saldo sin aportaciones 60→65 NUNCA duplica b60 (cota inferior [S]); bajo vpn difieren las mujeres (ventaja de supervivencia) |
| T* y balance VP, escenario A (bruto) | 2038 / -149,423 | — | endógeno umbral |
| T* y balance VP, escenario B (neto) | 2035 / -166,839 | 2042 / -2,683,873 (50 años) | endógeno umbral |
| Espera forzada_0.10 (esc. B) | 2034 / -336,367 | 2048.0 / -935,038 | Δ balance 598,671 |
| Espera forzada_0.40 (esc. B) | 2034 / -847,992 | 2042.0 / -2,683,873 | Δ balance 1,835,881 |
| Espera forzada_1.00 (esc. B) | 2033 / -1,858,820 | 2036.0 / -6,766,133 | Δ balance 4,907,313 |
| Rendimiento del fondo | 4.2% real (± en eje r_fpb) | 4.2% real | mismo supuesto [S] |
| Patrimonio inicial | A: 53,105 [V] / B: 35,689 [V] | ~35,000 | B replica su neto de reserva (53,105 − 17,416, Nota 7 EF 2T-2025) |
| Sensibilidad a I_t = 0 | |ΔB| = 44.40% del balance base (A); |ΔB| = 21.81% del balance base (B) | ingresos netos VP = 0.57% del gasto | ⚠️ el spec §7.4 esperaba <1%: NO se cumple — nuestro balance es ~18x menor en magnitud que el de Actuarius, así que el mismo I_t deja de ser despreciable. Hallazgo, no error |

## Jerarquía de sensibilidad (rango del balance VP por eje, esc. A)

| Eje | B mínimo | B máximo | Rango |
|---|---|---|---|
| decaimiento_flujos | -161,891 | -117,561 | 44,330 |
| definicion_piso | -149,423 | -113,139 | 36,284 |
| ingresos_cero | -215,762 | -215,762 | 0 |
| patrimonio_inicial | -149,423 | -142,528 | 6,895 |
| r_fpb | -200,652 | -81,657 | 118,995 |
| tasa_diferimiento | -1,841,404 | -149,423 | 1,691,981 |
