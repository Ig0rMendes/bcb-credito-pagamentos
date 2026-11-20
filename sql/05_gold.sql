-- =============================================================================
-- 05_gold.sql
-- Camada GOLD: tabelas prontas para responder à pergunta de negócio no Power BI.
--   1) gold_defasagem_juros_inadimplencia  juros de k meses atrás ao lado da inadimplência de hoje
--   2) gold_correlacao_defasagem           em quantos meses os juros "chegam" na inadimplência?
--   3) gold_pix_natureza_mensal            quem paga quem, mês a mês
--   4) gold_pix_empresas_forma_iniciacao   como as empresas pagam e recebem
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1) Defasagem: a Selic de 3, 6, 9 e 12 meses atrás ao lado da inadimplência atual
-- -----------------------------------------------------------------------------
-- Ideia: juros sobem hoje, mas a empresa só atrasa a parcela meses depois (o crédito
-- novo fica caro, o caixa aperta, as dívidas pós-fixadas pesam). LAG(x, k) pega o valor
-- de x k linhas antes; como a silver tem exatamente um mês por linha, sem buracos
-- (conferido em 03 e 06), k linhas = k meses.

CREATE OR REPLACE TABLE workspace.bcb.gold_defasagem_juros_inadimplencia
COMMENT 'Selic e juro real com defasagens de 3 a 12 meses, ao lado da inadimplência atual'
AS
WITH base AS (
  SELECT
    *,
    juro_real_ex_post - LAG(juro_real_ex_post, 12) OVER (ORDER BY data) AS juro_real_var_12m
  FROM workspace.bcb.silver_indicadores_mensais
)
SELECT
  data,
  selic_meta,
  LAG(selic_meta, 3)  OVER w AS selic_3m_antes,
  LAG(selic_meta, 6)  OVER w AS selic_6m_antes,
  LAG(selic_meta, 9)  OVER w AS selic_9m_antes,
  LAG(selic_meta, 12) OVER w AS selic_12m_antes,
  juro_real_ex_post,
  LAG(juro_real_ex_post, 6)  OVER w AS juro_real_6m_antes,
  LAG(juro_real_ex_post, 12) OVER w AS juro_real_12m_antes,
  -- Para a regressão do painel: variação de 12 meses do juro real, 6 meses antes (defasagem de pico)
  LAG(juro_real_var_12m, 6) OVER w AS juro_real_var_12m_6m_antes,
  inadimplencia_pj,
  inadimplencia_pj - LAG(inadimplencia_pj, 12) OVER w AS inadimplencia_pj_var_12m,  -- em pontos percentuais
  -- Mesma amostra comum da correlação (24 meses de defasagem + 12 da variação + 11 do IPCA 12m),
  -- para o painel e o relatório estatístico usarem exatamente os mesmos meses
  mes_seq >= MIN(mes_seq) OVER () + 24 + 12 + 11 AND inadimplencia_pj IS NOT NULL AS na_amostra_comum,
  inadimplencia_pf,
  concessoes_pj
FROM base
WINDOW w AS (ORDER BY data);


-- -----------------------------------------------------------------------------
-- 2) Correlação para cada defasagem de 0 a 24 meses
-- -----------------------------------------------------------------------------
-- Para cada k: correlação entre os juros do mês (t - k) e a inadimplência PJ do mês t.
-- A defasagem com a maior correlação sugere quanto tempo o efeito leva para aparecer.
--
-- Duas bases, de propósito:
--   'nivel'         compara os valores como estão (ex.: Selic 13,75% x inadimplência 3,1%)
--   'variacao_12m'  compara as mudanças em 12 meses (ex.: Selic +2 p.p. x inadimplência +0,4 p.p.)
-- Séries que só sobem ou só descem juntas por anos dão correlação alta "de graça" no nível.
-- A variação em 12 meses tira essa tendência. Se as duas bases apontam a mesma defasagem,
-- o resultado é mais confiável. Lembrete: correlação não prova causa (a economia como um todo
-- mexe nas duas séries).

