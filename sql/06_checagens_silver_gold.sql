-- =============================================================================
-- 06_checagens_silver_gold.sql
-- Confere silver e gold contra o gabarito (bronze_gabarito), que o Python calcula com pandas,
-- por outro caminho, a cada coleta. Mesmo esquema do 03:
--   encontrado (medido aqui no SQL) x esperado (gabarito) -> ok dentro da tolerância.
--
-- "Mês de referência" = último mês com inadimplência PJ publicada. Nada de datas fixas:
-- quando um mês novo entra, as checagens acompanham sozinhas.
-- =============================================================================

WITH
ind  AS (SELECT * FROM workspace.bcb.silver_indicadores_mensais),
defa AS (SELECT * FROM workspace.bcb.gold_defasagem_juros_inadimplencia),
ref  AS (SELECT MAX(data) AS mes_ref FROM ind WHERE inadimplencia_pj IS NOT NULL),
ultimo_pix AS (SELECT MAX(ano_mes) AS ano_mes FROM workspace.bcb.gold_pix_natureza_mensal),
corr_pico AS (   -- defasagem com a maior correlação, para cada indicador e base
  SELECT indicador_juros, base, defasagem_meses, correlacao
  FROM workspace.bcb.gold_correlacao_defasagem
  QUALIFY ROW_NUMBER() OVER (PARTITION BY indicador_juros, base ORDER BY correlacao DESC) = 1
),
encontrado AS (
  -- Silver: indicadores
  SELECT 'silver_indicadores: meses' AS checagem, CAST(COUNT(*) AS DOUBLE) AS encontrado FROM ind
  UNION ALL SELECT 'silver_indicadores: meses sem buraco (último - primeiro + 1)', MAX(mes_seq) - MIN(mes_seq) + 1 FROM ind
  UNION ALL SELECT 'silver_indicadores: IPCA 12m no mês de referência (%)', i.ipca_12m
            FROM ind i JOIN ref ON i.data = ref.mes_ref
  UNION ALL SELECT 'silver_indicadores: juro real no mês de referência (%)', i.juro_real_ex_post
            FROM ind i JOIN ref ON i.data = ref.mes_ref

  -- Silver: Pix (nada pode se perder entre bronze e silver)
  UNION ALL SELECT 'silver_pix: linhas', COUNT(*) FROM workspace.bcb.silver_pix
  UNION ALL SELECT 'silver_pix: diferença de valor para a bronze (R$)',
            (SELECT SUM(VALOR) FROM workspace.bcb.bronze_pix) - (SELECT SUM(valor) FROM workspace.bcb.silver_pix)
  UNION ALL SELECT 'silver_pix: linhas com empresa pagando ou recebendo', COUNT_IF(envolve_empresa)
            FROM workspace.bcb.silver_pix

  -- Gold: defasagem
  UNION ALL SELECT 'gold_defasagem: meses', COUNT(*) FROM defa
  UNION ALL SELECT 'gold_defasagem: Selic 6 meses antes do mês de referência', d.selic_6m_antes
            FROM defa d JOIN ref ON d.data = ref.mes_ref

  -- Gold: correlação
  UNION ALL SELECT 'gold_correlacao: linhas (25 defasagens x 2 indicadores x 2 bases)', COUNT(*)
            FROM workspace.bcb.gold_correlacao_defasagem
  UNION ALL SELECT 'gold_correlacao: mesma amostra em todas (meses distintos usados)', COUNT(DISTINCT meses_usados)
            FROM workspace.bcb.gold_correlacao_defasagem
  UNION ALL SELECT 'gold_correlacao: meses usados', MAX(meses_usados) FROM workspace.bcb.gold_correlacao_defasagem
  UNION ALL SELECT CONCAT('gold_correlacao: pico ', indicador_juros, ', ', base, ' (meses)'), defasagem_meses FROM corr_pico
  UNION ALL SELECT CONCAT('gold_correlacao: valor do pico ', indicador_juros, ', ', base), correlacao FROM corr_pico

  -- Gold: Pix
  UNION ALL SELECT 'gold_pix_natureza: linhas', COUNT(*) FROM workspace.bcb.gold_pix_natureza_mensal
  UNION ALL SELECT 'gold_pix_natureza: participação B2B no último mês', g.participacao_valor
            FROM workspace.bcb.gold_pix_natureza_mensal g JOIN ultimo_pix u ON g.ano_mes = u.ano_mes
            WHERE g.natureza = 'B2B'
  UNION ALL SELECT 'gold_pix_empresas: linhas', COUNT(*) FROM workspace.bcb.gold_pix_empresas_forma_iniciacao
  UNION ALL SELECT 'gold_pix_empresas: valor do último mês igual ao da natureza (R$ bi, diferença)',
            (SELECT SUM(g.valor) FROM workspace.bcb.gold_pix_empresas_forma_iniciacao g
               JOIN ultimo_pix u ON g.ano_mes = u.ano_mes) / 1e9
          - (SELECT SUM(g.valor) FROM workspace.bcb.gold_pix_natureza_mensal g
               JOIN ultimo_pix u ON g.ano_mes = u.ano_mes WHERE g.envolve_empresa) / 1e9
),
gabarito AS (
  SELECT checagem, esperado, tolerancia
  FROM workspace.bcb.bronze_gabarito
  WHERE checagem LIKE 'silver_%' OR checagem LIKE 'gold_%'
)
SELECT
  COALESCE(e.checagem, g.checagem)                              AS checagem,
  g.esperado,
  e.encontrado,
  COALESCE(ABS(e.encontrado - g.esperado) <= g.tolerancia, false) AS ok
FROM encontrado e
FULL OUTER JOIN gabarito g ON e.checagem = g.checagem
ORDER BY ok, checagem;   -- problemas aparecem primeiro
