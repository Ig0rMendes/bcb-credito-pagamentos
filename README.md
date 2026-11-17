# Crédito e pagamentos das empresas no Brasil

[![Testes](https://github.com/Ig0rMendes/bcb-credito-pagamentos/actions/workflows/testes.yml/badge.svg)](https://github.com/Ig0rMendes/bcb-credito-pagamentos/actions/workflows/testes.yml)
[![Pipeline mensal](https://github.com/Ig0rMendes/bcb-credito-pagamentos/actions/workflows/pipeline_mensal.yml/badge.svg)](https://github.com/Ig0rMendes/bcb-credito-pagamentos/actions/workflows/pipeline_mensal.yml)

> **Pergunta de negócio:** como os juros afetam a inadimplência das empresas, e como o Pix está mudando a forma como elas pagam?

Projeto em construção, em 3 etapas:

| Etapa | O que faz | Status |
|---|---|---|
| 1. Coleta via API | Python busca séries do Banco Central (APIs REST e OData, JSON), valida e salva tabelas limpas | ✅ concluída |
| 2. Nuvem | Databricks (Unity Catalog, Delta): volume → bronze → silver → gold, tudo em SQL e conferido | ✅ concluída |
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

O `pytest` também roda os SQLs de `sql/` localmente com DuckDB (um banco que funciona dentro do Python) e confere os resultados, antes de levá-los ao Databricks.

No Databricks: envie `series_sgs_longo.csv`, `pix_detalhado.parquet` e `gabarito.csv` para o volume `workspace.bcb.landing` e rode os arquivos de `sql/` em ordem.

## Estrutura

```
src/coletar_dados.py        # coleta, validação e transformação
src/gabarito.py             # valores esperados das checagens do Databricks, recalculados a cada coleta
tests/                      # testes automatizados (pytest), incluindo o SQL rodado localmente com DuckDB
sql/                        # SQL do Databricks, na ordem de execução
  01_estrutura.sql          #   schema e volume no Unity Catalog
  02_bronze.sql             #   arquivos do volume -> tabelas bronze (com colunas de auditoria)
  03_checagens_bronze.sql   #   confere as tabelas contra os números do Python
  04_silver.sql             #   indicadores mensais (pivot, IPCA 12m, juro real) e Pix com nomes claros
  05_gold.sql               #   defasagem juros -> inadimplência, correlação por defasagem, Pix por natureza e forma
  06_checagens_silver_gold.sql  # confere silver e gold contra cálculos independentes
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

## Camadas no Databricks (arquitetura medalhão)

| Camada | Tabela | Para que serve |
|---|---|---|
| Bronze | `bronze_sgs`, `bronze_pix` | Arquivos como vieram, com tipos fixados e colunas de auditoria |
| Silver | `silver_indicadores_mensais` | Um mês por linha: Selic, IPCA, IPCA 12m, juro real, inadimplência PJ/PF, concessões PJ |
| Silver | `silver_pix` | Pix com nomes claros, tipo de pagador/recebedor e marcação de mês parcial |
| Gold | `gold_defasagem_juros_inadimplencia` | Selic e juro real de 3 a 12 meses antes, ao lado da inadimplência atual |
| Gold | `gold_correlacao_defasagem` | Correlação juros × inadimplência PJ para defasagens de 0 a 24 meses |
| Gold | `gold_pix_natureza_mensal` | Valor, quantidade, ticket médio e participação por natureza, mês a mês |
| Gold | `gold_pix_empresas_forma_iniciacao` | Como empresas pagam e recebem (chave, QR Code, Pix Automático...) |

### Decisões da silver e da gold

- **Empresa vem da natureza, não de `PAG_PFPJ`:** nos dados do BCB, `PAG_PFPJ = 'PJ'` inclui o governo. Por isso o tipo de pagador e recebedor é lido da natureza (P = pessoa, B = empresa, G = governo).
- **IPCA em 12 meses composto:** inflação acumulada é produto, não soma. Em SQL: `exp(soma dos logaritmos) - 1`.
- **Juro real ex post (aproximação):** `(1 + Selic) / (1 + IPCA 12m) - 1`, comparando a meta Selic do mês com a inflação dos 12 meses anteriores.
- **Correlação em duas bases:** em nível e em variação de 12 meses. Séries com tendência longa ficam correlacionadas "de graça" no nível; a variação remove essa tendência. Se as duas apontam defasagens próximas, o resultado é mais confiável.
- **Mesma amostra para todas as defasagens:** todas as correlações usam os mesmos 94 meses (dez/2018 a set/2026), para serem comparáveis entre si.
- **Formas de iniciação do Pix:** só os códigos com descrição nos manuais do BCB foram traduzidos; `APDN` e `APES` ficam marcados como "descrição a confirmar".
- **Gabarito automático:** as checagens (`sql/03` e `sql/06`) não têm números escritos à mão. A cada coleta, `src/gabarito.py` recalcula com pandas, por outro caminho, os valores que as tabelas devem ter e grava `gabarito.csv`, que vira a tabela `bronze_gabarito`. O SQL mede as tabelas e compara. Datas também não são fixas: o "mês de referência" é o último com inadimplência publicada.
- **Tolerâncias:** contagens precisam bater exatamente; decimais têm tolerância pequena, porque motores diferentes arredondam a última casa de formas diferentes. A soma do Pix usa tolerância proporcional (1 parte em 1 trilhão do total), porque somar centenas de milhares de decimais em ordens diferentes muda os últimos centavos.
- **Trava nas checagens:** se qualquer checagem falhar, `sql/03` e `sql/06` param com erro (`raise_error`) e dizem qual falhou. No pipeline automático, isso impede que silver e gold sejam reconstruídas em cima de dados com problema. O resultado completo fica nas views `vw_checagens_bronze` e `vw_checagens_silver_gold`.
- **Testes das checagens:** o `pytest` confere que as checagens passam, que todo item do gabarito é conferido pelo SQL e que elas **param com erro** quando os dados estão incompletos (teste negativo).
- **Cuidado na leitura:** correlação não prova causa. Juros e inadimplência respondem ao ciclo econômico como um todo.

## Automação

O pipeline roda sozinho todo dia 28 (ou num clique, na aba **Actions**):

```
GitHub Actions (pipeline_mensal.yml)
  1. testa as transformações
  2. coleta os dados nas APIs do BCB e gera o gabarito
  3. testa o SQL com os dados novos (DuckDB)
  4. envia os arquivos para o volume do Databricks (Databricks CLI)
  5. dispara o Job do Databricks  ──►  carregar_bronze → checar_bronze → silver → gold → checar_silver_gold
     e só marca sucesso se o Job terminar com SUCCESS
```

- **Por que a coleta roda no GitHub, e não no Databricks:** a versão gratuita do Databricks só acessa um conjunto restrito de sites. Um workflow de teste (`teste_conexao_bcb.yml`) confirmou antes que as APIs do BCB respondem aos servidores do GitHub, incluindo o download completo do Pix.
- **O Job lê o SQL direto do GitHub** (branch `main`): o que roda na nuvem é sempre a versão versionada, sem copiar e colar.
- **Disjuntor:** se uma checagem falhar, o Job para antes de reconstruir silver e gold, e o workflow do GitHub fica vermelho com o link da execução.
- **"Terminar" não é "dar certo":** o workflow confere explicitamente se o Job terminou com `SUCCESS`, porque a CLI pode encerrar sem erro mesmo quando o Job falhou.
- **Segurança:** o token do Databricks fica nos *secrets* do GitHub (nunca no código), tem validade de 90 dias e só os escopos `files` e `jobs` (privilégio mínimo). Renovar antes de vencer: Settings → Developer → Access tokens no Databricks, e atualizar o secret `DATABRICKS_TOKEN` no GitHub.
- **Auditoria:** cada execução guarda gabarito, séries e o resultado do Job como artefato por 90 dias.
- **Testes a cada push** (`testes.yml`): sem os dados, os testes do SQL são pulados e os demais rodam.

