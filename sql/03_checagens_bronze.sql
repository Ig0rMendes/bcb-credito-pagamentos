-- =============================================================================
-- 03_checagens_bronze.sql
-- Confere se as tabelas bronze têm exatamente o que o Python gerou.
--
-- Como funciona:
--   1) "encontrado": este SQL mede as tabelas (conta linhas, meses, nulos...).
--   2) "esperado": vem da tabela bronze_gabarito, que o Python calculou com pandas na mesma coleta.
--   3) ok = true quando a diferença está dentro da tolerância.
-- Nenhum número está escrito à mão: numa coleta nova, o gabarito se atualiza sozinho.
-- Uma checagem que existe só de um lado (no SQL ou no gabarito) aparece com ok = false.
-- =============================================================================

WITH encontrado AS (
  SELECT 'bronze_sgs: linhas' AS checagem, COUNT(*) AS encontrado FROM workspace.bcb.bronze_sgs
  UNION ALL SELECT 'bronze_sgs: séries', COUNT(DISTINCT serie) FROM workspace.bcb.bronze_sgs
  UNION ALL SELECT 'bronze_sgs: duplicadas',          -- linhas totais - combinações (série, data) distintas
            (SELECT COUNT(*) FROM workspace.bcb.bronze_sgs)
          - (SELECT COUNT(*) FROM (SELECT DISTINCT serie, data FROM workspace.bcb.bronze_sgs))
  UNION ALL SELECT 'bronze_sgs: nulos', COUNT_IF(valor IS NULL OR data IS NULL) FROM workspace.bcb.bronze_sgs
  UNION ALL SELECT 'bronze_pix: linhas', COUNT(*) FROM workspace.bcb.bronze_pix
  UNION ALL SELECT 'bronze_pix: meses', COUNT(DISTINCT ano_mes) FROM workspace.bcb.bronze_pix
  UNION ALL SELECT 'bronze_pix: primeiro mês (AAAAMM)', CAST(MIN(ano_mes) AS INT) FROM workspace.bcb.bronze_pix
  UNION ALL SELECT 'bronze_pix: último mês (AAAAMM)', CAST(MAX(ano_mes) AS INT) FROM workspace.bcb.bronze_pix
  UNION ALL SELECT 'bronze_pix: nulos em VALOR/QUANTIDADE', COUNT_IF(VALOR IS NULL OR QUANTIDADE IS NULL)
            FROM workspace.bcb.bronze_pix
),
gabarito AS (
  SELECT checagem, esperado, tolerancia
  FROM workspace.bcb.bronze_gabarito
  WHERE checagem LIKE 'bronze_%'
)
SELECT
  COALESCE(e.checagem, g.checagem)                              AS checagem,
  g.esperado,
  e.encontrado,
  COALESCE(ABS(e.encontrado - g.esperado) <= g.tolerancia, false) AS ok
FROM encontrado e
FULL OUTER JOIN gabarito g ON e.checagem = g.checagem
ORDER BY ok, checagem;   -- problemas aparecem primeiro
