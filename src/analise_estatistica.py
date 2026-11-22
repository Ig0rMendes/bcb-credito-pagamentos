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


# ---------------------------------------------------------------------------
# Robustez: tamanho efetivo da amostra, incerteza da defasagem, controles e
# validação fora da amostra. Responde às perguntas "isso é real?" e "isso prevê?".
# ---------------------------------------------------------------------------

ARQ_CONTROLES = RAIZ / "data" / "processed" / "controles_mensais.csv"
HORIZONTE = 6            # meses à frente na previsão
TOLERANCIA_PICO = 0.05   # defasagens com correlação até 0,05 abaixo do pico formam a "faixa"
BLOCO_BOOTSTRAP = 12     # blocos de 12 meses preservam a autocorrelação das séries
REPETICOES_BOOTSTRAP = 2000
PANDEMIA = (pd.Timestamp("2020-03-01"), pd.Timestamp("2021-12-01"))
INICIO_TESTE = pd.Timestamp("2023-01-01")


def com_controles(largo: pd.DataFrame, controles: pd.DataFrame) -> pd.DataFrame:
    """Junta as séries de controle e calcula o juro real ex ante (Selic sobre a inflação ESPERADA)."""
    c = controles.assign(data=pd.to_datetime(controles["data"])).set_index("data")
    d = largo.join(c, how="left")
    d["juro_real_ex_ante"] = ((1 + d["selic_meta"] / 100) / (1 + d["ipca_expectativa_12m"] / 100) - 1) * 100
    d["concessoes_pj_12m"] = d["concessoes_pj"].rolling(12).sum()
    return d


