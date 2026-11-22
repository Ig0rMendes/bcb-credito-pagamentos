"""Testes da análise estatística com dados sintéticos (sem internet e sem os dados reais)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("statsmodels")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analise_estatistica import regressao  # noqa: E402


def test_regressao_recupera_o_efeito_conhecido():
    # y = 1 + 0,5 x + ruído pequeno: a regressão tem que achar 0,5 e um intervalo que o contenha.
    rng = np.random.default_rng(42)
    x = pd.Series(rng.normal(0, 2, 200))
    y = 1 + 0.5 * x + rng.normal(0, 0.1, 200)
    r = regressao(x, y)
    assert r["coeficiente"] == pytest.approx(0.5, abs=0.02)
    assert r["ic95_inferior"] < 0.5 < r["ic95_superior"]
    assert r["r2"] > 0.95


def test_newey_west_fica_mais_cauteloso_com_dados_autocorrelacionados():
    # Séries "lentas" (passeio aleatório suavizado): o erro-padrão comum subestima a incerteza.
    rng = np.random.default_rng(7)
    x = pd.Series(rng.normal(size=300)).rolling(12).mean().dropna().reset_index(drop=True)
    y = 0.3 * x + pd.Series(rng.normal(size=len(x))).rolling(12).mean().fillna(0)
    r = regressao(x, y)
    assert r["p_valor_newey_west"] > r["p_valor_comum"]


from analise_estatistica import amostra_efetiva, faixa_de_pico, fora_da_amostra, regra_de_alerta  # noqa: E402


def test_amostra_efetiva_menor_com_series_lentas():
    # Ruído independente: N efetivo perto de N. Séries suavizadas em 12 meses: N efetivo bem menor.
    rng = np.random.default_rng(1)
    a, b = rng.normal(size=200), rng.normal(size=200)
    assert amostra_efetiva(a, b) > 150
    lenta = lambda v: pd.Series(v).rolling(12).mean().dropna().values  # noqa: E731
    assert amostra_efetiva(lenta(rng.normal(size=212)), lenta(rng.normal(size=212))) < 60


def test_faixa_de_pico_inclui_defasagens_proximas():
    corr = pd.DataFrame({"indicador": "x", "base": "variacao_12m", "defasagem_meses": range(5),
                         "correlacao": [0.50, 0.78, 0.80, 0.76, 0.60]})
    assert faixa_de_pico(corr, "x") == (2, 1, 3)


def test_fora_da_amostra_nao_usa_o_futuro():
    # Alvo puro ruído: nenhum modelo pode ganhar muito da previsão "sem mudança".
    rng = np.random.default_rng(3)
    idx = pd.date_range("2015-01-01", periods=120, freq="MS")
    t = pd.DataFrame({c: rng.normal(size=120) for c in ["alvo", "inercia", "juro_real_ex_ante_var12", "atividade_var12",
                                                          "desocupacao_var12", "concessoes_var12"]}, index=idx)
    t["pandemia"] = 0.0
    t = t.rename(columns={"inercia": "inércia"})
    r = fora_da_amostra(t, inicio=pd.Timestamp("2021-01-01")).set_index("modelo")
    assert (r["ganho_vs_sem_mudanca"].drop("sem mudança") < 0.1).all()


def test_regra_de_alerta_conta_os_meses():
    t = pd.DataFrame({"juro_real_ex_ante_var12": [1, 1, -1, -1], "alvo": [0.2, -0.1, -0.3, 0.1]},
                     index=pd.date_range("2020-01-01", periods=4, freq="MS"))
    r = regra_de_alerta(t)
    assert (r["meses_com_alerta"], r["acerto_com_alerta"], r["subida_sem_alerta"]) == (2, 0.5, 0.5)
