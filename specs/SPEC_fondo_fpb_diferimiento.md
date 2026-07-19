# SPEC v2 — Balance del Fondo de Pensiones para el Bienestar con diferimiento endógeno
### Módulo fiscal-actuarial (Sección 8) · Datos México · Paper Amafore 2026

> **Para Claude Code (Fable 5).** Documento autocontenido. Objetivo: producir con nuestro pipeline público las cifras análogas al estudio actuarial de Actuarius (dic. 2025) — **año de suficiencia del fondo** y **balance actuarial en valor presente** — como resultado original de Datos México, no como cita. Rutas y líneas verificadas contra la rama `feat/insumos-seccion7` el 2026-07-18. Cifras externas verificadas contra las fuentes de la §2.
>
> Etiquetas: **[V]** verificado con fuente · **[I]** inferido · **[S]** supuesto.

---

## 0. Reglas de trabajo (no negociables)

1. **Rama nueva** `feat/fondo-fpb-diferimiento` a partir de `feat/insumos-seccion7`. No tocar `analisis/matrices/` (congelado para Sección 7).
2. **No-regresión bit a bit**: con los flags nuevos apagados (default), `simular()` produce resultados **idénticos** a los actuales con la misma semilla (test §8.1). Las Secciones 6 y 7 ya están escritas sobre esos números.
3. Todo parámetro no verificado se marca `⚠️ SUPUESTO PROVISIONAL` con comentario y entrada en bitácora (convención de `motor/reglas_sar.py`).
4. **Ruff**: nombres descriptivos en firmas públicas; variables matemáticas cortas solo en scope local (el CI ya falló por esto).
5. Unidades: **pesos reales de 2025** (convención del motor; coincide con Actuarius → comparabilidad directa). El módulo del fondo trabaja en **mdp** (millones de pesos).

---

## 1. Inventario del motor (verificado 2026-07-18)

| Pieza | Dónde | Estado |
|---|---|---|
| Complemento FPB por agente | `motor/motor.py` L441-447; columnas `requiere_FPB`, `complemento_FPB_anual` | ✅ |
| Gasto FPB anual con supervivencia (`costo_FPB_total_mm`, `% PIB`) | `motor/motor.py` L513-531 | ✅ |
| Mortalidad EMSSA-09 (0–109, por sexo), activos y retirados en proyección | `motor/data/cnsf_emssa09_mortalidad.csv`; `motor/motor.py` L470-478 | ✅ |
| Renta vitalicia `factor_anualidad` (ä_x anual anticipada) cacheada por (sexo, edad) | `motor/reglas_sar.py`; `motor/motor.py` L285-291 | ✅ |
| Tope FPB proyectado (anclas 2024/2026) | `motor/reglas_sar.py::tope_fpb_mensual` | ✅ pero ver flag §3.2 |
| Edad de retiro como override **global** (`PoliticaSAR.edad_retiro`) | `motor/reglas_sar.py` | ✅ (no por agente) |
| Horizonte 1997→2070, pesos reales 2025, corrida paper 100k × 5 semillas | `motor/config.yaml`; `analisis/matrices/corrida_final_paper.py` | ✅ |
| **Decisión de diferimiento 60 vs 65 por agente** | — | ❌ (retiro determinista a 65, L419) |
| **Recursión del fondo (patrimonio, suficiencia, balance VP)** | — | ❌ |
| **Stock de beneficiarios 2024-2025** | — | ❌ excluido por diseño (L166-168) |
| **Último salario formal por agente** | — | ❌ solo `suma_sal_formal` (L416) |

---

## 2. Fuentes verificadas (2026-07-18) — citar estas URLs en código y paper

