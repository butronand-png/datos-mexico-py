# REF — Estados Financieros del Fondo de Pensiones para el Bienestar, 2T-2025
### Extracción verificada 2026-07-18 · Fuente primaria: fpbienestar.org.mx/d/Estadosfinancieros2T2025.pdf (Banxico fiduciario, NIF B-16)
### Insumo para SPEC_fondo_fpb_diferimiento.md — todas las cifras en millones de pesos (mdp), nominales

## Estado de Situación Financiera (30-jun-2025 vs 31-dic-2024)

| Concepto | Jun-2025 | Dic-2024 |
|---|---|---|
| Disponibilidades (depósitos Banxico + intereses por cobrar) | 3,485 | 8,820 |
| Inversiones en instrumentos financieros negociables | 49,625 | 36,961 |
| **Total activo** | **53,110** | **45,781** |
| Total pasivo | 5 | 219 |
| **Patrimonio contable** | **53,105** | **45,562** |

Composición de inversiones (jun-2025): gubernamentales 48,264 + corporativos 1,361 = 49,625.

## Nota 7 — Reserva para devoluciones (jun-2025)

| Instituto | Reserva |
|---|---|
| IMSS | 11,746 |
| INFONAVIT | 4,284 |
| ISSSTE | 1,386 |
| **Total reserva** | **17,416** |

**Patrimonio no reservado = 53,105 − 17,416 = 35,689 mdp** ← [I] coincide con el patrimonio inicial ~35,000 del estudio Actuarius: usaron el neto de reserva.

## Estado de Actividades (ene–jun 2025)

| Concepto | Acumulado jun-2025 |
|---|---|
| Rendimiento de depósitos | 267 |
| Resultado de inversiones (incluye valuación a mercado) | 3,543 |
| **Total ingresos financieros** | **3,810** |
| Honorarios fiduciarios y gastos de operación | 21 |
| Cambio neto en patrimonio | 3,789 |
| Aportaciones de patrimonio netas de devoluciones (periodo) | 5,001 |

## Estado de Flujos de Efectivo (ene–jun 2025) — calibra I_t y D_t

| Flujo | Semestre | Anualizado [I] |
|---|---|---|
| Aportaciones en efectivo (entradas al fondo) | 3,113 | ~6,200 |
| Devoluciones y pagos por complemento (salidas) | (1,406) | ~(2,800) |
| Intereses cobrados | 1,237 | — |
| Honorarios y gastos de operación | (27) | ~(54) |

Nota: "Devoluciones y pagos por complemento" agrupa ambos egresos; el complemento puro fue $289.61 mdp acumulado a cierre 2025 (CONSAR) ⇒ el grueso del flujo (~95%) son devoluciones.

## Nota 1 — Confirmaciones legales (fuente primaria)

1. Fideicomiso creado por Decreto DOF 01-may-2024; contrato constitutivo 13-jun-2024; SHCP fideicomitente, Banxico fiduciario.
2. Población objetivo: 65 años cumplidos, cotización iniciada bajo LSS vigente desde 1-jul-1997 (Ley 97) **o régimen de cuentas individuales ISSSTE**.
3. Elegibilidad por monto: pensión igual o menor a $16,777.68 (salario promedio IMSS 2023 actualizado por inflación estimada 2024; el tope se actualiza cada año).
4. **Regla del complemento: "el monto de su pensión más el complemento sea igual a su ÚLTIMO SALARIO, hasta por el total descrito"** — piso = último salario, topado. Confirma la corrección de F2/§5.1 del spec.
5. Los recursos del patrimonio son imprescriptibles e inembargables; la reserva garantiza la atención de solicitudes de devolución y es el monto mínimo de patrimonio contable; su suficiencia se determina cada dos años por los Institutos.

## Gastos de operación observados
21 mdp en el semestre (~42-54 mdp/año) — vs. 53.1 mdp/año del supuesto de Actuarius: consistente [V].
