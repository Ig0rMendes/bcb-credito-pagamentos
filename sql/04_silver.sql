-- =============================================================================
-- 04_silver.sql
-- Camada SILVER: dados limpos, com nomes claros e regras de negócio documentadas.
-- Lê da bronze e não altera a bronze (se algo der errado aqui, basta rodar de novo).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1) Indicadores mensais: uma linha por mês, uma coluna por série
-- -----------------------------------------------------------------------------
-- A bronze está no formato "longo" (uma linha por série e mês). Para analisar uma
-- série contra a outra no mesmo mês, giramos para o formato "largo" (pivot).
--
-- Também calculamos:
--   ipca_12m          inflação acumulada em 12 meses (juros compostos, não soma simples)
--   juro_real_ex_post Selic descontada da inflação dos últimos 12 meses (aproximação:
--                     compara a meta Selic do mês com a inflação já ocorrida)

CREATE OR REPLACE TABLE workspace.bcb.silver_indicadores_mensais
COMMENT 'Indicadores macro e de crédito mensais (SGS/BCB), um mês por linha'
AS
WITH largo AS (
  SELECT
    data,
    MAX(CASE WHEN serie = 'selic_meta'       THEN valor END) AS selic_meta,         -- % a.a.
    MAX(CASE WHEN serie = 'ipca_mensal'      THEN valor END) AS ipca_mensal,        -- % a.m.
    MAX(CASE WHEN serie = 'inadimplencia_pj' THEN valor END) AS inadimplencia_pj,   -- %
    MAX(CASE WHEN serie = 'inadimplencia_pf' THEN valor END) AS inadimplencia_pf,   -- %
    MAX(CASE WHEN serie = 'concessoes_pj'    THEN valor END) AS concessoes_pj       -- R$ milhões
  FROM workspace.bcb.bronze_sgs
  GROUP BY data
),
com_ipca_12m AS (
  SELECT
    *,
    -- Acumular inflação é multiplicar: (1 + 0,5%) x (1 + 0,4%) x ... - 1.
    -- SQL não tem "produto acumulado", então usamos: produto = exp(soma dos logaritmos).
    CASE
      WHEN COUNT(ipca_mensal) OVER w12 = 12
      THEN ROUND((EXP(SUM(LN(1 + ipca_mensal / 100)) OVER w12) - 1) * 100, 4)
    END AS ipca_12m
  FROM largo
  WINDOW w12 AS (ORDER BY data ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
)
SELECT
  data,
  YEAR(data) * 12 + MONTH(data)                          AS mes_seq,  -- número sequencial do mês, facilita "mês - k"
  selic_meta,
  ipca_mensal,
  ipca_12m,
  ROUND(((1 + selic_meta / 100) / (1 + ipca_12m / 100) - 1) * 100, 4) AS juro_real_ex_post,
  inadimplencia_pj,
  inadimplencia_pf,
  concessoes_pj
FROM com_ipca_12m;


-- -----------------------------------------------------------------------------
-- 2) Pix: nomes claros e quem paga / quem recebe
-- -----------------------------------------------------------------------------
-- Cuidado encontrado nos dados: a coluna PAG_PFPJ marca o GOVERNO como "PJ".
-- Então "PJ" não significa "empresa". O tipo correto vem da NATUREZA:
--   1ª letra = quem paga, última letra = quem recebe
--   P = pessoa, B = empresa (business), G = governo
--   Ex.: P2B = pessoa paga empresa; B2G = empresa paga governo.

CREATE OR REPLACE TABLE workspace.bcb.silver_pix
COMMENT 'Transações Pix mensais (BCB) com nomes padronizados e tipo de pagador/recebedor'
AS
SELECT
  ano_mes,
  data,
  data = DATE '2020-11-01'                                AS mes_parcial,      -- Pix começou no meio de nov/2020
  NATUREZA                                                AS natureza,
  CASE LEFT(NATUREZA, 1)  WHEN 'P' THEN 'Pessoa' WHEN 'B' THEN 'Empresa' WHEN 'G' THEN 'Governo'
                          ELSE 'Não identificado' END     AS pagador_tipo,
  CASE RIGHT(NATUREZA, 1) WHEN 'P' THEN 'Pessoa' WHEN 'B' THEN 'Empresa' WHEN 'G' THEN 'Governo'
                          ELSE 'Não identificado' END     AS recebedor_tipo,
  NATUREZA IN ('B2B', 'B2P', 'B2G', 'P2B', 'G2B')         AS envolve_empresa,
  COALESCE(PAG_REGIAO, 'Nao informado')                   AS pagador_regiao,
  COALESCE(REC_REGIAO, 'Nao informado')                   AS recebedor_regiao,
  COALESCE(PAG_IDADE, 'Nao informado')                    AS pagador_idade,
  COALESCE(REC_IDADE, 'Nao informado')                    AS recebedor_idade,
  COALESCE(FORMAINICIACAO, 'Nao informado')               AS forma_iniciacao,
  -- Descrições segundo os manuais do Pix (BCB). Códigos sem descrição confirmada ficam marcados.
  CASE COALESCE(FORMAINICIACAO, 'Nao informado')
    WHEN 'MANU' THEN 'Dados bancários digitados'
    WHEN 'DICT' THEN 'Chave Pix'
    WHEN 'QRES' THEN 'QR Code estático'
    WHEN 'QRDN' THEN 'QR Code dinâmico'
    WHEN 'INIC' THEN 'Iniciador de pagamento'
    WHEN 'AUTO' THEN 'Pix Automático'
    WHEN 'Nao disponivel' THEN 'Não disponível'
    WHEN 'Nao informado'  THEN 'Não informado'
    ELSE CONCAT('Código ', FORMAINICIACAO, ' (descrição a confirmar)')
  END                                                     AS forma_iniciacao_descricao,
  FINALIDADE                                              AS finalidade,
  VALOR                                                   AS valor,            -- R$
  QUANTIDADE                                              AS quantidade        -- nº de transações
FROM workspace.bcb.bronze_pix;