| ID | Dato | Fuente / URL |
|---|---|---|
| F1 | ~7,000 beneficiarios jul-2024→may-2026; tope 2026 = $17,885.85/mes | IMSS (comunicado oficial): `gob.mx/imss/prensa/fondo-de-pensiones-para-el-bienestar-politica-publica-que-beneficia-a-pensionados-con-un-retiro-digno` |
| F2 | Elegibilidad: Ley 97 (cotizar desde 1-jul-1997), **65+ exclusivamente modalidad Vejez**, semanas requeridas (875 en 2026 — coincide con `semanas_requeridas(2026)` del motor ✓), resolución desde 2-may-2024, pensión inferior al **salario promedio del último año cotizado** | IMSS, misma URL |
| F3 | Complementos pagados a cierre 2025: **$289.61 mdp**; devoluciones acumuladas: **$4,458 mdp** | Cifras oficiales CONSAR vía prensa: `es-us.noticias.yahoo.com/puedo-recuperar-afore-fondo-pensiones-170000566.html` |
| F4 | Tope vigente $17,364.00 = salario promedio IMSS 2025; actualización cada 1-ene por inflación estimada | CONSAR: `gob.mx/consar/articulos/fondo-de-pensiones-para-el-bienestar-394538` |
| F5 | Mecánica del tope (fuente primaria): $16,777.68 (2024) = salario promedio 2023 **actualizado por inflación estimada**; actualización anual por inflación | FPB oficial: `fpbienestar.org.mx/s/que_es.html` |
| F6 | Patrimonio del fideicomiso: **46,719 mdp** (Banxico, feb-2025) | `elcontribuyente.mx/2025/04/en-que-va-el-fondo-de-pensiones-para-el-bienestar-devoluciones-superan-los-1400-millones/` |
| F7 | Patrimonio: **47,400 mdp** (may-2025); saldo >46,900 mdp (SHCP, 2026) | `sociedad-noticias.com/2026/05/24/explican-funcionamiento-del-fondo-de-pensiones-para-el-bienestar/` y `aregional.com/politica/el-impacto-del-fondo-de-pensiones-para-el-bienestar-en-los-bolsillos-de-2026/` |
| F8 | CIEP (citable académico): complemento iguala el **último salario** hasta el tope; FPB = 0.1% de pensionados; pensiones = 23.5% del gasto público y 6% del PIB (2025) | `ciep.mx/fondo-de-pensiones-para-el-bienestar/` |
| F9 | **Estados financieros oficiales del fideicomiso 2T-2025** — ✅ RESUELTO: cifras extraídas 2026-07-18 y disponibles en `REF_estados_financieros_FPB_2T2025.md` (entregar junto a este spec). Clave [V]: patrimonio contable jun-2025 = **53,105 mdp**; reserva devoluciones = **17,416 mdp** (IMSS 11,746 + INFONAVIT 4,284 + ISSSTE 1,386); **no reservado = 35,689 mdp** (≈ el R_0 de Actuarius [I]); flujos ene-jun 2025: aportaciones 3,113, devoluciones+complementos (1,406); Nota 1 confirma piso = último salario | `fpbienestar.org.mx/d/Estadosfinancieros2T2025.pdf` |

---

## 3. Flags de auditoría del motor (corregir/documentar en esta rama)

### 3.1 Piso del complemento
[V, F2/F8] El piso legal es el **salario del último año cotizado** (topado por el promedio IMSS nacional). El motor usa promedio de carrera (L428-441) — con perfiles crecientes **subestima** el complemento. Se corrige en §5.1.

### 3.2 Tope FPB: comentario contradicho por fuente primaria
[V, F4/F5] El tope se actualiza **anualmente por inflación estimada** ⇒ en pesos reales es ≈ constante. El comentario de `reglas_sar.py` ("NO se indexa a INPC... ~1.7% anual, pierde valor real") está **contradicho**. Además [I]: la ancla `tope_mensual_2026: 17364.00` de config es en realidad el tope **2025** (salario promedio 2025); el tope 2026 oficial es **17,885.85** (F1; +3.0% ≈ inflación estimada). Acción: re-etiquetar anclas (`tope_mensual_2025: 17364.00`, `tope_mensual_2026: 17885.85`), corregir la proyección a **tope real constante en pesos 2025** (deflactar las anclas nominales a pesos 2025 con INPC — serie en `motor/data/inpc_mensual.csv`), actualizar comentario y bitácora. Conservar la regla anterior tras flag para no-regresión.

### 3.3 Población del stock pre-2026
[V, F1/F3] El stock real es ínfimo (~7,000 personas; $289.61 mdp acumulados) porque la generación Ley 97 apenas alcanza los 65. La exclusión original casi no sesgaba, pero se incluye por rigor (§5.2) y el dato observado se usa como sanity check (§8.5).

---

## 4. F1 — Decisión de diferimiento endógena (cirugía en `motor/motor.py`)

### 4.1 Diseño

Nodo de decisión **una sola vez, al cumplir 60**, activo solo en proyección (`anio > anio_val`) y con flag encendido. **Punto de inserción: inmediatamente ANTES del bloque de retiro existente (L419)**, evaluando `edad == 60`:

```
Si vivo, no retirado, edad[j] == 60 y semanas[j] >= politica.semanas_requeridas(anio):
    b60 = saldo[j] / (12 · a_retiro(sexo[j], 60))
    saldo_proy_65 = saldo[j] · (1 + r_esperado)^5        # sin aportaciones — cota inferior [S]
    b65_esperada = saldo_proy_65 / (12 · a_retiro(sexo[j], 65))
    difiere[j] según la regla activa (§4.2)
    si NO difiere → retiro inmediato a 60:
        pension = b60 (o pg_mensual si b60 < pg_mensual, con requiere_pg=True)  # [S] PG plana provisional
        requiere_FPB[j] = False        # [V, F2] cesantía excluye el complemento — es ley
        via_de_pension = "cesantia_60"; edad_al_retiro = 60
    si difiere → sigue en el loop (cotiza/transita normal) y se retira a 65 con la lógica existente
```

**Requisitos de implementación:**

- **Factorizar el bloque de retiro existente** (L425-465) como función interna `_retirar_agente(j, edad_retiro, permite_fpb)` y llamarla desde ambos puntos (60 y 65). No duplicar código: el retiro a 60 debe alimentar `salida_retiro` para que la conciliación contable global (L481-489) siga cerrando.
- `a_retiro(sexo, 60)` ya funciona — el cache acepta cualquier edad [V].
- Quien no cumple semanas a los 60 **no tiene decisión** y sigue hasta 65 (lógica intacta). ⚠️ [S] declarar: quien cumple semanas a los 61–64 tampoco decide → sesgo pro-diferimiento; documentar en bitácora.
- Quien difiere y muere entre 60 y 65: mortalidad existente lo maneja (saldo sale como herencia, L474-478). Registrar `murio_difiriendo` — es el costo de esperar y un resultado reportable.
- `r_esperado` = `economia.rendimiento_real_anual` (4%) [S]. Ex-ante: NO usar el r histórico realizado.

### 4.2 Reglas de decisión — implementar AMBAS

1. **`"umbral"`** (default de reporte, réplica Actuarius): `difiere ⟺ b65_esperada >= umbral · b60`, umbral parametrizable (default 2.0) [S adoptado de Actuarius].
2. **`"vpn"`** (regla secundaria, requerida): difiere si el valor actuarial de esperar supera el de cobrar ya, con supervivencia EMSSA y la tasa técnica de config:

   VPN_esperar = b65_esperada · ä(65) · v^5 · 5p60   vs   VPN_ya = b60 · ä(60)

   con v = 1/(1+tasa_tecnica) y 5p60 de la tabla del sexo del agente. Reportar la tasa de diferimiento bajo ambas reglas — la divergencia entre ellas es en sí un resultado.

### 4.3 Config nueva

```yaml
diferimiento:
  activo: false            # default OFF — no-regresión bit a bit
  regla: "umbral"          # "umbral" | "vpn"
  umbral: 2.0              # b65 >= umbral·b60 [S, Actuarius]
  tasa_forzada: null       # si es 0.0-1.0: ignora la regla, sortea difiere~Bernoulli(p) — para F4
```

### 4.4 Salidas nuevas

- Columnas por agente: `via_de_pension` {vejez_65, cesantia_60, negativa, sin_retiro} (unificar con la función homónima de `analisis/matrices/dump_nivel_agente.py` L61), `b60_hipotetica`, `b65_esperada`, `difirio`, `murio_difiriendo`.
- **Tasa de diferimiento endógena** (media ± IC95 entre semillas; patrón t de Student de `corrida_final_paper.py` L111-115) — el número contra el 40% de Actuarius. Desagregada por sexo × escolaridad × decil de densidad: granularidad que Actuarius (3 estratos fijos) no tiene. Es contribución nuestra.

---

## 5. F2 — Gasto del fondo corregido

### 5.1 Piso legal
Tracking nuevo en el loop: `ultimo_sal_formal[j] = w_cot[j]` cuando `formal_imss[j]` (junto a L416). Al retiro por vejez a 65: `piso = min(ultimo_sal_formal[j], tope_fpb)` [V, F2/F8]. Config: `fpb.definicion_piso: "ultimo_anio"` (default con diferimiento activo) | `"promedio_carrera"` (regla actual, retenida para robustez y no-regresión). [I] Impacto esperado: piso ↑ ⇒ complementos ↑ ⇒ G_t ↑. Reportar ambas en F4.

### 5.2 Stock inicial 2024-2025 (anclaje observado)
Cola exógena en `motor/fondo_fpb.py` (NO en el loop):

