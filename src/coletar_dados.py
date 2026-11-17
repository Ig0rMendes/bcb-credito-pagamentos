"""
Coleta de dados públicos do Banco Central do Brasil (BCB) via API.

Duas fontes:
1. SGS (Sistema Gerenciador de Séries Temporais): séries como Selic, inadimplência e concessões de crédito.
   Endereço: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json
2. Pix Dados Abertos (API OData): estatísticas mensais de transações Pix por tipo (P2P, P2B, B2B...).
   Endereço: https://olinda.bcb.gov.br/olinda/servico/Pix_DadosAbertos/versao/v1/odata/

Saídas:
- data/raw/       -> o JSON exatamente como a API devolveu (para auditoria e reprocessamento)
- data/processed/ -> tabelas limpas (CSV/Parquet) e o gabarito.csv das checagens do Databricks

Como rodar (na pasta do projeto):
    pip install -r requirements.txt
    python src/coletar_dados.py
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from gabarito import gerar_gabarito

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_RAW = PASTA_PROJETO / "data" / "raw"
PASTA_PROCESSED = PASTA_PROJETO / "data" / "processed"

DATA_INICIAL = date(2015, 1, 1)  # 10+ anos: cobre ciclos de alta e queda de juros

# Séries do SGS. Códigos conferidos no portal de dados abertos do BCB (dadosabertos.bcb.gov.br).
SERIES_SGS = {
    432: {"nome": "selic_meta", "descricao": "Meta Selic definida pelo Copom", "unidade": "% a.a.", "frequencia": "diaria"},
    433: {"nome": "ipca_mensal", "descricao": "IPCA - variação mensal", "unidade": "% a.m.", "frequencia": "mensal"},
    21083: {"nome": "inadimplencia_pj", "descricao": "Inadimplência da carteira de crédito - Pessoas jurídicas - Total", "unidade": "%", "frequencia": "mensal"},
    21084: {"nome": "inadimplencia_pf", "descricao": "Inadimplência da carteira de crédito - Pessoas físicas - Total", "unidade": "%", "frequencia": "mensal"},
    20632: {"nome": "concessoes_pj", "descricao": "Concessões de crédito - Pessoas jurídicas - Total", "unidade": "R$ milhões", "frequencia": "mensal"},
}

URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
URL_PIX = (
    "https://olinda.bcb.gov.br/olinda/servico/Pix_DadosAbertos/versao/v1/odata/"
    "EstatisticasTransacoesPix(Database=@Database)"
)
PIX_INICIO = (2020, 11)  # o Pix começou a operar em novembro de 2020

# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------


# Identificação honesta do cliente. Sem isso, o requests se apresenta como "python-requests/x.y",
# e alguns sistemas de proteção contra robôs respondem com uma página HTML em vez do JSON
# (aconteceu na 1ª execução no GitHub Actions, fora do Brasil).
CABECALHOS = {
    "User-Agent": "bcb-credito-pagamentos/1.0 (projeto de portfolio; +https://github.com/Ig0rMendes/bcb-credito-pagamentos)",
    "Accept": "application/json",
}


def ler_json(resposta: requests.Response) -> list | dict:
    """Converte a resposta em JSON. Se não for JSON, o erro mostra O QUE veio (status, tipo e começo do texto)."""
    try:
        return resposta.json()
    except ValueError as erro:
        inicio = resposta.text[:300].replace("\n", " ")
        raise ValueError(
            f"a resposta não é JSON (HTTP {resposta.status_code}, "
            f"Content-Type: {resposta.headers.get('Content-Type', '?')}, {len(resposta.content)} bytes). "
            f"Início da resposta: {inicio!r}"
        ) from erro


def buscar_json(url: str, params: dict, tentativas: int = 3, timeout: int = 60) -> list | dict:
    """Faz a requisição GET e devolve o JSON. Tenta de novo se a API falhar (ela às vezes oscila)."""
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(url, params=params, timeout=timeout, headers=CABECALHOS)
            resposta.raise_for_status()
            return ler_json(resposta)
        except (requests.RequestException, ValueError) as erro:
            if tentativa == tentativas:
                raise RuntimeError(f"Falha ao acessar {url} com {params}: {erro}") from erro
            espera = 2 * tentativa
            print(f"  aviso: tentativa {tentativa} falhou ({erro}). Tentando de novo em {espera}s...")
            time.sleep(espera)
    return []  # nunca chega aqui; só para o editor não reclamar


def periodos_de_ate_10_anos(inicio: date, fim: date) -> list[tuple[date, date]]:
    """O BCB limita consultas de séries DIÁRIAS a 10 anos por requisição. Esta função quebra o período em blocos."""
    blocos, atual = [], inicio
    while atual <= fim:
        fim_bloco = min(date(atual.year + 9, 12, 31), fim)
        blocos.append((atual, fim_bloco))
        atual = date(fim_bloco.year + 1, 1, 1)
    return blocos


def validar_colunas(registros: list[dict], obrigatorias: list[str], fonte: str) -> None:
    """Para tudo se a API não mandou dados ou mudou o nome de algum campo.

    Sem isso, um campo renomeado viraria uma coluna vazia, as linhas seriam descartadas
    e o script "terminaria com sucesso" sem nenhum dado.
    """
    if not registros:
        raise ValueError(f"{fonte}: a API não devolveu nenhum registro.")
    faltando = [c for c in obrigatorias if c not in registros[0]]
    if faltando:
        raise ValueError(f"{fonte}: faltam as colunas {faltando}. A API mandou: {list(registros[0])}")


def meses_faltando(datas: pd.Series) -> list[str]:
    """Lista os meses que deveriam existir entre o primeiro e o último, mas não vieram (formato AAAA-MM)."""
    presentes = pd.DatetimeIndex(datas.unique())
    esperados = pd.date_range(presentes.min(), presentes.max(), freq="MS")  # MS = 1º dia de cada mês
    return [f"{d:%Y-%m}" for d in esperados.difference(presentes)]


def avisar_meses_faltando(datas: pd.Series, fonte: str) -> None:
    """Só avisa (não para): um mês faltando não impede a análise, mas você precisa saber dele."""
    faltando = meses_faltando(datas)
    if faltando:
        print(f"  ATENÇÃO {fonte}: {len(faltando)} mês(es) sem dados: {faltando}")


def sgs_para_dataframe(registros: list[dict], codigo: int) -> pd.DataFrame:
    """Converte a resposta do SGS ([{"data": "dd/mm/aaaa", "valor": "x.xx"}, ...]) em tabela."""
    validar_colunas(registros, ["data", "valor"], f"SGS {codigo}")
    df = pd.DataFrame(registros, columns=["data", "valor"])
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")  # a API devolve o valor como texto
    info = SERIES_SGS[codigo]
    df["codigo_sgs"] = codigo
    df["serie"] = info["nome"]
    df["unidade"] = info["unidade"]
    return df.dropna(subset=["valor"])


def diaria_para_mensal(df: pd.DataFrame) -> pd.DataFrame:
    """Para séries diárias (como a meta Selic), fica com o último valor de cada mês."""
    df = df.sort_values("data")
    mensal = df.groupby(df["data"].dt.to_period("M")).last(numeric_only=False).reset_index(drop=True)
    mensal["data"] = mensal["data"].dt.to_period("M").dt.to_timestamp()  # padroniza para o 1º dia do mês
    return mensal


def remover_mes_incompleto(df: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """Tira o mês corrente: ele ainda não terminou (ex.: a meta Selic de novembro seria só o valor do dia 8)."""
    return df[df["data"] < pd.Timestamp(hoje.year, hoje.month, 1)].reset_index(drop=True)


def pix_para_dataframe(registros: list[dict], hoje: date) -> pd.DataFrame:
    """Converte a resposta da API do Pix em tabela.

    Atenção: o parâmetro Database da API funciona como "a partir de" (Database=202208 devolve
    de 2022-08 até o último mês publicado). Por isso o mês de cada linha vem da coluna AnoMes,
    e nunca do mês que foi pedido na requisição.
    """
    validar_colunas(registros, ["AnoMes", "NATUREZA", "VALOR", "QUANTIDADE"], "Pix")
    df = pd.DataFrame(registros)
    df["ano_mes"] = df["AnoMes"].astype(int).astype(str)
    df["data"] = pd.to_datetime(df["ano_mes"], format="%Y%m")
    df = remover_mes_incompleto(df, hoje)
    return df.drop(columns=["AnoMes"])


def resumir_pix(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega as transações Pix por mês e natureza (P2P, P2B, B2B...): valor total e quantidade."""
    resumo = (
        df.groupby(["ano_mes", "NATUREZA"], as_index=False)[["VALOR", "QUANTIDADE"]].sum()
        .rename(columns={"NATUREZA": "natureza", "VALOR": "valor_reais", "QUANTIDADE": "quantidade"})
    )
    resumo["data"] = pd.to_datetime(resumo["ano_mes"], format="%Y%m")
    total_mes = resumo.groupby("ano_mes")["valor_reais"].transform("sum")
    resumo["participacao_valor"] = resumo["valor_reais"] / total_mes
    return resumo[["data", "ano_mes", "natureza", "valor_reais", "quantidade", "participacao_valor"]]


