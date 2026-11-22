"""
Coleta as séries de CONTROLE usadas só na análise estatística (src/analise_estatistica.py).

Ficam fora do pipeline do Databricks de propósito: não entram nas tabelas gold nem no Power BI,
servem para testar se a relação juros -> inadimplência resiste ao ciclo econômico.

  - IBC-Br com ajuste sazonal (SGS 24364): atividade econômica mensal, a "prévia do PIB".
  - Taxa de desocupação, PNAD Contínua (SGS 24369): trimestre móvel terminado no mês.
  - Expectativa de IPCA para os próximos 12 meses (Focus, mediana suavizada): permite calcular o
    juro real EX ANTE, que é o que as empresas enxergam na hora de tomar crédito.

Saída: data/processed/controles_mensais.csv  (data, ibc_br_dessaz, desocupacao, ipca_expectativa_12m)

Uso:  python src/coletar_controles.py
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from coletar_dados import PASTA_PROCESSED, PASTA_RAW, URL_SGS, buscar_json, remover_mes_incompleto

INICIO = date(2014, 1, 1)  # um ano antes das séries principais, para caber a variação de 12 meses
SERIES_CONTROLE = {24364: "ibc_br_dessaz", 24369: "desocupacao"}
URL_FOCUS = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoInflacao12Meses"
)


def sgs_mensal(registros: list[dict], nome: str) -> pd.Series:
    df = pd.DataFrame(registros)
    datas = pd.to_datetime(df["data"], format="%d/%m/%Y")
    return pd.Series(pd.to_numeric(df["valor"]).values, index=datas, name=nome)


def focus_mensal(registros: list[dict]) -> pd.Series:
    """Último valor publicado em cada mês (a expectativa que existia no fim do mês)."""
    df = pd.DataFrame(registros)
    df["data"] = pd.to_datetime(df["Data"])
    df = df.sort_values("data")
    mensal = df.groupby(df["data"].dt.to_period("M"))["Mediana"].last()
    mensal.index = mensal.index.to_timestamp()
    return mensal.rename("ipca_expectativa_12m")


def main() -> None:
    hoje = date.today()
    PASTA_RAW.mkdir(parents=True, exist_ok=True)
    colunas = []
    for codigo, nome in SERIES_CONTROLE.items():
        params = {"formato": "json", "dataInicial": INICIO.strftime("%d/%m/%Y"), "dataFinal": hoje.strftime("%d/%m/%Y")}
        registros = buscar_json(URL_SGS.format(codigo=codigo), params)
        (PASTA_RAW / f"sgs_{codigo}_{nome}.json").write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
        colunas.append(sgs_mensal(registros, nome))
        print(f"SGS {codigo} ({nome}): {len(registros)} meses")

    params = {
        "$filter": f"Indicador eq 'IPCA' and Suavizada eq 'S' and baseCalculo eq 0 and Data ge '{INICIO:%Y-%m-%d}'",
        "$select": "Data,Mediana",
        "$orderby": "Data asc",
        "$top": "20000",
        "$format": "json",
    }
    focus = buscar_json(URL_FOCUS, params).get("value", [])
    (PASTA_RAW / "focus_ipca_12m.json").write_text(json.dumps(focus, ensure_ascii=False), encoding="utf-8")
    colunas.append(focus_mensal(focus))
    print(f"Focus IPCA 12 meses: {len(focus)} registros diários")

    tabela = pd.concat(colunas, axis=1).sort_index()
    tabela.index.name = "data"
    tabela = remover_mes_incompleto(tabela.reset_index(), hoje)
    tabela.to_csv(PASTA_PROCESSED / "controles_mensais.csv", index=False, float_format="%.4f")
    print(f"Salvo: data/processed/controles_mensais.csv ({len(tabela)} meses)")


if __name__ == "__main__":
    main()