CREATE OR REPLACE TABLE workspace.bcb.gold_correlacao_defasagem
COMMENT 'Correlação entre juros defasados (0 a 24 meses) e inadimplência PJ, em nível e em variação de 12 meses'
AS
WITH base AS (
  SELECT
    mes_seq,
    selic_meta,
    juro_real_ex_post,
    inadimplencia_pj,
    selic_meta        - LAG(selic_meta, 12)        OVER (ORDER BY mes_seq) AS selic_var_12m,
    juro_real_ex_post - LAG(juro_real_ex_post, 12) OVER (ORDER BY mes_seq) AS juro_real_var_12m,
    inadimplencia_pj  - LAG(inadimplencia_pj, 12)  OVER (ORDER BY mes_seq) AS inadimplencia_pj_var_12m
  FROM workspace.bcb.silver_indicadores_mensais
),
defasagens AS (
  SELECT explode(sequence(0, 24)) AS defasagem_meses
),
-- Mesma amostra para todas as defasagens: só entram meses t que têm dados para TODAS
-- (24 meses de defasagem + 12 da variação + 11 para o IPCA em 12 meses do juro real).
-- Sem isso, k = 0 usaria mais meses que k = 24, e as correlações não seriam comparáveis.
inicio AS (
  SELECT MIN(mes_seq) + 24 + 12 + 11 AS primeiro_mes_seq FROM base
),
pares AS (                       -- cada mês t ao lado do mês t - k
  SELECT
    d.defasagem_meses,
    juros.selic_meta, juros.juro_real_ex_post, juros.selic_var_12m, juros.juro_real_var_12m,
    hoje.inadimplencia_pj, hoje.inadimplencia_pj_var_12m
  FROM defasagens d
  CROSS JOIN inicio
  JOIN base hoje  ON hoje.inadimplencia_pj IS NOT NULL AND hoje.mes_seq >= inicio.primeiro_mes_seq
  JOIN base juros ON juros.mes_seq = hoje.mes_seq - d.defasagem_meses
)
SELECT defasagem_meses, 'selic_meta' AS indicador_juros, 'nivel' AS base,
       ROUND(CORR(selic_meta, inadimplencia_pj), 4) AS correlacao,
       COUNT_IF(selic_meta IS NOT NULL AND inadimplencia_pj IS NOT NULL) AS meses_usados
FROM pares GROUP BY defasagem_meses
UNION ALL
SELECT defasagem_meses, 'selic_meta', 'variacao_12m',
       ROUND(CORR(selic_var_12m, inadimplencia_pj_var_12m), 4),
       COUNT_IF(selic_var_12m IS NOT NULL AND inadimplencia_pj_var_12m IS NOT NULL)
FROM pares GROUP BY defasagem_meses
UNION ALL
SELECT defasagem_meses, 'juro_real_ex_post', 'nivel',
       ROUND(CORR(juro_real_ex_post, inadimplencia_pj), 4),
       COUNT_IF(juro_real_ex_post IS NOT NULL AND inadimplencia_pj IS NOT NULL)
FROM pares GROUP BY defasagem_meses
UNION ALL
SELECT defasagem_meses, 'juro_real_ex_post', 'variacao_12m',
       ROUND(CORR(juro_real_var_12m, inadimplencia_pj_var_12m), 4),
       COUNT_IF(juro_real_var_12m IS NOT NULL AND inadimplencia_pj_var_12m IS NOT NULL)
FROM pares GROUP BY defasagem_meses;


-- -----------------------------------------------------------------------------
-- 3) Pix por natureza, mês a mês
-- -----------------------------------------------------------------------------
-- Agrega a silver (768 mil linhas) para ~700 linhas: o Power BI fica leve e rápido.
-- ticket_medio = valor médio de cada Pix (R$).
-- participação = fatia do mês (soma 100% dentro de cada mês).

CREATE OR REPLACE TABLE workspace.bcb.gold_pix_natureza_mensal
COMMENT 'Valor, quantidade, ticket médio e participação do Pix por natureza e mês'
AS
WITH agregado AS (
  SELECT
    ano_mes, data, mes_parcial, natureza, pagador_tipo, recebedor_tipo, envolve_empresa,
    SUM(valor)      AS valor,
    SUM(quantidade) AS quantidade
  FROM workspace.bcb.silver_pix
  GROUP BY ano_mes, data, mes_parcial, natureza, pagador_tipo, recebedor_tipo, envolve_empresa
)
SELECT
  *,
  ROUND(valor / NULLIF(quantidade, 0), 2)                                                      AS ticket_medio,
  ROUND(valor      / SUM(valor)      OVER (PARTITION BY ano_mes), 6)                  AS participacao_valor,
  ROUND(quantidade / SUM(quantidade) OVER (PARTITION BY ano_mes), 6)                  AS participacao_quantidade
FROM agregado;


-- -----------------------------------------------------------------------------
-- 4) Como as empresas pagam e recebem: natureza x forma de iniciação
-- -----------------------------------------------------------------------------
-- Só transações em que uma empresa paga ou recebe. Ex.: crescimento do QR Code dinâmico
-- no P2B indica empresas cobrando clientes com Pix (no lugar de boleto/cartão).

CREATE OR REPLACE TABLE workspace.bcb.gold_pix_empresas_forma_iniciacao
COMMENT 'Pix com empresa como pagadora ou recebedora, por natureza e forma de iniciação, mês a mês'
AS
WITH agregado AS (
  SELECT
    ano_mes, data, mes_parcial, natureza, pagador_tipo, recebedor_tipo,
    forma_iniciacao, forma_iniciacao_descricao,
    SUM(valor)      AS valor,
    SUM(quantidade) AS quantidade
  FROM workspace.bcb.silver_pix
  WHERE envolve_empresa
  GROUP BY ano_mes, data, mes_parcial, natureza, pagador_tipo, recebedor_tipo,
           forma_iniciacao, forma_iniciacao_descricao
)
SELECT
  *,
  ROUND(valor / NULLIF(quantidade, 0), 2)                                                      AS ticket_medio,
  ROUND(valor / SUM(valor) OVER (PARTITION BY ano_mes, natureza), 6)                  AS participacao_valor_na_natureza
FROM agregado;
