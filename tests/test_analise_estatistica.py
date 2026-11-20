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
