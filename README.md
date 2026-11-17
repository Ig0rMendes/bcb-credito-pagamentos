# Crédito e pagamentos das empresas no Brasil

> **Pergunta de negócio:** como os juros afetam a inadimplência das empresas, e como o Pix está mudando a forma como elas pagam?

Projeto em construção, em 3 etapas:

| Etapa | O que faz | Status |
|---|---|---|
| 1. Coleta via API | Python busca séries do Banco Central (APIs REST e OData, JSON), valida e salva tabelas limpas | ✅ concluída |
| 2. Nuvem | Databricks (Unity Catalog, Delta): arquivos no volume → camada bronze ✅ → silver e gold com SQL | 🔄 em andamento |
| 3. Painel | Power BI com análise de defasagem juros → inadimplência e recomendações | ⏳ |

## Fontes de dados (públicas)

| Série | Código SGS | Unidade |
|---|---|---|
| Meta Selic definida pelo Copom | 432 | % a.a. |
| IPCA – variação mensal | 433 | % a.m. |
| Inadimplência da carteira de crédito – Pessoas jurídicas – Total | 21083 | % |
| Inadimplência da carteira de crédito – Pessoas físicas – Total | 21084 | % |
| Concessões de crédito – Pessoas jurídicas – Total | 20632 | R$ milhões |
| Estatísticas de transações Pix (por natureza: P2P, P2B, B2B...) | API Pix Dados Abertos | R$ e quantidade |

Fontes: [SGS – Banco Central](https://www3.bcb.gov.br/sgspub) e [Portal de Dados Abertos do BCB](https://dadosabertos.bcb.gov.br).

## Como rodar

```bash
pip install -r requirements.txt
python src/coletar_dados.py   # coleta (precisa de internet)
pytest                         # testes das transformações (não precisam de internet)
```

No Databricks: envie `series_sgs_longo.csv` e `pix_detalhado.parquet` para o volume `workspace.bcb.landing` e rode os arquivos de `sql/` em ordem.

## Estrutura

```
src/coletar_dados.py        # coleta, validação e transformação
tests/                      # testes automatizados (pytest)
sql/                        # SQL do Databricks, na ordem de execução
  01_estrutura.sql          #   schema e volume no Unity Catalog
  02_bronze.sql             #   arquivos do volume -> tabelas bronze (com colunas de auditoria)
  03_checagens_bronze.sql   #   confere as tabelas contra os números do Python
data/raw/                   # JSON original da API (auditoria)
data/processed/             # CSV/Parquet limpos, prontos para o Databricks
```

## Decisões de tratamento

- **Séries diárias → mensais:** a meta Selic é diária; uso o último valor de cada mês.
- **Limite da API:** consultas de séries diárias são quebradas em blocos de até 10 anos.
- **Mês incompleto fora:** o mês corrente é descartado em todas as séries (a meta Selic de novembro seria só o valor do dia da coleta).
- **Pix – uma requisição só:** na API `EstatisticasTransacoesPix`, o parâmetro `Database=AAAAMM` funciona como "a partir de": `Database=202208` devolve de 2022-08 até o último mês publicado. Por isso o script faz **uma** requisição (`Database=202011`) e usa a coluna `AnoMes` de cada linha como o mês. (A 1ª versão pedia mês a mês e repetia os mesmos meses em cada resposta. Descobri isso conferindo os JSONs salvos em `data/raw/`.)
- **Pix – resumo:** valor e quantidade por mês e natureza (P2P, P2B, B2B...) e participação de cada natureza no valor total do mês.
- **Pix – nov/2020:** o Pix começou a funcionar no meio do mês, então nov/2020 é um mês parcial e não deve ser comparado com os demais.
- **Pix em Parquet para a nuvem:** o `pix_detalhado.csv` tem ~80 MB e o upload pelo navegador falhava. O script também grava `pix_detalhado.parquet` (~12 MB, formato colunar e comprimido, com os tipos das colunas). É ele que vai para o Databricks.
- **Arquivos grandes fora do Git:** o JSON do Pix (~200 MB) e os arquivos `pix_detalhado.*` estão no `.gitignore` e são gerados de novo pelo script.
- **JSON original preservado** em `data/raw/` para que qualquer número possa ser auditado.