# ---------------------------------------------------------------------------
# Coleta
# ---------------------------------------------------------------------------


def coletar_sgs(hoje: date) -> pd.DataFrame:
    tabelas = []
    for codigo, info in SERIES_SGS.items():
        print(f"SGS {codigo} - {info['descricao']}")
        registros = []
        blocos = periodos_de_ate_10_anos(DATA_INICIAL, hoje) if info["frequencia"] == "diaria" else [(DATA_INICIAL, hoje)]
        for ini, fim in blocos:
            params = {"formato": "json", "dataInicial": ini.strftime("%d/%m/%Y"), "dataFinal": fim.strftime("%d/%m/%Y")}
            registros += buscar_json(URL_SGS.format(codigo=codigo), params)

        (PASTA_RAW / f"sgs_{codigo}_{info['nome']}.json").write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
        df = sgs_para_dataframe(registros, codigo)
        if info["frequencia"] == "diaria":
            df = diaria_para_mensal(df)
        df = remover_mes_incompleto(df, hoje)
        avisar_meses_faltando(df["data"], f"SGS {codigo}")
        print(f"  {len(df)} meses, de {df['data'].min():%m/%Y} a {df['data'].max():%m/%Y}")
        tabelas.append(df)
    return pd.concat(tabelas, ignore_index=True)


