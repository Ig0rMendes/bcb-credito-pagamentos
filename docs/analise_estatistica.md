# Análise estatística: juros → inadimplência das empresas

> Gerado automaticamente por `src/analise_estatistica.py` em 22/11/2026.

**Inadimplência PJ** = série SGS 21083: percentual da carteira de crédito a pessoas jurídicas com atraso acima de 90 dias. É uma razão (atrasos ÷ carteira), então também muda quando a carteira cresce ou encolhe.

## Resumo honesto

- **A relação existe e resiste a controles, mas é imprecisa.** O juro real ajuda a explicar a inadimplência dos meses seguintes mesmo descontando atividade, desemprego, concessões de crédito e a pandemia. Sem os meses de 2020–2021, porém, o efeito fica perto de zero.
- **Como previsão de magnitude, ajuda pouco.** Fora da amostra, só o modelo mais simples (apenas o juro real) erra menos que a previsão ingênua "vai ficar como está", e por pouco (10% a 16% conforme a janela). Somar inércia e controles piora a previsão.
- **Serve como alerta de direção.** Quando o juro real ex ante subiu em 12 meses, a inadimplência subiu nos 6 meses seguintes em 72% dos meses (contra 27% sem o alerta). No período de teste, que não foi usado para escolher nada além do horizonte, foram 83% contra 38%.

## 1. Correlação por defasagem (descritivo)

Amostra fixa de **94 meses** (12/2018 a 09/2026), a mesma para as 25 defasagens, com as duas séries em variação de 12 meses.

| Indicador | Pico | Faixa (r até 0,05 abaixo do pico) | Pico no bootstrap (90%) | r no pico | r, intervalo de 95% (bootstrap) | Tamanho efetivo da amostra |
|---|---|---|---|---|---|---|
| Juro real ex post | 6 meses | 4 a 8 meses | 0 a 7 meses | 0,83 | 0,44 a 0,92 | ~9 meses |
| Selic (meta) | 10 meses | 8 a 13 meses | 5 a 14 meses | 0,78 | 0,53 a 0,86 | ~8 meses |

- **Por que o tamanho efetivo é tão pequeno:** variações de 12 meses em meses vizinhos repetem 11 meses de dados. Pela fórmula de Bartlett, os 94 pontos valem cerca de 9 observações independentes. Por isso o r alto (0,83) tem um intervalo largo.
- **A defasagem é uma faixa, não um número.** O bootstrap de blocos de 12 meses (2000 reamostragens) coloca o pico do juro real entre 0 e 7 meses em 90% das vezes.
- **Seleção:** o pico foi escolhido entre 25 defasagens × 2 indicadores × 2 bases. Por isso os p-valores da regressão no pico (abaixo) são otimistas; a validação fora da amostra (seção 3) é o teste que vale.

Regressão na defasagem de pico (variação em 12 meses dos dois lados, erro-padrão Newey-West com 12 defasagens):

| Indicador | Defasagem | +1 p.p. na variação em 12 meses dos juros → variação em 12 meses da inadimplência | Intervalo de 95% | R² |
|---|---|---|---|---|
| Juro real ex post | 6 meses | 0,113 p.p. | 0,083 a 0,143 | 0,68 |
| Selic (meta) | 10 meses | 0,111 p.p. | 0,070 a 0,152 | 0,61 |

Com o **juro real ex ante** (Selic sobre a inflação esperada no Focus), o pico fica em 9 meses (faixa de 6 a 12) e r = 0,77.

## 2. O juro real ainda importa depois da inércia e dos controles?

Alvo: **mudança da inadimplência nos 6 meses seguintes**, só com o que se sabia no mês (nada do alvo é conhecido na hora). 112 meses, de 12/2016 a 03/2026. Erro-padrão Newey-West com 6 defasagens.

