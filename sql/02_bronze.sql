-- =============================================================================
-- 02_bronze.sql
-- Camada BRONZE: os CSVs viram tabelas, sem nenhuma regra de negócio.
-- Só fixamos os tipos das colunas e registramos de onde e quando cada linha veio.
--
-- Pré-requisito: os arquivos abaixo enviados para /Volumes/workspace/bcb/landing/
--   series_sgs_longo.csv   (SGS: Selic, IPCA, inadimplência PJ e PF, concessões PJ)
--   pix_detalhado.parquet  (Pix: uma linha por combinação de mês e categorias)
--   gabarito.csv           (valores esperados das checagens, gerados pelo Python)
--
-- Por que o Pix vai em Parquet e o SGS em CSV?
--   O CSV do Pix tem ~80 MB e o upload pelo navegador falhava. Em Parquet ele tem ~12 MB:
--   o formato é colunar e comprimido, e já guarda o tipo de cada coluna (texto, número, data).
--   O SGS tem só 30 KB, então o CSV não atrapalha.
-- =============================================================================

-- Séries do SGS (formato longo: uma linha por série e mês)
CREATE OR REPLACE TABLE workspace.bcb.bronze_sgs
COMMENT 'Séries mensais do SGS/BCB, como saíram do script de coleta'
AS
SELECT
  *,
  _metadata.file_name          AS arquivo_origem,   -- auditoria: de qual arquivo veio
  _metadata.file_modification_time AS arquivo_modificado_em,
  current_timestamp()          AS carregado_em      -- auditoria: quando entrou na tabela
FROM read_files(
  '/Volumes/workspace/bcb/landing/series_sgs_longo.csv',
  format      => 'csv',
  header      => true,
  schemaHints => 'data DATE, valor DOUBLE, codigo_sgs INT, serie STRING, unidade STRING'
);

-- Estatísticas do Pix (granular)
CREATE OR REPLACE TABLE workspace.bcb.bronze_pix
COMMENT 'Estatísticas de transações Pix (API Pix Dados Abertos/BCB), como saíram do script de coleta'
AS
SELECT
  *,
  _metadata.file_name          AS arquivo_origem,
  _metadata.file_modification_time AS arquivo_modificado_em,
  current_timestamp()          AS carregado_em
FROM read_files(
  '/Volumes/workspace/bcb/landing/pix_detalhado.parquet',
  format => 'parquet'   -- os tipos já vêm dentro do arquivo: não precisa de schemaHints
);

-- Gabarito: valores esperados, calculados com pandas a cada coleta (src/gabarito.py).
-- As checagens 03 e 06 comparam as tabelas com ele, sem nenhum número escrito à mão.
CREATE OR REPLACE TABLE workspace.bcb.bronze_gabarito
COMMENT 'Valores esperados das checagens, gerados pelo Python na mesma coleta dos dados'
AS
SELECT
  *,
  _metadata.file_name          AS arquivo_origem,
  _metadata.file_modification_time AS arquivo_modificado_em,
  current_timestamp()          AS carregado_em
FROM read_files(
  '/Volumes/workspace/bcb/landing/gabarito.csv',
  format      => 'csv',
  header      => true,
  schemaHints => 'checagem STRING, esperado DOUBLE, tolerancia DOUBLE'
);