def coletar_pix(hoje: date) -> pd.DataFrame:
    # Uma única requisição: Database = mês inicial devolve todos os meses dali em diante.
    # (Na 1ª versão eu pedia mês a mês, e cada resposta repetia todos os meses seguintes.)
    inicio = f"{PIX_INICIO[0]}{PIX_INICIO[1]:02d}"
    params = {"@Database": f"'{inicio}'", "$format": "json"}
    print(f"  Baixando Pix desde {inicio} (arquivo grande, ~200 MB; pode levar alguns minutos)...")
    resposta = buscar_json(URL_PIX, params, timeout=300)
    registros = resposta.get("value", []) if isinstance(resposta, dict) else []
    if not registros:
        return pd.DataFrame()
    (PASTA_RAW / "pix").mkdir(exist_ok=True)
    (PASTA_RAW / "pix" / f"pix_desde_{inicio}.json").write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    df = pix_para_dataframe(registros, hoje)
    avisar_meses_faltando(df["data"], "Pix")
    print(f"  {len(df)} linhas, {df['ano_mes'].nunique()} meses, de {df['data'].min():%m/%Y} a {df['data'].max():%m/%Y}")
    return df


def main() -> None:
    PASTA_RAW.mkdir(parents=True, exist_ok=True)
    PASTA_PROCESSED.mkdir(parents=True, exist_ok=True)
    hoje = date.today()

    print("== Séries do SGS ==")
    sgs = coletar_sgs(hoje)
    sgs.to_csv(PASTA_PROCESSED / "series_sgs_longo.csv", index=False)
    largo = sgs.pivot_table(index="data", columns="serie", values="valor").reset_index()
    largo.to_csv(PASTA_PROCESSED / "series_sgs_mensal.csv", index=False)

    print("== Estatísticas do Pix ==")
    pix = coletar_pix(hoje)
    if pix.empty:
        print("Nenhum dado de Pix retornado. Confira a conexão e rode de novo.")
    else:
        print(f"  Colunas recebidas: {list(pix.columns)}")
        pix.to_csv(PASTA_PROCESSED / "pix_detalhado.csv", index=False)  # para abrir e conferir no Excel
        # Parquet: mesmo conteúdo, ~7x menor e com os tipos das colunas gravados no arquivo.
        # É este que vai para o Databricks (o CSV de ~80 MB falhava no upload pelo navegador).
        pix.assign(data=pix["data"].dt.date).to_parquet(PASTA_PROCESSED / "pix_detalhado.parquet", index=False)
        resumir_pix(pix).to_csv(PASTA_PROCESSED / "pix_por_natureza.csv", index=False)

        # Valores esperados das checagens do Databricks, recalculados a cada coleta
        gabarito = gerar_gabarito(sgs, pix)
        gabarito.to_csv(PASTA_PROCESSED / "gabarito.csv", index=False)
        print(f"  Gabarito: {len(gabarito)} checagens em gabarito.csv")

    print(f"\nPronto! Arquivos em: {PASTA_PROCESSED}")


if __name__ == "__main__":
    main()
