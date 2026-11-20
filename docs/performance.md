# Performance do Power BI: antes e depois

Objetivo: medir o efeito do desenho do modelo de dados no Power BI, comparando uma
**versão 1 "ingênua"** (tabela detalhada + tudo em DAX) com uma **versão 2 otimizada**
(tabelas gold agregadas no Databricks + modelo estrela). As duas versões têm
**exatamente a mesma página de teste**, com os mesmos 5 visuais.

## Condições do teste

- Power BI Desktop (mesma versão nas duas medições; atualização adiada de propósito)
- Modo de conexão: **Import**, conector Azure Databricks, SQL warehouse serverless (Databricks Free Edition)
- Rede: Wi-Fi 2,4 GHz (afeta só o tempo de carga; os visuais consultam a memória local)
- Data: 18/11/2026

## Página de teste (igual nas duas versões)

| # | Visual | Medidas |
|---|---|---|
| 1 | Linhas: participação no valor por natureza, mês a mês | `Participação no Valor` |
| 2 | Colunas: valor por natureza | `Valor Pix` |
| 3 | Cartão: ticket médio | `Ticket Médio` |
| 4 | Matriz: natureza × forma de iniciação (só com empresa) | `Valor Pix` |
| 5 | Linhas: Selic × inadimplência PJ | `Selic`, `Inadimplência PJ` |

## Versão 1: ingênua

**Modelo:** `silver_pix` (768.106 linhas, todas as colunas) + `silver_indicadores_mensais`.
Sem tabela calendário (hierarquia automática de datas ligada, que é o padrão).

| Métrica | Resultado |
|---|---|
| Tamanho do arquivo `.pbix` | **13,9 MB** |
| Tempo de carga (Load + 3 Refresh) | 63 s, 36 s, 78 s, 90 s → **mediana ~70 s**, faixa 36–90 s |

**Tempo dos visuais** (Performance Analyzer, 3 rodadas de "Refresh visuals", em ms):

| Visual | Rodada 1 | Rodada 2 | Rodada 3 | **Mediana** |
|---|---|---|---|---|
| Participação por natureza (linhas) | 835 | 952 | 919 | **919** |
| Valor por natureza (colunas) | 489 | 219 | 328 | **328** |
| Selic × inadimplência (linhas) | 828 | 217 | 326 | **326** |
| Ticket médio (cartão) | 571 | 970 | 217 | **571** |
| Matriz natureza × forma | 804 | 987 | 881 | **881** |

**Onde o tempo vai** (rodada 3, em ms):

| Visual | Consulta DAX | Desenho do visual | Outros (espera) | Total |
|---|---|---|---|---|
| Participação por natureza | 17 | 551 | 351 | 919 |
| Valor por natureza | 50 | 113 | 165 | 328 |
| Selic × inadimplência | 51 | 109 | 166 | 326 |
| Ticket médio | 41 | 52 | 124 | 217 |
| Matriz | 15 | 717 | 149 | 881 |

### Leitura da versão 1

- **A consulta DAX é rápida mesmo com 768 mil linhas: 15 a 51 ms.** O motor do Power BI
  (VertiPaq) comprime e consulta esse volume com folga. O gargalo **não** é o tamanho da tabela.
- **O tempo está no desenho dos visuais e na espera:** os dois visuais mais lentos são os que
  desenham mais elementos (o gráfico de linhas com 10 naturezas × 72 meses e a matriz com
  várias colunas). "Outros" é o tempo esperando os demais visuais, que rodam ao mesmo tempo.
- **Consequência para a versão 2:** trocar a tabela detalhada pela agregada deve reduzir muito
  o **tamanho do arquivo** e o **tempo de carga**, mas pouco o tempo dos visuais. Para os
  visuais, a otimização certa é no **desenho** (menos séries, menos colunas), não no modelo.

## Versão 2: otimizada

**Modelo:** as 4 tabelas **gold** (já agregadas no Databricks) + duas dimensões criadas em DAX:
`dCalendario` (um mês por linha) e `dNatureza` (natureza, tipo de pagador e de recebedor).
Modelo estrela com 5 relacionamentos (4 de muitos para um e 1 de um para um, filtro em uma direção
nos de muitos para um). **Data/hora automática desligada** (a v1 criava uma tabela de datas escondida
para cada coluna de data) e detecção automática de relacionamentos desligada (relacionamentos feitos à mão).

