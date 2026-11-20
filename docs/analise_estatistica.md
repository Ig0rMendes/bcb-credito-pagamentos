# Análise estatística: juros → inadimplência das empresas

> Gerado automaticamente por `src/analise_estatistica.py` em 20/11/2026. Amostra: **94 meses**, de 12/2018 a 09/2026 (a mesma para todas as defasagens).

## 1. Em quantos meses os juros "chegam" na inadimplência?

Correlação de Pearson entre os juros de *k* meses atrás e a inadimplência PJ de hoje. Defasagem com a maior correlação:

| Indicador | Base | Defasagem | Correlação |
|---|---|---|---|
| Juro real ex post | nível | **7 meses** | 0,91 |
| Juro real ex post | variação em 12 meses | **6 meses** | 0,83 |
| Selic (meta) | nível | **13 meses** | 0,87 |
| Selic (meta) | variação em 12 meses | **10 meses** | 0,78 |

## 2. Qual o tamanho do efeito? (regressão na defasagem de pico, variação em 12 meses)

| Indicador | Defasagem | Efeito de +1 p.p. nos juros | Intervalo de 95% (Newey-West) | R² | p-valor (Newey-West) |
|---|---|---|---|---|---|
| Juro real ex post | 6 meses | **0,113 p.p.** de inadimplência PJ | 0,083 a 0,143 | 0,68 | 2.8e-13 |
| Selic (meta) | 10 meses | **0,111 p.p.** de inadimplência PJ | 0,070 a 0,152 | 0,61 | 9.3e-08 |

## 3. Como ler

- Quando o **juro real** sobe 1 ponto percentual em 12 meses, a inadimplência das empresas tende a subir cerca de **0,11 ponto** em 12 meses, uns **6 meses depois**. No período, a inadimplência PJ variou entre 1,24% e 3,36%.
- O R² de 0,68 indica que a variação do juro real acompanha cerca de 68% da variação da inadimplência nesse período.
- **Newey-West:** as variações de 12 meses de meses vizinhos compartilham 11 meses de dados; o erro-padrão comum ficaria otimista demais. Mesmo corrigido, o intervalo de 95% não chega perto de zero.

## 4. Cuidados

- **Correlação não prova causa.** Juros e inadimplência respondem juntos ao ciclo da economia (pandemia, inflação, crises).
- **Amostra curta:** 94 meses cobrem poucos ciclos de juros. A defasagem de pico é uma estimativa, não uma constante.
- **Juro real ex post** compara a meta Selic do mês com a inflação **passada** de 12 meses (aproximação).