```
G_t_stock = gasto_anual_stock_2025 · S(t),   S(t) = 0.5·tp66_H + 0.5·tp66_M  (EMSSA ya cargada)
```

`gasto_anual_stock_2025` [S]: 193 mdp/año (289.61 mdp acumulados en ~18 meses, F3). Config: `fpb_fondo.stock_inicial.{gasto_anual_mdp: 193, edad_cohorte: 66}`.

---

## 6. F3 — Recursión del fondo (`motor/fondo_fpb.py`, módulo nuevo)

Post-proceso puro sobre el DataFrame `anual` de `simular()`. Sin tocar el core.

R_{t+1} = (1 + r_fpb)·R_t + I_t − D_t − G_t,   t = 2026…2070   (rendimiento sobre saldo inicial del año [S])

**Dos especificaciones coherentes de la recursión — implementar AMBAS (evitan doble conteo de la reserva):**

| | **Escenario A (bruto)** — reporte principal | **Escenario B (neto)** — comparable Actuarius |
|---|---|---|
| R_0 | **53_105 mdp** (patrimonio contable jun-2025 [V, F9]; sensibilidad con extrapolación a cierre 2025 ~60_000 [I]) | **35_689 mdp** (patrimonio no reservado [V, F9] = 53,105 − 17,416) |
| D_t (devoluciones) | **2_800 mdp/año** [V, F9: flujo obs. 1,406 en 6m], decaimiento [S] `factor_decaimiento: 0.95` (la fuente — cuentas 70+/75+ no reclamadas — se agota) | **0** — la reserva de 17,416 ya pre-fondea las devoluciones; restarlas de nuevo sería doble conteo |
| I_t (aportaciones de cuentas inactivas) | **6_200 mdp/año** [V, F9: flujo obs. 3,113 en 6m], mismo decaimiento [S] | I_t **neto** = 3_400 mdp/año [I: 6,200 − 2,800], mismo decaimiento |
| Gastos operativos | 54 mdp/año [V, F9: 27 en 6m — consistente con 53.1 de Actuarius] | igual |
| r_fpb | 0.042 real [S, Actuarius/Banxico] | igual |
| G_t | `costo_FPB_total_mm` (media entre semillas) + G_t_stock | igual |

⚠️ Los flujos de F9 son nominales 2025 = pesos reales 2025 en el año base [V]; el decaimiento se aplica en términos reales [S].

Funciones puras (testeables):
1. `anio_suficiencia(trayectoria) -> int | None` — primer año con R_t < 0; None si no se agota a 2070.
2. `balance_vp(trayectoria, r) -> float` — B = R_0 + Σ (I_t − D_t − G_t)/(1+r)^(t−2025), truncado a 2070.
3. `trayectoria_fondo(...) -> pd.DataFrame` — `anio, ingresos_mdp, devoluciones_mdp, gasto_fpb_mdp, rendimiento_mdp, patrimonio_mdp`.
4. CSV en `analisis/fondo/` + figura (patrón `motor/figuras.py`): patrimonio vs. año, marcando T* propio y el 2042 de Actuarius como referencia.

```yaml
fpb_fondo:
  rendimiento_real: 0.042             # PROVISIONAL [S, Actuarius/Banxico]
  gastos_operativos_mdp: 54           # [V, F9] 27 mdp en 6m
  factor_decaimiento_flujos: 0.95     # PROVISIONAL [S] — la fuente (cuentas 70+/75+) se agota
  escenario_a:                        # bruto — reporte principal
    patrimonio_inicial_mdp: 53105     # [V, F9] patrimonio contable jun-2025
    ingresos_anuales_mdp: 6200        # [V, F9] flujo observado anualizado
    devoluciones_anuales_mdp: 2800    # [V, F9] flujo observado anualizado
  escenario_b:                        # neto de reserva — comparable Actuarius
    patrimonio_inicial_mdp: 35689     # [V, F9] 53,105 - 17,416
    ingresos_anuales_mdp: 3400        # [I] neto de devoluciones
    devoluciones_anuales_mdp: 0       # reserva pre-fondeada — no doble contar
  stock_inicial:
    gasto_anual_mdp: 193              # PROVISIONAL — ancla 289.61 acumulado [V, F3]
    edad_cohorte: 66
```

**Unidades**: `costo_FPB_total_mm` ya está en millones (L530 divide entre 1e6). Todo el módulo en mdp reales 2025. Test dedicado §8.4.

---

## 7. F4 — Sensibilidad (script en `analisis/fondo/`)