Conferência de que as duas versões mostram **os mesmos números**: ticket médio R$ 422,45 nas duas, e a
matriz com totais idênticos por forma de iniciação (ex.: Chave Pix R$ 32.623.868.178.148 com empresa).

| Métrica | Resultado |
|---|---|
| Tamanho do arquivo `.pbix` | **0,22 MB** |
| Tempo de carga (Load + 3 Refresh) | ~15 s, ~13 s, ~6 s, ~5 s → **mediana ~10 s** (precisão de ~2 s) |

**Tempo dos visuais** (Performance Analyzer, 3 rodadas, em ms):

| Visual | Rodada 1 | Rodada 2 | Rodada 3 | **Mediana** |
|---|---|---|---|---|
| Participação por natureza (linhas) | 493 | 415 | 542 | **493** |
| Valor por natureza (colunas) | 491 | 412 | 375 | **412** |
| Selic × inadimplência (linhas) | 489 | 410 | 374 | **410** |
| Ticket médio (cartão) | 508 | 434 | 421 | **434** |
| Matriz natureza × forma | 501 | 431 | 497 | **497** |

**Onde o tempo vai** (rodada 3, em ms):

| Visual | Consulta DAX | Desenho do visual | Outros (espera) | Total |
|---|---|---|---|---|
| Participação por natureza | 16 | 112 | 413 | 542 |
| Valor por natureza | 9 | 141 | 225 | 375 |
| Selic × inadimplência | 8 | 137 | 228 | 374 |
| Ticket médio | 6 | 203 | 212 | 421 |
| Matriz | 12 | 302 | 183 | 497 |

## Antes × depois

| Métrica | v1 ingênua | v2 otimizada | Diferença |
|---|---|---|---|
| Tamanho do arquivo | 13,95 MB | 0,22 MB | **63× menor (−98,4%)** |
| Tempo de carga (mediana) | ~70 s | ~10 s | **~7× mais rápido** |
| Visual mais lento da página (mediana das rodadas) | 919 ms | 508 ms | **−45%** |
| Consulta DAX (soma dos 5 visuais, rodada 3) | 174 ms | 51 ms | −71% (mas são milissegundos) |
| Participação por natureza (mediana) | 919 ms | 493 ms | −46% |
| Matriz natureza × forma (mediana) | 881 ms | 497 ms | −44% |
| Ticket médio (mediana) | 571 ms | 434 ms | −24% |
| Valor por natureza (mediana) | 328 ms | 412 ms | +26% (faixas se sobrepõem: 219–489 × 375–491) |
| Selic × inadimplência (mediana) | 326 ms | 410 ms | +26% (faixas se sobrepõem: 217–828 × 374–489) |

## Conclusões

1. **O maior ganho foi no tamanho e na carga, como previsto pela medição da v1.** Levar a agregação
   para o Databricks (camada gold) fez o Power BI importar ~3 mil linhas em vez de 768 mil:
   arquivo 63× menor e carga ~7× mais rápida. Na prática, é o que decide se um painel atualiza em
   segundos ou em minutos, e quanto da cota do warehouse cada atualização consome.
2. **A página ficou ~45% mais rápida**, puxada pelos dois visuais mais pesados (linhas por natureza e
   matriz), e a v2 ficou mais **estável**: todos os visuais entre ~370 e ~540 ms, contra 217 a 987 ms na v1.
3. **Nem tudo melhorou, e isso também é resultado.** Dois visuais simples ficaram com mediana maior,
   mas as faixas das duas versões se sobrepõem: com 3 rodadas, essa diferença é ruído, não piora real.
4. **A consulta DAX nunca foi o gargalo** (dezenas de milissegundos nas duas versões). O que pesa é o
   desenho e a espera entre visuais. Para as páginas finais, a regra é: poucos visuais por página e
   poucos elementos por visual.
5. **Limites da medição:** 3 rodadas por versão, Wi-Fi 2,4 GHz e warehouse compartilhado da versão
   gratuita. As diferenças grandes (tamanho, carga, visuais pesados) são claras; as pequenas, não.
