-- =============================================================================
-- 01_estrutura.sql
-- Cria o "endereço" onde o projeto vai morar no Databricks.
--
-- Hierarquia do Unity Catalog:  catálogo  >  schema  >  tabelas / volumes
--   workspace          catálogo padrão do Databricks Free Edition
--   workspace.bcb      schema deste projeto (agrupa tudo dele)
--   workspace.bcb.landing   volume: "pasta" onde os CSVs chegam, antes de virarem tabela
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS workspace.bcb
COMMENT 'Projeto: crédito e pagamentos das empresas no Brasil (dados públicos do Banco Central)';

CREATE VOLUME IF NOT EXISTS workspace.bcb.landing
COMMENT 'Área de chegada: CSVs gerados por src/coletar_dados.py, enviados sem alteração';