def amostra_efetiva(x: pd.Series, y: pd.Series) -> float:
    """Tamanho efetivo da amostra para a correlação de duas séries autocorrelacionadas (Bartlett).

    N_ef = N / (1 + 2 * soma_k rho_x(k) * rho_y(k)). Com variações de 12 meses, vizinhos repetem
    11 meses de dados, então 94 pontos valem bem menos que 94 observações independentes.
    """
    x, y = x - x.mean(), y - y.mean()
    n = len(x)
    soma = 0.0
    for k in range(1, n // 4):
        rx = np.corrcoef(x[:-k], x[k:])[0, 1]
        ry = np.corrcoef(y[:-k], y[k:])[0, 1]
        if rx * ry <= 0:  # para quando o produto deixa de ser positivo (truncagem usual)
            break
        soma += rx * ry
    return n / (1 + 2 * soma)


def faixa_de_pico(corr: pd.DataFrame, indicador: str, base: str = "variacao_12m") -> tuple[int, int, int]:
    """Defasagem de pico e a faixa de defasagens com correlação a até 0,05 do pico."""
    g = corr[(corr["indicador"] == indicador) & (corr["base"] == base)]
    pico = g.loc[g["correlacao"].idxmax()]
    perto = g[g["correlacao"] >= pico["correlacao"] - TOLERANCIA_PICO]["defasagem_meses"]
    return int(pico["defasagem_meses"]), int(perto.min()), int(perto.max())


def bootstrap_pico(x: pd.Series, y: pd.Series, alvo: pd.DatetimeIndex, semente: int = 42) -> dict:
    """Bootstrap de blocos móveis: reamostra blocos de 12 meses e recalcula a defasagem de pico e o r.

    Devolve o intervalo de 90% da defasagem de pico e o intervalo de 95% do r no pico original.
    """
    rng = np.random.default_rng(semente)
    defasados = np.column_stack([x.shift(k).loc[alvo].values for k in range(DEFASAGEM_MAXIMA + 1)])
    yv = y.loc[alvo].values
    n = len(yv)
    k_orig = int(np.argmax([np.corrcoef(defasados[:, k], yv)[0, 1] for k in range(DEFASAGEM_MAXIMA + 1)]))
    picos, rs = [], []
    inicios_possiveis = n - BLOCO_BOOTSTRAP + 1
    for _ in range(REPETICOES_BOOTSTRAP):
        inicios = rng.integers(0, inicios_possiveis, size=int(np.ceil(n / BLOCO_BOOTSTRAP)))
        idx = np.concatenate([np.arange(s, s + BLOCO_BOOTSTRAP) for s in inicios])[:n]
        cs = [np.corrcoef(defasados[idx, k], yv[idx])[0, 1] for k in range(DEFASAGEM_MAXIMA + 1)]
        picos.append(int(np.argmax(cs)))
        rs.append(cs[k_orig])
    return {
        "pico": k_orig,
        "pico_p05": int(np.percentile(picos, 5)),
        "pico_p95": int(np.percentile(picos, 95)),
        "r_ic95_inferior": float(np.percentile(rs, 2.5)),
        "r_ic95_superior": float(np.percentile(rs, 97.5)),
    }


def base_previsao(d: pd.DataFrame, h: int = HORIZONTE) -> pd.DataFrame:
    """Tabela para prever a MUDANÇA FUTURA da inadimplência, só com o que se sabe no mês t.

    alvo:  inadimplência(t + h) - inadimplência(t)      (nada disso é conhecido em t)
    inercia: inadimplência(t) - inadimplência(t - h)    (a própria tendência recente)
    juros:  variação em 12 meses do juro real ex ante e ex post, conhecida em t
    controles: atividade (IBC-Br, var. 12m em %), desemprego (var. 12m em p.p.),
               concessões PJ acumuladas em 12 meses (var. 12m em %) e um indicador da pandemia.
    """
    t = pd.DataFrame(index=d.index)
    t["alvo"] = d["inadimplencia_pj"].shift(-h) - d["inadimplencia_pj"]
    t["inércia"] = d["inadimplencia_pj"] - d["inadimplencia_pj"].shift(h)
    t["juro_real_ex_ante_var12"] = d["juro_real_ex_ante"].diff(12)
    t["juro_real_ex_post_var12"] = d["juro_real"].diff(12)
    t["atividade_var12"] = (d["ibc_br_dessaz"] / d["ibc_br_dessaz"].shift(12) - 1) * 100
    t["desocupacao_var12"] = d["desocupacao"].diff(12)
    t["concessoes_var12"] = (d["concessoes_pj_12m"] / d["concessoes_pj_12m"].shift(12) - 1) * 100
    t["pandemia"] = ((t.index >= PANDEMIA[0]) & (t.index <= PANDEMIA[1])).astype(float)
    return t.dropna()


MODELOS = {
    "só juro real": ["juro_real_ex_ante_var12"],
    "inércia": ["inércia"],
    "inércia + juro real": ["inércia", "juro_real_ex_ante_var12"],
    "inércia + juro real + controles": ["inércia", "juro_real_ex_ante_var12", "atividade_var12",
                                        "desocupacao_var12", "concessoes_var12", "pandemia"],
}


def ajustar(t: pd.DataFrame, colunas: list[str], h: int = HORIZONTE):
    X = sm.add_constant(t[colunas])
    return sm.OLS(t["alvo"], X).fit(cov_type="HAC", cov_kwds={"maxlags": h})


def modelos_dentro_da_amostra(t: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for nome, cols in MODELOS.items():
        m = ajustar(t, cols)
        linha = {"modelo": nome, "r2_ajustado": m.rsquared_adj, "meses": int(m.nobs)}
        if "juro_real_ex_ante_var12" in cols:
            ic = m.conf_int().loc["juro_real_ex_ante_var12"]
            linha.update(coef_juro=m.params["juro_real_ex_ante_var12"], ic95_inf=ic[0], ic95_sup=ic[1],
                         p_juro=m.pvalues["juro_real_ex_ante_var12"])
        linhas.append(linha)
    return pd.DataFrame(linhas)


def fora_da_amostra(t: pd.DataFrame, h: int = HORIZONTE, inicio: pd.Timestamp = INICIO_TESTE) -> pd.DataFrame:
    """Janela expansiva: em cada mês t do teste, treina só com alvos já conhecidos em t (até t - h)."""
    erros = {nome: [] for nome in ["sem mudança", *MODELOS]}
    for mes in t.index[t.index >= inicio]:
        treino = t[t.index <= mes - pd.DateOffset(months=h)]
        real = t.loc[mes, "alvo"]
        erros["sem mudança"].append(real)
        for nome, cols in MODELOS.items():
            m = sm.OLS(treino["alvo"], sm.add_constant(treino[cols])).fit()
            previsto = float(m.predict(sm.add_constant(t.loc[[mes], cols], has_constant="add")).iloc[0])
            erros[nome].append(real - previsto)
    base = np.sqrt(np.mean(np.square(erros["sem mudança"])))
    linhas = []
    for nome, e in erros.items():
        rmse = float(np.sqrt(np.mean(np.square(e))))
        linhas.append({"modelo": nome, "rmse_pp": rmse, "ganho_vs_sem_mudanca": 1 - rmse / base, "meses_teste": len(e)})
    return pd.DataFrame(linhas)


def fora_da_amostra_janelas(t: pd.DataFrame) -> pd.DataFrame:
    """O resultado fora da amostra depende de onde começa o teste? (2022, 2023 e 2024)"""
    linhas = []
    for ano in (2022, 2023, 2024):
        r = fora_da_amostra(t, inicio=pd.Timestamp(f"{ano}-01-01")).set_index("modelo")["ganho_vs_sem_mudanca"]
        linhas.append({"teste_desde": ano, **r.to_dict()})
    return pd.DataFrame(linhas)


def regra_de_alerta(t: pd.DataFrame) -> dict:
    """Regra simples, testada no histórico: 'juro real ex ante subiu em 12 meses' -> inadimplência sobe em 6 meses?"""
    alerta = t["juro_real_ex_ante_var12"] > 0
    subiu = t["alvo"] > 0
    return {
        "meses_com_alerta": int(alerta.sum()),
        "acerto_com_alerta": float(subiu[alerta].mean()),
        "meses_sem_alerta": int((~alerta).sum()),
        "subida_sem_alerta": float(subiu[~alerta].mean()),
        "mudanca_media_com_alerta": float(t.loc[alerta, "alvo"].mean()),
        "mudanca_media_sem_alerta": float(t.loc[~alerta, "alvo"].mean()),
        "inicio": t.index.min(),
        "fim": t.index.max(),
    }


def robustez_horizonte(d: pd.DataFrame) -> pd.DataFrame:
    """O juro real ajuda a prever a inadimplência em 3, 6, 9 e 12 meses? (com inércia e controles)"""
    linhas = []
    for h in (3, 6, 9, 12):
        t = base_previsao(d, h)
        m = ajustar(t, MODELOS["inércia + juro real + controles"], h)
        ic = m.conf_int().loc["juro_real_ex_ante_var12"]
        linhas.append({"horizonte": h, "coef_juro": m.params["juro_real_ex_ante_var12"],
                       "ic95_inf": ic[0], "ic95_sup": ic[1], "meses": int(m.nobs)})
    return pd.DataFrame(linhas)


def relatorio(largo: pd.DataFrame, corr: pd.DataFrame, reg: pd.DataFrame, rob: dict) -> str:
    alvo = amostra_comum(largo)
    br = lambda v, casas=2: f"{v:.{casas}f}".replace(".", ",")  # noqa: E731
    pct = lambda v: f"{v * 100:.0f}%"  # noqa: E731
    real = reg.set_index("indicador").loc["juro_real"]
    selic = reg.set_index("indicador").loc["selic_meta"]
    bj, bs = rob["boot_juro_real"], rob["boot_selic"]
    fj, fs = rob["faixa_juro_real"], rob["faixa_selic"]
    dentro, fora, janelas, regra, regra_teste, horiz, semp = (
        rob["dentro"], rob["fora"], rob["janelas"], rob["regra"], rob["regra_teste"], rob["horizontes"], rob["sem_pandemia"])
    m = dentro.set_index("modelo")
    f = fora.set_index("modelo")
    texto = [
        "# Análise estatística: juros → inadimplência das empresas",
        "",
        f"> Gerado automaticamente por `src/analise_estatistica.py` em {date.today():%d/%m/%Y}.",
        "",
        "**Inadimplência PJ** = série SGS 21083: percentual da carteira de crédito a pessoas jurídicas com atraso "
        "acima de 90 dias. É uma razão (atrasos ÷ carteira), então também muda quando a carteira cresce ou encolhe.",
        "",
        "## Resumo honesto",
        "",
        f"- **A relação existe e resiste a controles, mas é imprecisa.** O juro real ajuda a explicar a inadimplência "
        f"dos meses seguintes mesmo descontando atividade, desemprego, concessões de crédito e a pandemia. "
        f"Sem os meses de 2020–2021, porém, o efeito fica perto de zero.",
        f"- **Como previsão de magnitude, ajuda pouco.** Fora da amostra, só o modelo mais simples (apenas o juro real) "
        f"erra menos que a previsão ingênua \"vai ficar como está\", e por pouco ({rob['ganho_min_simples']:.0f}% a "
        f"{rob['ganho_max_simples']:.0f}% conforme a janela). Somar inércia e controles piora a previsão.",
        f"- **Serve como alerta de direção.** Quando o juro real ex ante subiu em 12 meses, a inadimplência subiu nos "
        f"6 meses seguintes em {pct(regra['acerto_com_alerta'])} dos meses (contra {pct(regra['subida_sem_alerta'])} sem o alerta). "
        f"No período de teste, que não foi usado para escolher nada além do horizonte, foram {pct(regra_teste['acerto_com_alerta'])} "
        f"contra {pct(regra_teste['subida_sem_alerta'])}.",
        "",
        "## 1. Correlação por defasagem (descritivo)",
        "",
        f"Amostra fixa de **{len(alvo)} meses** ({alvo.min():%m/%Y} a {alvo.max():%m/%Y}), a mesma para as 25 defasagens, "
        "com as duas séries em variação de 12 meses.",
        "",
        "| Indicador | Pico | Faixa (r até 0,05 abaixo do pico) | Pico no bootstrap (90%) | r no pico | r, intervalo de 95% (bootstrap) | Tamanho efetivo da amostra |",
        "|---|---|---|---|---|---|---|",
        f"| Juro real ex post | {fj[0]} meses | {fj[1]} a {fj[2]} meses | {bj['pico_p05']} a {bj['pico_p95']} meses | "
        f"{br(corr.query('indicador == \"juro_real\" and base == \"variacao_12m\"')['correlacao'].max())} | "
        f"{br(bj['r_ic95_inferior'])} a {br(bj['r_ic95_superior'])} | ~{rob['nef_juro_real']:.0f} meses |",
        f"| Selic (meta) | {fs[0]} meses | {fs[1]} a {fs[2]} meses | {bs['pico_p05']} a {bs['pico_p95']} meses | "
        f"{br(corr.query('indicador == \"selic_meta\" and base == \"variacao_12m\"')['correlacao'].max())} | "
        f"{br(bs['r_ic95_inferior'])} a {br(bs['r_ic95_superior'])} | ~{rob['nef_selic']:.0f} meses |",
        "",
        "- **Por que o tamanho efetivo é tão pequeno:** variações de 12 meses em meses vizinhos repetem 11 meses de dados. "
        f"Pela fórmula de Bartlett, os {len(alvo)} pontos valem cerca de {rob['nef_juro_real']:.0f} observações independentes. "
        "Por isso o r alto (0,83) tem um intervalo largo.",
        f"- **A defasagem é uma faixa, não um número.** O bootstrap de blocos de 12 meses ({REPETICOES_BOOTSTRAP} reamostragens) "
        f"coloca o pico do juro real entre {bj['pico_p05']} e {bj['pico_p95']} meses em 90% das vezes.",
        "- **Seleção:** o pico foi escolhido entre 25 defasagens × 2 indicadores × 2 bases. Por isso os p-valores da "
        "regressão no pico (abaixo) são otimistas; a validação fora da amostra (seção 3) é o teste que vale.",
        "",
        "Regressão na defasagem de pico (variação em 12 meses dos dois lados, erro-padrão Newey-West com 12 defasagens):",
        "",
        "| Indicador | Defasagem | +1 p.p. na variação em 12 meses dos juros → variação em 12 meses da inadimplência | Intervalo de 95% | R² |",
        "|---|---|---|---|---|",
        f"| Juro real ex post | {int(real['defasagem_meses'])} meses | {br(real['coeficiente'], 3)} p.p. | "
        f"{br(real['ic95_inferior'], 3)} a {br(real['ic95_superior'], 3)} | {br(real['r2'])} |",
        f"| Selic (meta) | {int(selic['defasagem_meses'])} meses | {br(selic['coeficiente'], 3)} p.p. | "
        f"{br(selic['ic95_inferior'], 3)} a {br(selic['ic95_superior'], 3)} | {br(selic['r2'])} |",
        "",
        f"Com o **juro real ex ante** (Selic sobre a inflação esperada no Focus), o pico fica em {rob['faixa_ex_ante'][0]} meses "
        f"(faixa de {rob['faixa_ex_ante'][1]} a {rob['faixa_ex_ante'][2]}) e r = {br(rob['r_ex_ante'])}.",
        "",
        "## 2. O juro real ainda importa depois da inércia e dos controles?",
        "",
        f"Alvo: **mudança da inadimplência nos {HORIZONTE} meses seguintes**, só com o que se sabia no mês (nada do alvo é "
        f"conhecido na hora). {int(m.loc['inércia', 'meses'])} meses, de {rob['t_inicio']:%m/%Y} a {rob['t_fim']:%m/%Y}. "
        f"Erro-padrão Newey-West com {HORIZONTE} defasagens.",
        "",
        "| Modelo | R² ajustado | +1 p.p. na variação em 12 meses do juro real ex ante → p.p. de inadimplência em 6 meses | Intervalo de 95% |",
        "|---|---|---|---|",
    ]
    for nome in MODELOS:
        r = m.loc[nome]
        efeito = "—" if pd.isna(r.get("coef_juro")) else br(r["coef_juro"], 3)
        ic = "—" if pd.isna(r.get("coef_juro")) else f"{br(r['ic95_inf'], 3)} a {br(r['ic95_sup'], 3)}"
        texto.append(f"| {nome} | {br(r['r2_ajustado'])} | {efeito} | {ic} |")
    texto += [
        "",
        "- **Inércia** = quanto a inadimplência mudou nos 6 meses anteriores. **Controles** = atividade (IBC-Br, variação em 12 meses), "
        "desemprego (PNAD, variação em 12 meses), concessões de crédito PJ acumuladas em 12 meses (variação em 12 meses) "
        "e um indicador da pandemia (mar/2020 a dez/2021).",
        f"- **Sem os meses da pandemia**, o efeito cai para {br(semp['coef'], 3)} p.p. (intervalo de {br(semp['ic95_inf'], 3)} a "
        f"{br(semp['ic95_sup'], 3)}, {semp['meses']} meses): continua positivo, mas perto de zero. Boa parte da força da "
        "relação vem de 2020–2022.",
        "- **Outros horizontes** (mesmo modelo completo):",
        "",
        "| Horizonte | Efeito | Intervalo de 95% |",
        "|---|---|---|",
    ]
    for _, h in horiz.iterrows():
        texto.append(f"| {int(h['horizonte'])} meses | {br(h['coef_juro'], 3)} | {br(h['ic95_inf'], 3)} a {br(h['ic95_sup'], 3)} |")
    texto += [
        "",
        "## 3. Prevê fora da amostra?",
        "",
        f"Janela expansiva: em cada mês do teste, o modelo é treinado só com resultados que já eram conhecidos naquele mês. "
        f"Erro médio (RMSE, em p.p.) de {int(f.loc['sem mudança', 'meses_teste'])} previsões, de {INICIO_TESTE:%m/%Y} em diante. "
        "Referência: prever \"sem mudança\".",
        "",
        "| Modelo | RMSE (p.p.) | Ganho sobre \"sem mudança\" |",
        "|---|---|---|",
    ]
    for nome, r in f.iterrows():
        texto.append(f"| {nome} | {br(r['rmse_pp'], 3)} | {r['ganho_vs_sem_mudanca'] * 100:+.0f}% |".replace(".", ","))
    texto += [
        "",
        "Sensibilidade ao início do teste (ganho sobre \"sem mudança\"):",
        "",
        "| Teste desde | " + " | ".join(MODELOS) + " |",
        "|---|" + "---|" * len(MODELOS),
    ]
    for _, j in janelas.iterrows():
        texto.append(f"| {int(j['teste_desde'])} | " + " | ".join(f"{j[n] * 100:+.0f}%" for n in MODELOS) + " |")
    texto += [
        "",
        "- **Leitura:** só o modelo com apenas o juro real ganha da previsão ingênua nas três janelas, por uma margem "
        "pequena. Os modelos com inércia e controles explicam melhor o passado (seção 2), mas preveem pior: sinal de "
        "excesso de ajuste com poucos dados. A inércia atrapalha porque a inadimplência tende a voltar, não a continuar. "
        "**Conclusão: usar o juro real como sinal de direção, não como previsão de quanto a inadimplência vai mudar.**",
        "",
        "## 4. Regra de alerta (direção)",
        "",
        "Regra sem nenhum parâmetro ajustado: **alerta quando o juro real ex ante está maior que 12 meses antes.** "
        "O horizonte de 6 meses veio da análise da seção 1, que usou todo o período (limitação).",
        "",
        "| Período | Meses com alerta | Inadimplência subiu em 6 meses (com alerta) | Meses sem alerta | Subiu (sem alerta) | Mudança média com / sem alerta |",
        "|---|---|---|---|---|---|",
    ]
    for rotulo, rg in (("Histórico todo", regra), ("Só o teste (2023+)", regra_teste)):
        texto.append(
            f"| {rotulo} ({rg['inicio']:%m/%Y}–{rg['fim']:%m/%Y}) | {rg['meses_com_alerta']} | {pct(rg['acerto_com_alerta'])} | "
            f"{rg['meses_sem_alerta']} | {pct(rg['subida_sem_alerta'])} | "
            f"{br(rg['mudanca_media_com_alerta'])} / {br(rg['mudanca_media_sem_alerta'])} p.p. |")
    texto += [
        "",
        "## 5. Limitações",
        "",
        "- **Correlação não prova causa.** Mesmo com controles, juros e inadimplência respondem a choques comuns.",
        f"- **Poucos ciclos:** cerca de 10 anos e ~{rob['nef_juro_real']:.0f} observações efetivamente independentes na correlação.",
        "- **Dado agregado e público:** todo o mercado tem este sinal. O valor para uma instituição está em combiná-lo com "
        "dados próprios (setor, porte, garantias, comportamento de pagamento), o que este projeto não tem.",
        "- **Juro real ex post x ex ante:** o ex post usa a inflação passada; o ex ante usa a mediana do Focus para os próximos "
        "12 meses (último valor de cada mês). Os modelos das seções 2 a 4 usam o ex ante.",
    ]
    return "\n".join(texto) + "\n"


def robustez(largo: pd.DataFrame, corr: pd.DataFrame) -> dict:
    alvo = amostra_comum(largo)
    d = com_controles(largo, pd.read_csv(ARQ_CONTROLES))
    rob = {}
    for ind, chave in (("juro_real", "juro_real"), ("selic_meta", "selic")):
        x, y = series(largo, ind, "variacao_12m")
        k = faixa_de_pico(corr, ind)[0]
        rob[f"faixa_{chave}"] = faixa_de_pico(corr, ind)
        rob[f"boot_{chave}"] = bootstrap_pico(x, y, alvo)
        rob[f"nef_{chave}"] = amostra_efetiva(x.shift(k).loc[alvo].values, y.loc[alvo].values)
    ex_ante = d.assign(juro_real=d["juro_real_ex_ante"])
    c2 = correlacoes(ex_ante)
    rob["faixa_ex_ante"] = faixa_de_pico(c2, "juro_real")
    rob["r_ex_ante"] = c2.query("indicador == 'juro_real' and base == 'variacao_12m'")["correlacao"].max()
    t = base_previsao(d)
    rob["t_inicio"], rob["t_fim"] = t.index.min(), t.index.max()
    rob["dentro"] = modelos_dentro_da_amostra(t)
    rob["fora"] = fora_da_amostra(t)
    rob["janelas"] = fora_da_amostra_janelas(t)
    simples = rob["janelas"]["só juro real"] * 100
    rob["ganho_min_simples"], rob["ganho_max_simples"] = simples.min(), simples.max()
    rob["regra"] = regra_de_alerta(t)
    rob["regra_teste"] = regra_de_alerta(t[t.index >= INICIO_TESTE])
    rob["horizontes"] = robustez_horizonte(d)
    sp = t[t["pandemia"] == 0]
    cols = [c for c in MODELOS["inércia + juro real + controles"] if c != "pandemia"]
    mp = ajustar(sp, cols)
    ic = mp.conf_int().loc["juro_real_ex_ante_var12"]
    rob["sem_pandemia"] = {"coef": mp.params["juro_real_ex_ante_var12"], "ic95_inf": ic[0], "ic95_sup": ic[1], "meses": int(mp.nobs)}
    return rob


def main() -> None:
    largo = indicadores_mensais(pd.read_csv(ARQ_SGS))
    corr = correlacoes(largo)
    reg = regressoes_nos_picos(largo, corr)
    reg.to_csv(ARQ_CSV, index=False)
    rob = robustez(largo, corr)
    rob["fora"].to_csv(RAIZ / "data" / "processed" / "validacao_fora_da_amostra.csv", index=False)
    ARQ_MD.parent.mkdir(exist_ok=True)
    ARQ_MD.write_text(relatorio(largo, corr, reg, rob), encoding="utf-8")
    print(reg.round(4).to_string(index=False))
    print(rob["fora"].round(4).to_string(index=False))
    print(f"\nRelatório: {ARQ_MD.relative_to(RAIZ)} | Tabelas: {ARQ_CSV.relative_to(RAIZ)}, validacao_fora_da_amostra.csv")


if __name__ == "__main__":
    main()
