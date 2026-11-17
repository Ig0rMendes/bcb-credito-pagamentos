"""Testa os SQLs do Databricks localmente, com DuckDB, antes de rodá-los na nuvem.

O DuckDB é um banco de dados que roda dentro do Python, sem servidor. A sintaxe é quase igual
à do Databricks; o pouco que muda é trocado em `traduzir`. Assim um erro de lógica no SQL
aparece no `pytest`, e não só depois de subir para o Databricks.

O que é testado:
  - as checagens 03 e 06 passam contra o gabarito que o Python calcula (src/gabarito.py);
  - todo nome de checagem existe dos dois lados (SQL e gabarito);
  - quando os dados estão errados, as checagens PARAM com erro (a trava do Job automático).

Precisa dos dados gerados por `python src/coletar_dados.py`. Sem eles, os testes são pulados.
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

duckdb = pytest.importorskip("duckdb")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from gabarito import gerar_gabarito  # noqa: E402

SQL = RAIZ / "sql"
DADOS = RAIZ / "data" / "processed"
ARQ_SGS = DADOS / "series_sgs_longo.csv"
ARQ_PIX = DADOS / "pix_detalhado.parquet"

pytestmark = pytest.mark.skipif(
    not (ARQ_SGS.exists() and ARQ_PIX.exists()),
    reason="dados não encontrados: rode python src/coletar_dados.py",
)


def traduzir(sql: str) -> str:
    """Troca o que é exclusivo do Databricks pelo equivalente no DuckDB."""
    sql = sql.replace("workspace.bcb.", "")
    sql = sql.replace("explode(sequence(0, 24))", "unnest(generate_series(0, 24))")
    sql = re.sub(r"\nCOMMENT '[^']*'\n", "\n", sql)  # DuckDB não aceita COMMENT no CREATE TABLE
    sql = sql.replace("raise_error(", "error(")  # nome da função que interrompe a consulta com erro
    return sql


def rodar(con, arquivo: str):
    return con.execute(traduzir((SQL / arquivo).read_text(encoding="utf-8"))).fetchall()


def montar_banco(remover_linhas_pix: int = 0):
    """Cria a bronze (dados + gabarito) e roda silver e gold.

    `remover_linhas_pix` > 0 estraga a bronze de propósito, DEPOIS de calcular o gabarito,
    simulando um upload incompleto para o Databricks.
    """
    con = duckdb.connect()
    con.execute(
        f"CREATE TABLE bronze_sgs AS SELECT * FROM read_csv('{ARQ_SGS.as_posix()}', header = true, "
        "types = {'data': 'DATE', 'valor': 'DOUBLE'})"
    )
    # O Parquet é lido pelo leitor do próprio DuckDB, e não pelo pd.read_parquet (pyarrow):
    # em alguns Windows o pyarrow do Anaconda trava ao LER Parquet ("instrução ilegal", 0xc000001d).
    con.execute(f"CREATE TABLE bronze_pix AS SELECT * FROM read_parquet('{ARQ_PIX.as_posix()}')")

    sgs = pd.read_csv(ARQ_SGS)
    pix = con.execute("SELECT * FROM bronze_pix").df()
    gabarito = gerar_gabarito(sgs, pix)  # noqa: F841 (usado pelo DuckDB pelo nome da variável)
    con.execute("CREATE TABLE bronze_gabarito AS SELECT * FROM gabarito")

    if remover_linhas_pix:  # estraga a bronze depois do gabarito pronto
        con.execute(f"DELETE FROM bronze_pix WHERE rowid < {remover_linhas_pix}")
    for arquivo in ["04_silver.sql", "05_gold.sql"]:
        rodar(con, arquivo)
    return con


@pytest.fixture(scope="module")
def banco():
    con = montar_banco()
    yield con
    con.close()


@pytest.mark.parametrize("arquivo", ["03_checagens_bronze.sql", "06_checagens_silver_gold.sql"])
def test_checagens_passam_contra_o_gabarito(banco, arquivo):
    resultado = rodar(banco, arquivo)
    falhas = [linha for linha in resultado if not linha[-1]]
    assert resultado, "a checagem não devolveu nenhuma linha"
    assert not falhas, f"Checagens com problema (checagem, esperado, encontrado, ok): {falhas}"


def test_todo_item_do_gabarito_e_conferido_pelo_sql(banco):
    nomes_sql = {linha[0] for arq in ["03_checagens_bronze.sql", "06_checagens_silver_gold.sql"]
                 for linha in rodar(banco, arq) if linha[2] is not None}
    nomes_gabarito = {linha[0] for linha in banco.execute("SELECT checagem FROM bronze_gabarito").fetchall()}
    assert nomes_gabarito == nomes_sql


def test_checagens_param_com_erro_quando_os_dados_estao_incompletos():
    # Simula um upload que perdeu 10 linhas do Pix: o gabarito (feito antes) não bate mais.
    # No Job automático, o erro impede que as etapas seguintes rodem com dados ruins.
    con = montar_banco(remover_linhas_pix=10)
    with pytest.raises(duckdb.Error, match="Checagem falhou"):
        rodar(con, "03_checagens_bronze.sql")
    with pytest.raises(duckdb.Error, match="Checagem falhou"):
        rodar(con, "06_checagens_silver_gold.sql")
    # A view continua disponível para investigar o que falhou
    falhas = {linha[0] for linha in con.execute(
        "SELECT checagem FROM vw_checagens_bronze WHERE NOT ok UNION ALL "
        "SELECT checagem FROM vw_checagens_silver_gold WHERE NOT ok").fetchall()}
    con.close()
    assert "bronze_pix: linhas" in falhas
    assert "silver_pix: linhas" in falhas


def test_silver_pix_nao_confunde_governo_com_empresa(banco):
    # PAG_PFPJ marca governo como "PJ"; o tipo correto vem da natureza.
    tipos = dict(banco.execute("SELECT natureza, pagador_tipo FROM silver_pix GROUP BY 1, 2").fetchall())
    assert tipos["G2P"] == "Governo"
    assert tipos["B2P"] == "Empresa"