1. **Tasa de diferimiento** (eje #1 de Actuarius): `tasa_forzada` ∈ {0.10, 0.20, 0.40, 0.60, 0.80, 1.00} + endógena (ambas reglas). Reportar T* y B por punto vs. su tabla (10%: −935,038 mdp, 2048 / 100%: −6,766,133 mdp, 2036).
2. **r_fpb** ∈ {0.032, 0.042, 0.062}.
3. **Definición del piso**: `ultimo_anio` vs `promedio_carrera` (eje propio).
4. **I_t = 0**: demostrar que mueve B en <1%.
5. **R_0** ∈ {35_689 (B, neto [V]), 53_105 (A, jun-25 [V]), 60_000 (A, cierre 2025 extrapolado [I])}.
6. **Decaimiento de flujos** ∈ {0.90, 0.95, 1.00} — solo escenario A.

Entregable: tabla maestra CSV + markdown con {nuestro valor, Actuarius, delta} donde exista comparable.

---

## 8. Tests y criterios de aceptación

1. **No-regresión bit a bit** (bloqueante): flags apagados ⇒ `simular(cfg, semilla=20260701)` produce `agentes` y `anual` idénticos (`pd.testing.assert_frame_equal`) a la rama base. Si falla, no hay merge.
2. **Nodo de decisión**: agente sintético controlado; difiere ⟺ regla activa lo dicta; retiro a 60 ⇒ `requiere_FPB=False`. Ambas reglas testeadas.
3. **Recursión analítica**: con I=D=G=0, R_t = R_0(1+r)^t exacto; con G constante y r=0, T* cerrado.
4. **Unidades**: G_2026 del módulo == `costo_FPB_total_mm` 2026 del motor + stock (tol 1e-6).
5. **Sanity observado**: G_2026 simulado vs ~193 mdp/año observados [V, F3] — se espera simulado > observado (acceso pleno vs rampa administrativa); si >100×, investigar antes de reportar [I].
6. **Contabilidad**: checks `ContabilidadError` verdes con diferimiento activo (retiro a 60 alimenta `salida_retiro`).
7. Ruff + suite completa (5 checks CI, Python 3.10–3.13).

---

## 9. Orden de ejecución

1. Rama + test de no-regresión (rojo intencional hasta el final).
2. Flags de auditoría §3.2 (tope: re-etiquetar anclas, tope real constante, bitácora).
3. F1: factorizar retiro → nodo de diferimiento → ambas reglas → columnas nuevas.
4. F2: piso `ultimo_anio` + stock exógeno.
5. F3: `motor/fondo_fpb.py` + tests analíticos.
6. Corrida 100k × 5 semillas con `diferimiento.activo=true` (patrón `corrida_final_paper.py`).
7. F4: barridos + tabla comparativa.
8. No-regresión en verde + PR contra `feat/insumos-seccion7` con checklist de este spec.

## 10. Resultados que el paper espera

1. **Tasa de diferimiento endógena** (ambas reglas, con IC) vs. 40% Actuarius — desagregada por perfil (ellos no pueden).
2. **Año de suficiencia T*** propio (vs. 2042).
3. **Balance actuarial VP 2026–2070** propio (comparable: su cobertura a 50 años, −2,683,873 mdp — NO su base a 100 años).
4. Jerarquía de sensibilidad propia (¿beneficiarios efectivos dominan también aquí?).
5. Punto ciego #7 cerrado con fundamento legal [V, F2]: de acceso 100% implícito a decisión endógena.

## 11. Benchmarks Actuarius (tabla comparativa final)

| Métrica | Actuarius [V, PDF dic-2025] |
|---|---|
| Escenario base | 40% espera (b65 ≥ 2·b60), 100 años |
| Año de suficiencia | 2042 |
| Balance VP (100 años) | −3,520,904 mdp |
| Cobertura 50 años (nuestro comparable) | −2,683,873 mdp, suficiencia 2042 |
| Sensibilidad espera 100% / 10% | −6,766,133 mdp, 2036 / −935,038 mdp, 2048 |
| Rendimiento del fondo | 4.2% real |
| Patrimonio inicial | ~35,000 mdp — [V, F9] resuelto: es el patrimonio NO reservado (53,105 − 17,416 = 35,689 al 2T-2025). Nuestro reporte: escenario B lo replica; escenario A usa el bruto con devoluciones explícitas |
| Ingresos netos VP | 20,507 mdp (0.57% del gasto) |
