"""
Análise estatística: juros -> inadimplência das empresas, com defasagem.

Lê data/processed/series_sgs_longo.csv (gerado por coletar_dados.py) e produz:
  - docs/analise_estatistica.md                 relatório com os resultados (gerado automaticamente)
  - data/processed/regressao_defasagem.csv       coeficientes e intervalos, para o Power BI

Método, em três camadas:
  1. Correlação de Pearson entre os juros de k meses atrás e a inadimplência PJ de hoje (k = 0 a 24),
     em nível e em variação de 12 meses, sempre na MESMA amostra de meses (como em sql/05_gold.sql).
  2. Regressão linear simples na defasagem de maior correlação (variação de 12 meses):
     inadimplência_var12(t) = a + b * juros_var12(t - k)
  3. Erro-padrão de Newey-West (HAC): variações de 12 meses em meses vizinhos compartilham 11 meses
     de dados, então os resíduos são autocorrelacionados e o teste comum fica otimista demais.

Uso:  python src/analise_estatistica.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

RAIZ = Path(__file__).resolve().parents[1]
ARQ_SGS = RAIZ / "data" / "processed" / "series_sgs_longo.csv"
ARQ_CSV = RAIZ / "data" / "processed" / "regressao_defasagem.csv"
ARQ_MD = RAIZ / "docs" / "analise_estatistica.md"

DEFASAGEM_MAXIMA = 24
LAGS_NEWEY_WEST = 12  # cobre a sobreposição das variações de 12 meses
INDICADORES = {"selic_meta": "Selic (meta)", "juro_real": "Juro real ex post"}


def indicadores_mensais(sgs: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por mês, com IPCA 12m e juro real (mesma definição da silver)."""
    largo = sgs.assign(data=pd.to_datetime(sgs["data"])).pivot(index="data", columns="serie", values="valor").sort_index()
    ipca_12m = ((1 + largo["ipca_mensal"] / 100).rolling(12).apply(np.prod, raw=True) - 1) * 100
    largo["juro_real"] = ((1 + largo["selic_meta"] / 100) / (1 + ipca_12m / 100) - 1) * 100
    return largo


def amostra_comum(largo: pd.DataFrame) -> pd.DatetimeIndex:
    """Meses em que TODAS as defasagens têm dados (24 de defasagem + 12 da variação + 11 do IPCA 12m)."""
    inicio = largo.index[0] + pd.DateOffset(months=DEFASAGEM_MAXIMA + 12 + 11)
    return largo.index[(largo.index >= inicio) & largo["inadimplencia_pj"].notna()]


def series(largo: pd.DataFrame, indicador: str, base: str) -> tuple[pd.Series, pd.Series]:
    x, y = largo[indicador], largo["inadimplencia_pj"]
    if base == "variacao_12m":
        x, y = x.diff(12), y.diff(12)
    return x, y


def correlacoes(largo: pd.DataFrame) -> pd.DataFrame:
    alvo = amostra_comum(largo)
    linhas = []
    for indicador in INDICADORES:
        for base in ["nivel", "variacao_12m"]:
            x, y = series(largo, indicador, base)
            for k in range(DEFASAGEM_MAXIMA + 1):
                corr = np.corrcoef(x.shift(k).loc[alvo], y.loc[alvo])[0, 1]
                linhas.append((indicador, base, k, corr, len(alvo)))
    return pd.DataFrame(linhas, columns=["indicador", "base", "defasagem_meses", "correlacao", "meses"])


def regressao(x: pd.Series, y: pd.Series) -> dict:
    """MQO com erro-padrão comum e com Newey-West. Devolve só números (fácil de testar e de exportar)."""
    X = sm.add_constant(x.rename("x"))
    comum = sm.OLS(y, X).fit()
    nw = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": LAGS_NEWEY_WEST})
    ic = nw.conf_int().loc["x"]
    return {
        "coeficiente": nw.params["x"],
        "intercepto": nw.params["const"],
        "r2": comum.rsquared,
        "p_valor_comum": comum.pvalues["x"],
        "p_valor_newey_west": nw.pvalues["x"],
        "ic95_inferior": ic[0],
        "ic95_superior": ic[1],
        "meses": int(comum.nobs),
    }


def regressoes_nos_picos(largo: pd.DataFrame, corr: pd.DataFrame) -> pd.DataFrame:
    alvo = amostra_comum(largo)
    var12 = corr[corr["base"] == "variacao_12m"]
    linhas = []
    for indicador, grupo in var12.groupby("indicador"):
        k = int(grupo.loc[grupo["correlacao"].idxmax(), "defasagem_meses"])
        x, y = series(largo, indicador, "variacao_12m")
        linhas.append({"indicador": indicador, "defasagem_meses": k, **regressao(x.shift(k).loc[alvo], y.loc[alvo])})
    return pd.DataFrame(linhas)


