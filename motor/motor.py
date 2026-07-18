"""Núcleo del motor de microsimulación actuarial (walking skeleton, §4).

Loop de acumulación en tiempo discreto anual:

    S_{t+1} = (S_t + A_t - C_t) * (1 + r_t)

con identidad contable verificada en CADA periodo (aborta si falla):

    ΔS = A + R - C          (por agente, en el paso de acumulación)
    ΔS_total = A + R - C - salidas   (conciliación global de flujos)

Diseño skeleton (cada bloque en su versión más cruda defendible):
- Trayectorias laborales: Markov homogéneo de 4 estados, calibrado a las
  participaciones ENOE 2025T1.       ⚠️ PROVISIONAL (Prioridad 1)
- Salarios: lognormal persistente + perfil determinístico de edad.
                                     ⚠️ PROVISIONAL (Prioridad 2)
- Rendimientos: r real constante.    ⚠️ PROVISIONAL (Prioridad 3)
- Mortalidad: tabla CNSF EMSSA-09 estática.  ⚠️ PROVISIONAL (Prioridad 4)
- Reglas SAR: exactas desde el inicio (reglas_sar.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from motor import reglas_sar
from motor.reglas_sar import factor_anualidad

ESTADOS = ["formal", "informal", "desempleado", "fuera"]
FORMAL, INFORMAL, DESEMPLEADO, FUERA = 0, 1, 2, 3

class ContabilidadError(RuntimeError):
    """La identidad ΔS = A + R - C no cuadró: hay una fuga en la tubería."""


def matriz_markov(part: dict[str, float], cfg: dict, delta_densidad_pp: float = 0.0) -> np.ndarray:
    """Matriz de transición homogénea 4x4 calibrada a participaciones ENOE.

    ⚠️ SUPUESTO PROVISIONAL: diagonal hand-coded (persistencias de config);
    masa fuera de la diagonal repartida proporcional a las participaciones
    objetivo de los demás estados. Sustituir por estimación del panel ENOE
    (Emiliano, Prioridad 1).
    """
    shares = np.array(
        [part["formal"], part["informal"], part["desempleado"], part["fuera"]]
    )
    diag = np.array(
        [
            cfg["mercado_laboral"]["persistencia_formal"],
            cfg["mercado_laboral"]["persistencia_informal"],
            cfg["mercado_laboral"]["persistencia_desempleo"],
            cfg["mercado_laboral"]["persistencia_fuera"],
        ]
    )
    M = np.zeros((4, 4))
    for i in range(4):
        M[i, i] = diag[i]
        otros = [j for j in range(4) if j != i]
        w = shares[otros] / shares[otros].sum()
        M[i, otros] = (1 - diag[i]) * w
    # Escenario: +/- delta pp de probabilidad de transitar a formal (§6)
    if delta_densidad_pp != 0.0:
        d = delta_densidad_pp / 100.0
        for i in range(4):
            objetivo = min(max(M[i, FORMAL] + d, 0.001), 0.999)
            ajuste = objetivo - M[i, FORMAL]
            otros = [j for j in range(4) if j != FORMAL]
            M[i, FORMAL] = objetivo
            M[i, otros] -= ajuste * M[i, otros] / M[i, otros].sum()
        M = np.clip(M, 0.0, 1.0)
        M /= M.sum(axis=1, keepdims=True)
    return M


def estacionaria(M: np.ndarray) -> np.ndarray:
    vals, vecs = np.linalg.eig(M.T)
    v = np.real(vecs[:, np.argmax(np.real(vals))])
    return v / v.sum()


@dataclass
class ResultadoSimulacion:
    agentes: pd.DataFrame
    anual: pd.DataFrame
    validacion: dict
    ledger: pd.DataFrame = field(default_factory=pd.DataFrame)


def _perfil_edad(edades: np.ndarray, cfg: dict) -> np.ndarray:
    g = cfg["economia"]["crecimiento_salarial_edad"]
    c = cfg["economia"]["curvatura_perfil_edad"]
    e = edades - 25.0
    return g * e - c * e**2


def simular(
    cfg: dict,
    conapo: pd.DataFrame,
    qx: dict[str, np.ndarray],
    participaciones: dict[str, float],
    escenario: str = "base",
    semilla: int | None = None,
    politica: reglas_sar.PoliticaSAR | None = None,
    r_historico: dict[int, float] | None = None,
    indice_salarial: dict[int, float] | None = None,
    matriz_heterogenea: bool = False,
    tensor_transicion: np.ndarray | None = None,
) -> ResultadoSimulacion:
    """Corre el motor end-to-end: backcast 1997-2025 + proyección 2026-2070.

    Args:
        politica: parámetros de ley con overrides opcionales (Sección 9).
            ``None`` == ley vigente; el backcast es idéntico en ambos casos.
        r_historico: rendimiento real BRUTO observado por año (serie CONSAR
            de precios de gestión deflactada con INPC, bitácora #23). En los
            años sin dato (proyección 2026+) aplica el r constante de config.
        indice_salarial: nivel salarial real por año calendario (2025=1.0,
            SBC IMSS deflactado, bitácora #24). Corrige el NIVEL transversal
            del backcast; el perfil individual edad-salario es TODO Fase 2.
            Años sin dato (2026+): 1.0 (el secular lo pone g_secular).
        matriz_heterogenea: ruta de 5 ESTADOS (Fase 2.5/Paso 3, Brecha 2).
            Si True, la transición usa las matrices ANUALES 5x5 por perfil
            (edad x sexo x escolaridad; formal_IMSS, formal_ISSSTE,
            informal, desempleado, fuera_PEA — orden de ESTADOS_ANUALES en
            analisis/matrices/carga_matrices.py), estimadas directas del
            panel ENOE 1ª↔5ª entrevista 2015-2024. El estado inicial
            (stock 2025 y entrantes) se sortea de los shares ENOE 2025T1
            partiendo formal con prop_issste_formales; el flag
            sector_issste NO se sortea (el estado gobierna el sector, la
            columna de salida se deriva del estado final). SUPUESTO
            backcast: el tensor 5x5 (promedio 2015-2024) aplica en TODO el
            horizonte 1997-2070, también hacia atrás. La ruta homogénea (4
            estados, False) queda intacta bit a bit. Limitación vigente:
            el delta de escenario (delta_densidad_pp) NO aplica a la ruta
            heterogénea (pendiente de paso dedicado).
        tensor_transicion: tensor (8, 2, 3, E, E) que sustituye al estimado
            de ENOE en la ruta heterogénea (contrafactuales Sección 7).
            Ignorado con matriz_heterogenea=False. None == sin sustitución.
    """
    if r_historico is None:
        r_historico = {}
    if indice_salarial is None:
        indice_salarial = {}
    if politica is None:
        politica = reglas_sar.PoliticaSAR()
    rng = np.random.default_rng(semilla if semilla is not None else cfg["semilla"])
    sim = cfg["simulacion"]
    n0 = sim["n_agentes"]
    anio_ini, anio_val, anio_fin = (
        sim["anio_backcast"],
        sim["anio_validacion"],
        sim["anio_fin"],
    )
    uma_mensual = cfg["economia"]["uma_diaria_2025"] * 30.4
    r_real = cfg["economia"]["rendimiento_real_anual"]
    delta_pp = cfg["escenarios"][escenario]["delta_densidad_pp"]

    M_hist = matriz_markov(participaciones, cfg, 0.0)
    M_fut = matriz_markov(participaciones, cfg, delta_pp)
    pi0 = estacionaria(M_hist)

    # ------------------------------------------------------------------
    # Población inicial: muestra de CONAPO 2025, edades 15-64.
    # ⚠️ SUPUESTO PROVISIONAL: se excluye el stock de pensionados pre-2026;
    # el costo FPB reportado es SOLO de cohortes que se retiran 2026+.
    # ------------------------------------------------------------------
    c25 = conapo[(conapo["anio"] == 2025) & conapo["edad"].between(15, 64)]
    pesos_pob = c25["poblacion"].to_numpy().astype(float)
    W = pesos_pob.sum() / n0  # personas representadas por agente
    idx = rng.choice(len(c25), size=n0, p=pesos_pob / pesos_pob.sum())
    edad_2025 = c25["edad"].to_numpy()[idx]
    sexo = np.where(c25["sexo"].to_numpy()[idx] == "H", 0, 1)

    # ------------------------------------------------------------------
    # Ruta heterogénea (Fase 2.5, 5 estados): matrices ANUALES por perfil.
    # Import perezoso desde analisis/matrices — solo se toca esta ruta con
    # el flag activo; con False el motor no importa ni carga nada extra.
    # ------------------------------------------------------------------
    tensor_P = None
    esc_idx = None
    etiquetas_estado = np.array(ESTADOS, dtype=object)
    if matriz_heterogenea:
        import sys
        from pathlib import Path

        ruta_mat = str(Path(__file__).resolve().parent.parent / "analisis" / "matrices")
        if ruta_mat not in sys.path:
            sys.path.insert(0, ruta_mat)
        from asignacion_perfiles import (
            ESCOLARIDADES,
            asigna_escolaridad_idx,
            construye_tensor,
            filas_transicion,
            marginal_escolaridad,
        )
        from carga_matrices import (
            ESTADO_A_IDX_ANUALES,
            ESTADOS_ANUALES,
            cargar_matrices_anuales,
        )

        marginal_esc = marginal_escolaridad()
        # Tensor 5x5 ANUAL (sin P^4). ⚠️ SUPUESTO backcast (decisión c):
        # el promedio 2015-2024 aplica en todo el horizonte, también
        # hacia atrás — continuidad individual sobre fidelidad de época.
        # tensor_transicion permite inyectar un tensor alternativo con la
        # misma forma (8, 2, 3, E, E) — contrafactuales de la Sección 7
        # (p. ej. swap de canal por sexo). None == tensor estimado ENOE.
        if tensor_transicion is not None:
            tensor_P = tensor_transicion
        else:
            tensor_P = construye_tensor(cargar_matrices_anuales())
        etiquetas_estado = np.array(ESTADOS_ANUALES, dtype=object)
        n_est_het = len(ESTADOS_ANUALES)
        idx_f_imss = ESTADO_A_IDX_ANUALES["formal_IMSS"]
        idx_f_issste = ESTADO_A_IDX_ANUALES["formal_ISSSTE"]
        # Distribución inicial de 5 estados (decisión b, fix punto ciego
        # pi0): shares ENOE 2025T1 con formal partido por prop_issste.
        p_issste_h = cfg["mercado_laboral"]["prop_issste_formales"]
        pi0_het = np.empty(n_est_het)
        pi0_het[idx_f_imss] = participaciones["formal"] * (1.0 - p_issste_h)
        pi0_het[idx_f_issste] = participaciones["formal"] * p_issste_h
        pi0_het[ESTADO_A_IDX_ANUALES["informal"]] = participaciones["informal"]
        pi0_het[ESTADO_A_IDX_ANUALES["desempleado"]] = participaciones["desempleado"]
        pi0_het[ESTADO_A_IDX_ANUALES["fuera_PEA"]] = participaciones["fuera"]
        pi0_het = pi0_het / pi0_het.sum()
        # Escolaridad v1: estática, muestreada de la marginal ENOE 2024T3
        # con la edad observada en 2025 (la marginal es transversal).
        esc_idx = asigna_escolaridad_idx(
            edad_2025.astype(float), sexo, rng, marginal_esc
        )

    # Entrantes 2026-2070: cohortes de 15 años según CONAPO
    entrantes = {
        a: conapo[(conapo["anio"] == a) & (conapo["edad"] == 15)]
        for a in range(2026, anio_fin + 1)
    }

    # Arrays de estado (crecen con los entrantes)
    edad = (edad_2025 - (2025 - anio_ini)).astype(float)  # edad en 1997
    n = n0
    if matriz_heterogenea:
        # 5 estados: distribución inicial ENOE (pi0_het), no la
        # estacionaria homogénea de 4. El flag sector_issste NO se
        # sortea: el estado gobierna el sector (decisión b).
        estado = rng.choice(n_est_het, size=n, p=pi0_het)
        sector_issste = np.zeros(n, dtype=bool)  # placeholder; derivado al final
    else:
        estado = rng.choice(4, size=n, p=pi0)
        sector_issste = None  # se sortea abajo (ruta homogénea intacta)
    mu = rng.normal(0.0, cfg["salarios"]["sigma_log"], size=n)
    # ⚠️ Alcance IMSS-solo (bitácora #25): flag persistente de sector.
    # Los ISSSTE se modelan (transitan, ganan salario) pero no aportan al
    # agregado RCV-IMSS ni acumulan semanas IMSS. Activable si el equipo
    # amplía el alcance a IMSS+ISSSTE (decisión PENDIENTE).
    p_issste = cfg["mercado_laboral"]["prop_issste_formales"]
    if not matriz_heterogenea:
        sector_issste = rng.random(n) < p_issste
    saldo = np.zeros(n)
    semanas = np.zeros(n)
    anios_formal = np.zeros(n)
    anios_activo = np.zeros(n)  # años desde la entrada (denominador densidad)
    suma_sal_formal = np.zeros(n)
    vivo = np.ones(n, dtype=bool)
    retirado = np.zeros(n, dtype=bool)
    pension = np.zeros(n)
    piso_fpb_i = np.zeros(n)
    anio_retiro = np.full(n, -1)
    edad_al_retiro = np.full(n, -1)
    requiere_pg = np.zeros(n, dtype=bool)
    requiere_fpb = np.zeros(n, dtype=bool)
    tasa_reemplazo = np.full(n, np.nan)
    saldo_final = np.full(n, np.nan)
    # F1 diferimiento (SPEC fondo FPB §4): estado del nodo de decisión 60
    # vs 65. Los arrays existen siempre (baratos); las columnas de salida
    # solo se emiten con diferimiento.activo=true (no-regresión §8.1).
    via_pension = np.full(n, "sin_retiro", dtype=object)
    b60_hipotetica = np.full(n, np.nan)
    b65_esperada = np.full(n, np.nan)
    difirio = np.zeros(n, dtype=bool)
    murio_difiriendo = np.zeros(n, dtype=bool)

    base_log_w = np.log(cfg["salarios"]["mediana_uma_mensual"] * uma_mensual)

    # Factores de anualidad (renta vitalicia anual anticipada, EMSSA-09),
    # cacheados por (sexo, edad de retiro) — la edad puede cambiar por reforma
    i_tec = cfg["economia"]["tasa_tecnica_anualidad"]
    cache_anualidad: dict[tuple[int, int], float] = {}

    def a_retiro(sexo_j: int, edad_ret: int) -> float:
        clave = (sexo_j, edad_ret)
        if clave not in cache_anualidad:
            tabla = qx["H"] if sexo_j == 0 else qx["M"]
            cache_anualidad[clave] = factor_anualidad(tabla, edad_ret, i_tec)
        return cache_anualidad[clave]

    pg_mensual = cfg["pension_garantizada"]["pg_mensual_2025"]
    g_secular = cfg["economia"]["crecimiento_salarial_secular_real"]
    tope_fpb_2024 = cfg["fpb"]["tope_mensual_2024"]
    # Regla legada (#22): su segundo ancla era el valor hoy re-etiquetado
    # como tope 2025 (17,364.00) — se le pasa ese mismo valor para
    # reproducir bits (auditoría #26; fallback a la clave vieja por si la
    # config del llamador aún no está re-etiquetada).
    tope_fpb_legado = cfg["fpb"].get(
        "tope_mensual_2025", cfg["fpb"].get("tope_mensual_2026")
    )
    regla_tope = cfg["fpb"].get("regla_tope", "legada")
    if regla_tope == "real_constante":
        from motor.datos import cargar_deflactor_inpc

        topes_nominales = {
            a: cfg["fpb"][f"tope_mensual_{a}"] for a in (2024, 2025, 2026)
        }
        deflactor_inpc = cargar_deflactor_inpc()
    elif regla_tope != "legada":
        raise ValueError(f"fpb.regla_tope desconocida: {regla_tope!r}")

    # F1: decisión de diferimiento 60 vs 65 (SPEC fondo FPB §4). Default
    # OFF — con el flag apagado el flujo (y el stream del rng) es idéntico
    # bit a bit al de la rama base (§8.1).
    dif_cfg = cfg.get("diferimiento") or {}
    dif_activo = bool(dif_cfg.get("activo", False))
    dif_regla = dif_cfg.get("regla", "umbral")
    dif_umbral = float(dif_cfg.get("umbral", 2.0))
    dif_tasa_forzada = dif_cfg.get("tasa_forzada")
    if dif_activo and dif_regla not in ("umbral", "vpn"):
        raise ValueError(f"diferimiento.regla desconocida: {dif_regla!r}")
    # r ex-ante de la proyección del saldo 60→65: el rendimiento esperado
    # de config, NO el histórico realizado (⚠️ SUPUESTO, SPEC §4.1).
    r_esperado = r_real

    def _retirar_agente(
        j: int,
        edad_retiro_j: int,
        anio_j: int,
        tope_fpb_j: float,
        permite_fpb: bool,
        via_con_pension: str,
    ) -> float:
        """Liquida el retiro del agente j; regresa el saldo que sale del sistema.

        Bloque de retiro factorizado (SPEC §4.1): lo llaman el retiro a la
        edad legal (permite_fpb=True, via "vejez_65") y el retiro anticipado
        por cesantía del nodo de diferimiento (permite_fpb=False — [V] la
        cesantía excluye el complemento FPB por ley, via "cesantia_60").
        La aritmética es idéntica al bloque original (no-regresión §8.1).
        """
        sal_prom = (
            suma_sal_formal[j] / anios_formal[j]
            if anios_formal[j] > 0
            else np.nan
        )
        if semanas[j] >= politica.semanas_requeridas(anio_j):
            p = saldo[j] / (12.0 * a_retiro(sexo[j], edad_retiro_j))
            if p < pg_mensual:
                # ⚠️ PROVISIONAL: PG como piso plano (el vigente es
                # tabulador edad x semanas x salario) pagada por el
                # Estado al agotarse el saldo — aquí piso directo.
                p = pg_mensual
                requiere_pg[j] = True
            piso = min(sal_prom, tope_fpb_j) if not np.isnan(sal_prom) else 0.0
            # ⚠️ PROVISIONAL: elegibilidad FPB = cumplir semanas y
            # edad 65 (ley 97); piso = salario promedio de cotización
            # con tope — confirmar reglas exactas con Fabiola/Yáñez.
            if permite_fpb and p < piso:
                requiere_fpb[j] = True
                piso_fpb_i[j] = piso
            pension[j] = p
            # pensión efectiva percibida = piso FPB si aplica el complemento
            efectiva = piso if requiere_fpb[j] else p
            tasa_reemplazo[j] = (
                efectiva / sal_prom
                if not np.isnan(sal_prom) and sal_prom > 0
                else np.nan
            )
            via_pension[j] = via_con_pension
        else:
            # negativa de pensión: entrega del saldo en una exhibición
            pension[j] = 0.0
            tasa_reemplazo[j] = 0.0 if anios_formal[j] > 0 else np.nan
            via_pension[j] = "negativa"
        saldo_final[j] = saldo[j]
        anio_retiro[j] = anio_j
        edad_al_retiro[j] = int(edad[j])
        liberado = saldo[j]
        saldo[j] = 0.0
        return liberado

    ledger_rows = []
    anual_rows = []
    validacion: dict = {}

    for anio in range(anio_ini, anio_fin + 1):
        M = M_hist if anio <= anio_val else M_fut

        # -- entrantes (proyección): agentes que cumplen 15 este año --------
        if anio > anio_val:
            ent = entrantes[anio]
            pob15 = ent["poblacion"].sum()
            n_new = round(pob15 / W)
            if n_new > 0:
                p_h = ent[ent["sexo"] == "H"]["poblacion"].sum() / pob15
                edad = np.append(edad, np.full(n_new, 15.0))
                sexo = np.append(sexo, (rng.random(n_new) > p_h).astype(int))
                if matriz_heterogenea:
                    # entrantes de 15: proxy 25-29 (mismo fallback del Paso 2)
                    esc_idx = np.append(esc_idx, asigna_escolaridad_idx(
                        np.full(n_new, 15.0), sexo[-n_new:], rng, marginal_esc
                    ))
                    # sin sorteo de flag; estado inicial de la dist. de 5
                    sector_issste = np.append(sector_issste, np.zeros(n_new, dtype=bool))
                    estado = np.append(estado, rng.choice(n_est_het, size=n_new, p=pi0_het))
                else:
                    sector_issste = np.append(sector_issste, rng.random(n_new) < p_issste)
                    estado = np.append(estado, rng.choice(4, size=n_new, p=pi0))
                mu = np.append(mu, rng.normal(0.0, cfg["salarios"]["sigma_log"], n_new))
                saldo = np.append(saldo, np.zeros(n_new))
                semanas = np.append(semanas, np.zeros(n_new))
                anios_formal = np.append(anios_formal, np.zeros(n_new))
                anios_activo = np.append(anios_activo, np.zeros(n_new))
                suma_sal_formal = np.append(suma_sal_formal, np.zeros(n_new))
                vivo = np.append(vivo, np.ones(n_new, dtype=bool))
                retirado = np.append(retirado, np.zeros(n_new, dtype=bool))
                pension = np.append(pension, np.zeros(n_new))
                piso_fpb_i = np.append(piso_fpb_i, np.zeros(n_new))
                anio_retiro = np.append(anio_retiro, np.full(n_new, -1))
                edad_al_retiro = np.append(edad_al_retiro, np.full(n_new, -1))
                requiere_pg = np.append(requiere_pg, np.zeros(n_new, dtype=bool))
                requiere_fpb = np.append(requiere_fpb, np.zeros(n_new, dtype=bool))
                tasa_reemplazo = np.append(tasa_reemplazo, np.full(n_new, np.nan))
                saldo_final = np.append(saldo_final, np.full(n_new, np.nan))
                via_pension = np.append(
                    via_pension, np.full(n_new, "sin_retiro", dtype=object)
                )
                b60_hipotetica = np.append(b60_hipotetica, np.full(n_new, np.nan))
                b65_esperada = np.append(b65_esperada, np.full(n_new, np.nan))
                difirio = np.append(difirio, np.zeros(n_new, dtype=bool))
                murio_difiriendo = np.append(
                    murio_difiriendo, np.zeros(n_new, dtype=bool)
                )
                n += n_new

        # -- parámetros de ley del año (con overrides de reforma si aplican) --
        edad_ret = politica.edad_retiro_en(anio)
        tope_salarial = politica.tope_salarial_uma_en(anio) * uma_mensual
        cs_anual = politica.cuota_social_diaria_en(anio) * 365.0
        cs_tope = politica.cuota_social_tope_uma_en(anio) * uma_mensual

        activo = vivo & ~retirado & (edad >= 15) & (edad < edad_ret)

        # -- transición laboral (solo activos en el mercado) -----------------
        if activo.any():
            u = rng.random(n)
            if matriz_heterogenea:
                # fila origen de P^(g) por agente; bin de edad recalculado
                # cada año (el perfil envejece con el agente)
                filas = filas_transicion(tensor_P, edad, sexo, esc_idx, estado)
            else:
                filas = M[estado]
            cum = np.cumsum(filas, axis=1)
            # cota superior = nº de estados de la ruta (4 u 5)
            nuevo = np.clip((u[:, None] > cum).sum(axis=1), 0, filas.shape[1] - 1)
            estado = np.where(activo, nuevo, estado)

        # -- salarios (pesos reales 2025) ------------------------------------
        # nivel_t: índice salarial real observado del año (backcast, #24);
        # g_secular: crecimiento real de calendario en proyección, compartido
        # con el tope FPB (0 en el skeleton — bitácora #22)
        nivel_t = indice_salarial.get(anio, 1.0)
        log_w = (
            base_log_w
            + mu
            + _perfil_edad(edad, cfg)
            + np.log(nivel_t)
            + g_secular * (anio - 2025)
        )
        w = np.exp(log_w)
        w_cot = np.minimum(w, tope_salarial)  # tope 25 UMA

        # formal_imss: canal que aporta al RCV-IMSS (target de validación).
        # Los formales ISSSTE quedan modelados pero fuera del target (#25).
        if matriz_heterogenea:
            # 5 estados: el estado gobierna el sector (formal_IMSS explícito)
            formal_imss = activo & (estado == idx_f_imss)
        else:
            formal = activo & (estado == FORMAL)
            formal_imss = formal & ~sector_issste

        # -- acumulación: S' = (S + A - C)(1 + r) ----------------------------
        tasa_a = politica.tasa_aportacion(anio)
        tasa_c = politica.tasa_comision(anio)
        A = np.where(formal_imss, tasa_a * w_cot * 12.0, 0.0)
        A = A + np.where(formal_imss & (w_cot <= cs_tope), cs_anual, 0.0)  # cuota social
        cuenta = vivo & ~retirado
        C = np.where(cuenta, tasa_c * saldo, 0.0)
        base = np.where(cuenta, saldo + A - C, saldo)
        # r del año: serie observada CONSAR (backcast) o constante de config
        # (proyección 2026+; el estocástico es Prioridad 3)
        r_t = r_historico.get(anio, r_real)
        R = np.where(cuenta, base * r_t, 0.0)
        saldo_nuevo = np.where(cuenta, base + R, saldo)

        # ============ CHECK CONTABLE ΔS = A + R - C (por agente) ============
        delta = saldo_nuevo[cuenta] - saldo[cuenta]
        flujo = A[cuenta] + R[cuenta] - C[cuenta]
        if not np.allclose(delta, flujo, rtol=1e-9, atol=1e-6):
            peor = np.abs(delta - flujo).max()
            raise ContabilidadError(
                f"ΔS != A + R - C en {anio} (desvío máximo {peor:.6e} pesos)"
            )
        saldo_total_pre = saldo[vivo].sum()
        saldo = saldo_nuevo

        semanas = semanas + np.where(formal_imss, 52.0, 0.0)
        anios_formal = anios_formal + formal_imss
        anios_activo = anios_activo + activo
        suma_sal_formal = suma_sal_formal + np.where(formal_imss, w_cot, 0.0)

        # -- retiro: nodo de diferimiento (60) + edad legal (65; reformable) --
        salida_retiro = 0.0
        if regla_tope == "real_constante":
            tope_fpb = reglas_sar.tope_fpb_mensual_real_constante(
                anio, topes_nominales, deflactor_inpc
            )
        else:
            tope_fpb = reglas_sar.tope_fpb_mensual(
                anio, tope_fpb_2024, tope_fpb_legado, g_secular
            )

        # Nodo de decisión UNA sola vez al cumplir 60 (SPEC §4.1-4.2): solo
        # en proyección y con el flag encendido. Quien no cumple semanas a
        # los 60 NO tiene decisión y sigue hasta 65 (⚠️ SUPUESTO declarado:
        # quien las cumple a los 61-64 tampoco decide → sesgo
        # pro-diferimiento; bitácora #27).
        if dif_activo and anio > anio_val and edad_ret > 60:
            decide = vivo & ~retirado & (edad == 60.0)
            for j in np.where(decide)[0]:
                if semanas[j] < politica.semanas_requeridas(anio):
                    continue
                b60 = saldo[j] / (12.0 * a_retiro(sexo[j], 60))
                anios_espera = edad_ret - 60
                # cota inferior [S]: proyección del saldo SIN aportaciones
                saldo_proy = saldo[j] * (1.0 + r_esperado) ** anios_espera
                b65 = saldo_proy / (12.0 * a_retiro(sexo[j], edad_ret))
                b60_hipotetica[j] = b60
                b65_esperada[j] = b65
                if dif_tasa_forzada is not None:
                    # sensibilidad F4: ignora la regla, sortea Bernoulli(p)
                    espera = rng.random() < float(dif_tasa_forzada)
                elif dif_regla == "umbral":
                    # réplica Actuarius: difiere si b65 >= umbral·b60
                    espera = b65 >= dif_umbral * b60
                else:  # "vpn" (validada al parsear config)
                    # VPN_esperar = b65·ä(65)·v^k·kp60  vs  VPN_ya = b60·ä(60)
                    tabla = qx["H"] if sexo[j] == 0 else qx["M"]
                    kp60 = float(np.prod(1.0 - tabla[60:edad_ret]))
                    v_tec = 1.0 / (1.0 + i_tec)
                    vpn_esperar = (
                        b65
                        * a_retiro(sexo[j], edad_ret)
                        * v_tec**anios_espera
                        * kp60
                    )
                    vpn_ya = b60 * a_retiro(sexo[j], 60)
                    espera = vpn_esperar >= vpn_ya
                difirio[j] = espera
                if not espera:
                    # retiro inmediato por cesantía: sin complemento FPB
                    # [V, F2 — es ley]; alimenta salida_retiro para que la
                    # conciliación global siga cerrando.
                    salida_retiro += _retirar_agente(
                        j, 60, anio, tope_fpb,
                        permite_fpb=False, via_con_pension="cesantia_60",
                    )
                    retirado[j] = True

        cumple_edad = vivo & ~retirado & (edad >= edad_ret) & (anio > anio_val)
        if cumple_edad.any():
            for j in np.where(cumple_edad)[0]:
                salida_retiro += _retirar_agente(
                    j, edad_ret, anio, tope_fpb,
                    permite_fpb=True, via_con_pension="vejez_65",
                )
            retirado[cumple_edad] = True

        # -- mortalidad (solo en proyección; el backcast condiciona a estar
        #    vivo en 2025 por construcción de la muestra CONAPO) -------------
        salida_muerte = 0.0
        if anio > anio_val:
            edades_i = np.clip(edad.astype(int), 0, 109)
            q = np.where(sexo == 0, qx["H"][edades_i], qx["M"][edades_i])
            muere = vivo & (rng.random(n) < q)
            # quien difirió y muere antes de retirarse: el costo de esperar
            # (SPEC §4.1) — el saldo sale como herencia, línea de abajo
            murio_difiriendo |= muere & difirio & ~retirado
            # ⚠️ PROVISIONAL: el saldo de activos fallecidos sale del sistema
            # (herencia a beneficiarios); sin pensión de sobrevivencia.
            salida_muerte = saldo[muere & ~retirado].sum()
            saldo[muere & ~retirado] = 0.0
            vivo = vivo & ~muere

        # ===== CONCILIACIÓN GLOBAL: ΔS_total = A + R - C - salidas ==========
        saldo_total_post = saldo[vivo].sum()
        flujo_neto = A[cuenta].sum() + R[cuenta].sum() - C[cuenta].sum()
        delta_total = saldo_total_post - saldo_total_pre
        esperado = flujo_neto - salida_retiro - salida_muerte
        if not np.isclose(delta_total, esperado, rtol=1e-9, atol=1e-3):
            raise ContabilidadError(
                f"Conciliación global falla en {anio}: ΔS={delta_total:.2f} "
                f"vs A+R-C-salidas={esperado:.2f}"
            )

        ledger_rows.append(
            {
                "anio": anio,
                "aportaciones_mm": A[cuenta].sum() * W / 1e6,
                "rendimientos_mm": R[cuenta].sum() * W / 1e6,
                "comisiones_mm": C[cuenta].sum() * W / 1e6,
                "salidas_retiro_mm": salida_retiro * W / 1e6,
                "salidas_muerte_mm": salida_muerte * W / 1e6,
                "saldo_total_mm": saldo_total_post * W / 1e6,
                "check_contable": "OK",
            }
        )

        # -- snapshot de validación 2025 --------------------------------------
        if anio == anio_val:
            validacion = {
                "saldo_rcv_simulado_mm": saldo[vivo & ~retirado].sum() * W / 1e6,
                "cotizantes_simulados": int(formal_imss.sum() * W),
                "cuentas_simuladas": int((vivo & (saldo > 0)).sum() * W),
                "peso_agente": W,
            }

        # -- costo FPB del año (jubilados vivos con complemento) --------------
        jub = vivo & retirado & (pension > 0)
        compl = np.where(
            jub & requiere_fpb, np.maximum(piso_fpb_i - pension, 0.0), 0.0
        )
        costo_fpb = compl.sum() * 12.0 * W
        pib_t = (
            cfg["macro"]["pib_2025_mm"]
            * (1 + cfg["macro"]["crecimiento_pib_real"]) ** (anio - 2025)
            * 1e6
        )
        anual_rows.append(
            {
                "anio": anio,
                "escenario": escenario,
                "n_jubilados": int(jub.sum() * W),
                "n_bajo_piso": int((jub & requiere_fpb).sum() * W),
                "costo_FPB_total_mm": costo_fpb / 1e6,
                "costo_como_pct_PIB": 100.0 * costo_fpb / pib_t,
            }
        )

        edad = edad + 1.0

    if matriz_heterogenea:
        # sector_issste DERIVADO del estado final (no hay flag en esta
        # ruta): True == terminó en formal_ISSSTE. Solo compatibilidad de
        # post-proceso; el sector es dinámico vía transiciones 5x5.
        sector_issste = estado == idx_f_issste

    df_ag = pd.DataFrame(
        {
            "agente_id": np.arange(n),
            "escenario": escenario,
            "cohorte_retiro": anio_retiro,
            "genero": np.where(sexo == 0, "H", "M"),
            "densidad_cotizacion": np.divide(
                anios_formal,
                anios_activo,
                out=np.zeros(n),
                where=anios_activo > 0,
            ),
            "saldo_final": saldo_final,
            "pension_mensual": pension,
            "tasa_reemplazo": tasa_reemplazo,
            "requiere_PG": requiere_pg,
            "requiere_FPB": requiere_fpb,
            "complemento_FPB_anual": np.where(
                requiere_fpb, 12.0 * np.maximum(piso_fpb_i - pension, 0.0), 0.0
            ),
            "edad_retiro": edad_al_retiro,
            "sector_issste": sector_issste,  # fuera del target IMSS; activable (#25)
            "semanas_cotizadas": semanas,
            # ⚠️ instrumentación diagnóstico NaN Paso 4 (solo exposición; el
            # estado se congela al retirarse, así que para retirados es el
            # estado laboral al momento del retiro). Etiquetas por ruta.
            "estado_final": etiquetas_estado[estado],
            "anios_formal": anios_formal,
            "vivo_final": vivo,
            "semilla": semilla if semilla is not None else cfg["semilla"],
        }
    )
    if matriz_heterogenea:
        df_ag["escolaridad"] = np.array(ESCOLARIDADES, dtype=object)[esc_idx]
    if dif_activo:
        # Salidas del nodo de diferimiento (SPEC §4.4). Emitidas SOLO con
        # el flag encendido: con el default apagado el df es idéntico al de
        # la rama base (no-regresión §8.1). via_de_pension usa las
        # categorías {vejez_65, cesantia_60, negativa, sin_retiro}.
        df_ag["via_de_pension"] = via_pension
        df_ag["b60_hipotetica"] = b60_hipotetica
        df_ag["b65_esperada"] = b65_esperada
        df_ag["difirio"] = difirio
        df_ag["murio_difiriendo"] = murio_difiriendo
    return ResultadoSimulacion(
        agentes=df_ag,
        anual=pd.DataFrame(anual_rows),
        validacion=validacion,
        ledger=pd.DataFrame(ledger_rows),
    )