| Modelo | R² ajustado | +1 p.p. na variação em 12 meses do juro real ex ante → p.p. de inadimplência em 6 meses | Intervalo de 95% |
|---|---|---|---|
| só juro real | 0,45 | 0,075 | 0,046 a 0,105 |
| inércia | 0,05 | — | — |
| inércia + juro real | 0,47 | 0,088 | 0,048 a 0,127 |
| inércia + juro real + controles | 0,60 | 0,080 | 0,037 a 0,123 |

- **Inércia** = quanto a inadimplência mudou nos 6 meses anteriores. **Controles** = atividade (IBC-Br, variação em 12 meses), desemprego (PNAD, variação em 12 meses), concessões de crédito PJ acumuladas em 12 meses (variação em 12 meses) e um indicador da pandemia (mar/2020 a dez/2021).
- **Sem os meses da pandemia**, o efeito cai para 0,049 p.p. (intervalo de 0,003 a 0,095, 90 meses): continua positivo, mas perto de zero. Boa parte da força da relação vem de 2020–2022.
- **Outros horizontes** (mesmo modelo completo):

| Horizonte | Efeito | Intervalo de 95% |
|---|---|---|
| 3 meses | 0,051 | 0,029 a 0,074 |
| 6 meses | 0,080 | 0,037 a 0,123 |
| 9 meses | 0,098 | 0,050 a 0,146 |
| 12 meses | 0,086 | 0,040 a 0,132 |

## 3. Prevê fora da amostra?

Janela expansiva: em cada mês do teste, o modelo é treinado só com resultados que já eram conhecidos naquele mês. Erro médio (RMSE, em p.p.) de 39 previsões, de 01/2023 em diante. Referência: prever "sem mudança".

| Modelo | RMSE (p.p.) | Ganho sobre "sem mudança" |
|---|---|---|
| sem mudança | 0,323 | +0% |
| só juro real | 0,291 | +10% |
| inércia | 0,377 | -17% |
| inércia + juro real | 0,362 | -12% |
| inércia + juro real + controles | 0,370 | -15% |

Sensibilidade ao início do teste (ganho sobre "sem mudança"):

| Teste desde | só juro real | inércia | inércia + juro real | inércia + juro real + controles |
|---|---|---|---|---|
| 2022 | +16% | -29% | -10% | -11% |
| 2023 | +10% | -17% | -12% | -15% |
| 2024 | +14% | -9% | +18% | +33% |

- **Leitura:** só o modelo com apenas o juro real ganha da previsão ingênua nas três janelas, por uma margem pequena. Os modelos com inércia e controles explicam melhor o passado (seção 2), mas preveem pior: sinal de excesso de ajuste com poucos dados. A inércia atrapalha porque a inadimplência tende a voltar, não a continuar. **Conclusão: usar o juro real como sinal de direção, não como previsão de quanto a inadimplência vai mudar.**

## 4. Regra de alerta (direção)

Regra sem nenhum parâmetro ajustado: **alerta quando o juro real ex ante está maior que 12 meses antes.** O horizonte de 6 meses veio da análise da seção 1, que usou todo o período (limitação).

| Período | Meses com alerta | Inadimplência subiu em 6 meses (com alerta) | Meses sem alerta | Subiu (sem alerta) | Mudança média com / sem alerta |
|---|---|---|---|---|---|
| Histórico todo (12/2016–03/2026) | 50 | 72% | 62 | 27% | 0,19 / -0,20 p.p. |
| Só o teste (2023+) (01/2023–03/2026) | 23 | 83% | 16 | 38% | 0,26 / -0,02 p.p. |

## 5. Limitações

- **Correlação não prova causa.** Mesmo com controles, juros e inadimplência respondem a choques comuns.
- **Poucos ciclos:** cerca de 10 anos e ~9 observações efetivamente independentes na correlação.
- **Dado agregado e público:** todo o mercado tem este sinal. O valor para uma instituição está em combiná-lo com dados próprios (setor, porte, garantias, comportamento de pagamento), o que este projeto não tem.
- **Juro real ex post x ex ante:** o ex post usa a inflação passada; o ex ante usa a mediana do Focus para os próximos 12 meses (último valor de cada mês). Os modelos das seções 2 a 4 usam o ex ante.