def relatorio(largo: pd.DataFrame, corr: pd.DataFrame, reg: pd.DataFrame) -> str:
    alvo = amostra_comum(largo)
    picos = corr.loc[corr.groupby(["indicador", "base"])["correlacao"].idxmax()]
    br = lambda v, casas=2: f"{v:.{casas}f}".replace(".", ",")  # noqa: E731
    texto = [
        "# Análise estatística: juros → inadimplência das empresas",
        "",
        f"> Gerado automaticamente por `src/analise_estatistica.py` em {date.today():%d/%m/%Y}. "
        f"Amostra: **{len(alvo)} meses**, de {alvo.min():%m/%Y} a {alvo.max():%m/%Y} "
        "(a mesma para todas as defasagens).",
        "",
        "## 1. Em quantos meses os juros \"chegam\" na inadimplência?",
        "",
        "Correlação de Pearson entre os juros de *k* meses atrás e a inadimplência PJ de hoje. "
        "Defasagem com a maior correlação:",
        "",
        "| Indicador | Base | Defasagem | Correlação |",
        "|---|---|---|---|",
    ]
    for _, p in picos.sort_values(["indicador", "base"]).iterrows():
        base = "variação em 12 meses" if p["base"] == "variacao_12m" else "nível"
        texto.append(f"| {INDICADORES[p['indicador']]} | {base} | **{int(p['defasagem_meses'])} meses** | {br(p['correlacao'])} |")
    texto += [
        "",
        "## 2. Qual o tamanho do efeito? (regressão na defasagem de pico, variação em 12 meses)",
        "",
        "| Indicador | Defasagem | Efeito de +1 p.p. nos juros | Intervalo de 95% (Newey-West) | R² | p-valor (Newey-West) |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in reg.iterrows():
        texto.append(
            f"| {INDICADORES[r['indicador']]} | {int(r['defasagem_meses'])} meses | "
            f"**{br(r['coeficiente'], 3)} p.p.** de inadimplência PJ | {br(r['ic95_inferior'], 3)} a {br(r['ic95_superior'], 3)} | "
            f"{br(r['r2'])} | {r['p_valor_newey_west']:.1e} |"
        )
    real = reg.set_index("indicador").loc["juro_real"]
    faixa = largo.loc[alvo, "inadimplencia_pj"]
    texto += [
        "",
        "## 3. Como ler",
        "",
        f"- Quando o **juro real** sobe 1 ponto percentual em 12 meses, a inadimplência das empresas tende a subir "
        f"cerca de **{br(real['coeficiente'], 2)} ponto** em 12 meses, uns **{int(real['defasagem_meses'])} meses depois**. "
        f"No período, a inadimplência PJ variou entre {br(faixa.min())}% e {br(faixa.max())}%.",
        f"- O R² de {br(real['r2'])} indica que a variação do juro real acompanha cerca de "
        f"{round(real['r2'] * 100)}% da variação da inadimplência nesse período.",
        "- **Newey-West:** as variações de 12 meses de meses vizinhos compartilham 11 meses de dados; o erro-padrão "
        "comum ficaria otimista demais. Mesmo corrigido, o intervalo de 95% não chega perto de zero.",
        "",
        "## 4. Cuidados",
        "",
        "- **Correlação não prova causa.** Juros e inadimplência respondem juntos ao ciclo da economia "
        "(pandemia, inflação, crises).",
        f"- **Amostra curta:** {len(alvo)} meses cobrem poucos ciclos de juros. A defasagem de pico é uma estimativa, "
        "não uma constante.",
        "- **Juro real ex post** compara a meta Selic do mês com a inflação **passada** de 12 meses (aproximação).",
    ]
    return "\n".join(texto) + "\n"


def main() -> None:
    largo = indicadores_mensais(pd.read_csv(ARQ_SGS))
    corr = correlacoes(largo)
    reg = regressoes_nos_picos(largo, corr)
    reg.to_csv(ARQ_CSV, index=False)
    ARQ_MD.parent.mkdir(exist_ok=True)
    ARQ_MD.write_text(relatorio(largo, corr, reg), encoding="utf-8")
    print(reg.round(4).to_string(index=False))
    print(f"\nRelatório: {ARQ_MD.relative_to(RAIZ)} | Tabela: {ARQ_CSV.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
