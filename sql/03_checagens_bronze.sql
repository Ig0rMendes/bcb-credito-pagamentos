-- =============================================================================
-- 03_checagens_bronze.sql
-- Confere se as tabelas bronze têm exatamente o que o Python gerou.
-- Cada linha mostra o valor ESPERADO (conferido no CSV com pandas) e o ENCONTRADO.
-- Tudo certo = coluna "ok" com true em todas as linhas.
-- Valores esperados da coleta de 16/11/2026; se você coletar de novo, eles mudam.
-- =============================================================================

WITH sgs AS (
  SELECT
    COUNT(*)                                        AS linhas,
    COUNT(DISTINCT serie)                           AS series,
    COUNT(*) - COUNT(DISTINCT serie, data)          AS duplicadas,
    COUNT_IF(valor IS NULL OR data IS NULL)         AS nulos
  FROM workspace.bcb.bronze_sgs
),
pix AS (
  SELECT
    COUNT(*)                                        AS linhas,
    COUNT(DISTINCT ano_mes)                         AS meses,
    MIN(ano_mes)                                    AS primeiro_mes,
    MAX(ano_mes)                                    AS ultimo_mes,
    COUNT_IF(VALOR IS NULL OR QUANTIDADE IS NULL)   AS nulos
  FROM workspace.bcb.bronze_pix
)
SELECT 'SGS: linhas'           AS checagem, '707'    AS esperado, CAST(linhas AS STRING)     AS encontrado, linhas = 707        AS ok FROM sgs
UNION ALL SELECT 'SGS: séries',            '5',      CAST(series AS STRING),     series = 5          FROM sgs
UNION ALL SELECT 'SGS: duplicadas',        '0',      CAST(duplicadas AS STRING), duplicadas = 0      FROM sgs
UNION ALL SELECT 'SGS: nulos',             '0',      CAST(nulos AS STRING),      nulos = 0           FROM sgs
UNION ALL SELECT 'Pix: linhas',            '768106', CAST(linhas AS STRING),     linhas = 768106     FROM pix
UNION ALL SELECT 'Pix: meses',             '72',     CAST(meses AS STRING),      meses = 72          FROM pix
UNION ALL SELECT 'Pix: primeiro mês',      '202011', primeiro_mes,               primeiro_mes = '202011' FROM pix
UNION ALL SELECT 'Pix: último mês',        '202610', ultimo_mes,                 ultimo_mes = '202610'   FROM pix
UNION ALL SELECT 'Pix: nulos em VALOR/QUANTIDADE', '0', CAST(nulos AS STRING),   nulos = 0           FROM pix;

-- Conferência cruzada com o resumo que o Python calculou (pix_por_natureza.csv):
-- em out/2026, B2B deve ter 51,82% do valor; P2P 24,35%; P2B 11,30%; B2P 10,95%.
SELECT
  NATUREZA,
  ROUND(SUM(VALOR) / 1e9, 1)                                   AS valor_bilhoes,
  ROUND(100 * SUM(VALOR) / SUM(SUM(VALOR)) OVER (), 2)          AS participacao_pct
FROM workspace.bcb.bronze_pix
WHERE ano_mes = '202610'
GROUP BY NATUREZA
ORDER BY valor_bilhoes DESC;
