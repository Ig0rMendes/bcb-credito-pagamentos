"""
Gabarito automático: os valores que as tabelas do Databricks DEVEM ter.

A cada coleta, este módulo recalcula com pandas (sem SQL) os números que as checagens
sql/03 e sql/06 conferem. O resultado vai para data/processed/gabarito.csv, que sobe para o
Databricks junto com os dados. Assim:
  - nenhum número fica escrito à mão no SQL (nada fica desatualizado quando entra um mês novo);
  - o gabarito é uma conta INDEPENDENTE: pandas, com outra lógica, conferindo o resultado do SQL.

Cada checagem tem: nome (igual ao usado no SQL), valor esperado e tolerância
(motores diferentes podem arredondar a última casa decimal de forma diferente).
Os nomes precisam ser idênticos aos do SQL; o teste tests/test_sql_local.py garante isso.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Mesma regra do 04_silver.sql: naturezas em que uma empresa paga ou recebe
NATUREZAS_COM_EMPRESA = {"B2B", "B2P", "B2G", "P2B", "G2B"}
DEFASAGEM_MAXIMA = 24  # meses, igual ao 05_gold.sql


def _indicadores_mensais(sgs: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por mês, uma coluna por série, mais IPCA 12m e juro real (contas feitas de outro jeito que o SQL)."""
    largo = sgs.pivot(index="data", columns="serie", values="valor").sort_index()
    # IPCA 12m multiplicando diretamente os 12 fatores (o SQL usa exp(soma de logaritmos))
    largo["ipca_12m"] = ((1 + largo["ipca_mensal"] / 100).rolling(12).apply(np.prod, raw=True) - 1) * 100
    largo["juro_real"] = ((1 + largo["selic_meta"] / 100) / (1 + largo["ipca_12m"] / 100) - 1) * 100
    return largo


def _picos_de_correlacao(largo: pd.DataFrame) -> tuple[int, dict[tuple[str, str], tuple[int, float]]]:
    """Para cada indicador e base, a defasagem com maior correlação (deslocando a série com shift, não com JOIN)."""
    inicio = largo.index[0] + pd.DateOffset(months=DEFASAGEM_MAXIMA + 12 + 11)
    alvo = largo.index[(largo.index >= inicio) & largo["inadimplencia_pj"].notna()]
    picos = {}
    for indicador, coluna in [("selic_meta", "selic_meta"), ("juro_real_ex_post", "juro_real")]:
        for base in ["nivel", "variacao_12m"]:
            x = largo[coluna] if base == "nivel" else largo[coluna].diff(12)
            y = largo["inadimplencia_pj"] if base == "nivel" else largo["inadimplencia_pj"].diff(12)
            correlacoes = {k: np.corrcoef(x.shift(k).loc[alvo], y.loc[alvo])[0, 1] for k in range(DEFASAGEM_MAXIMA + 1)}
            k_pico = max(correlacoes, key=correlacoes.get)
            picos[(indicador, base)] = (k_pico, correlacoes[k_pico])
    return len(alvo), picos


def gerar_gabarito(sgs: pd.DataFrame, pix: pd.DataFrame) -> pd.DataFrame:
    """Recebe as tabelas que vão para a bronze e devolve: checagem, esperado, tolerancia."""
    sgs = sgs.assign(data=pd.to_datetime(sgs["data"]))
    pix = pix.assign(data=pd.to_datetime(pix["data"]), ano_mes=pix["ano_mes"].astype(str))
    linhas: list[tuple[str, float, float]] = []

    def checar(nome: str, esperado: float, tolerancia: float = 0) -> None:
        linhas.append((nome, float(esperado), float(tolerancia)))

    # ---------------- Bronze (sql/03) ----------------
    checar("bronze_sgs: linhas", len(sgs))
    checar("bronze_sgs: séries", sgs["serie"].nunique())
    checar("bronze_sgs: duplicadas", sgs.duplicated(["serie", "data"]).sum())
    checar("bronze_sgs: nulos", sgs[["data", "valor"]].isna().any(axis=1).sum())
    checar("bronze_pix: linhas", len(pix))
    checar("bronze_pix: meses", pix["ano_mes"].nunique())
    checar("bronze_pix: primeiro mês (AAAAMM)", int(pix["ano_mes"].min()))
    checar("bronze_pix: último mês (AAAAMM)", int(pix["ano_mes"].max()))
    checar("bronze_pix: nulos em VALOR/QUANTIDADE", pix[["VALOR", "QUANTIDADE"]].isna().any(axis=1).sum())

    # ---------------- Silver (sql/06) ----------------
    largo = _indicadores_mensais(sgs)
    ref = largo["inadimplencia_pj"].last_valid_index()  # mês de referência: último com inadimplência PJ
    checar("silver_indicadores: meses", len(largo))
    meses_esperados = len(pd.date_range(largo.index.min(), largo.index.max(), freq="MS"))
    checar("silver_indicadores: meses sem buraco (último - primeiro + 1)", meses_esperados)
    checar("silver_indicadores: IPCA 12m no mês de referência (%)", largo.loc[ref, "ipca_12m"], 0.0002)
    checar("silver_indicadores: juro real no mês de referência (%)", largo.loc[ref, "juro_real"], 0.0002)

    empresa = pix["NATUREZA"].isin(NATUREZAS_COM_EMPRESA)
    checar("silver_pix: linhas", len(pix))
    # Somar centenas de milhares de decimais em ordens diferentes muda os últimos centavos
    # (o computador guarda ~16 dígitos). Tolerância proporcional: 1 parte em 1 trilhão do total.
    checar("silver_pix: diferença de valor para a bronze (R$)", 0, max(1.0, pix["VALOR"].sum() * 1e-12))
    checar("silver_pix: linhas com empresa pagando ou recebendo", empresa.sum())

    # ---------------- Gold (sql/06) ----------------
    checar("gold_defasagem: meses", len(largo))
    seis_meses_antes = ref - pd.DateOffset(months=6)
    checar("gold_defasagem: Selic 6 meses antes do mês de referência", largo.loc[seis_meses_antes, "selic_meta"])

    meses_usados, picos = _picos_de_correlacao(largo)
    checar("gold_correlacao: linhas (25 defasagens x 2 indicadores x 2 bases)", (DEFASAGEM_MAXIMA + 1) * 4)
    checar("gold_correlacao: mesma amostra em todas (meses distintos usados)", 1)
    checar("gold_correlacao: meses usados", meses_usados)
    for (indicador, base), (k, corr) in picos.items():
        checar(f"gold_correlacao: pico {indicador}, {base} (meses)", k)
        checar(f"gold_correlacao: valor do pico {indicador}, {base}", corr, 0.001)

    ultimo = pix["ano_mes"].max()
    no_ultimo = pix[pix["ano_mes"] == ultimo]
    b2b = no_ultimo.loc[no_ultimo["NATUREZA"] == "B2B", "VALOR"].sum() / no_ultimo["VALOR"].sum()
    checar("gold_pix_natureza: linhas", len(pix.groupby(["ano_mes", "NATUREZA"])))
    checar("gold_pix_natureza: participação B2B no último mês", b2b, 0.000001)
    forma = pix["FORMAINICIACAO"].fillna("Nao informado")
    checar("gold_pix_empresas: linhas", len(pix[empresa].groupby(["ano_mes", "NATUREZA", forma[empresa]])))
    checar("gold_pix_empresas: valor do último mês igual ao da natureza (R$ bi, diferença)", 0, 0.001)

    return pd.DataFrame(linhas, columns=["checagem", "esperado", "tolerancia"])
