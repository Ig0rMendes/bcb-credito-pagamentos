"""Testes das transformações, com dados de exemplo no mesmo formato que a API devolve (não precisam de internet)."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from coletar_dados import (  # noqa: E402
    buscar_json,
    diaria_para_mensal,
    meses_faltando,
    periodos_de_ate_10_anos,
    pix_para_dataframe,
    remover_mes_incompleto,
    resumir_pix,
    sgs_para_dataframe,
    validar_colunas,
)


def test_sgs_converte_data_e_valor_texto():
    registros = [{"data": "01/01/2024", "valor": "1.32"}, {"data": "01/02/2024", "valor": "1.41"}]
    df = sgs_para_dataframe(registros, 21083)
    assert df["data"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]
    assert df["valor"].tolist() == [1.32, 1.41]
    assert (df["serie"] == "inadimplencia_pj").all()


def test_sgs_descarta_valor_vazio():
    registros = [{"data": "01/01/2024", "valor": ""}, {"data": "01/02/2024", "valor": "2.5"}]
    assert len(sgs_para_dataframe(registros, 433)) == 1


def test_diaria_vira_mensal_com_ultimo_valor_do_mes():
    registros = [
        {"data": "02/01/2024", "valor": "11.75"},
        {"data": "31/01/2024", "valor": "11.25"},  # mudou no fim do mês: este é o que vale
        {"data": "01/02/2024", "valor": "11.25"},
    ]
    mensal = diaria_para_mensal(sgs_para_dataframe(registros, 432))
    assert mensal["data"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]
    assert mensal["valor"].tolist() == [11.25, 11.25]


def test_periodos_respeitam_limite_de_10_anos():
    blocos = periodos_de_ate_10_anos(date(2015, 1, 1), date(2026, 11, 8))
    assert blocos == [(date(2015, 1, 1), date(2024, 12, 31)), (date(2025, 1, 1), date(2026, 11, 8))]


def test_remove_mes_corrente_incompleto():
    df = pd.DataFrame({"data": pd.to_datetime(["2026-10-01", "2026-11-01"]), "valor": [13.75, 13.75]})
    assert remover_mes_incompleto(df, date(2026, 11, 8))["data"].tolist() == [pd.Timestamp("2026-10-01")]


def test_pix_usa_mes_da_coluna_anomes_e_tira_mes_corrente():
    # A API devolve vários meses numa resposta só: o mês de cada linha é o AnoMes, não o mês pedido.
    registros = [
        {"AnoMes": 202209, "NATUREZA": "B2B", "VALOR": 10.0, "QUANTIDADE": 1},
        {"AnoMes": 202610, "NATUREZA": "P2P", "VALOR": 20.0, "QUANTIDADE": 2},
        {"AnoMes": 202611, "NATUREZA": "P2P", "VALOR": 5.0, "QUANTIDADE": 1},  # mês corrente: sai
    ]
    df = pix_para_dataframe(registros, date(2026, 11, 8))
    assert df["ano_mes"].tolist() == ["202209", "202610"]
    assert df["data"].tolist() == [pd.Timestamp("2022-09-01"), pd.Timestamp("2026-10-01")]


def test_resumo_pix_soma_e_calcula_participacao():
    pix = pd.DataFrame([
        {"ano_mes": "202401", "NATUREZA": "B2B", "VALOR": 60.0, "QUANTIDADE": 2},
        {"ano_mes": "202401", "NATUREZA": "B2B", "VALOR": 15.0, "QUANTIDADE": 1},
        {"ano_mes": "202401", "NATUREZA": "P2P", "VALOR": 25.0, "QUANTIDADE": 5},
    ])
    r = resumir_pix(pix).set_index("natureza")
    assert r.loc["B2B", "valor_reais"] == 75.0
    assert r.loc["B2B", "quantidade"] == 3
    assert r.loc["B2B", "participacao_valor"] == 0.75
    assert r.loc["P2P", "participacao_valor"] == 0.25


def test_para_se_a_api_renomear_uma_coluna():
    # Sem a validação, isso viraria uma tabela vazia sem nenhum erro.
    with pytest.raises(ValueError, match="valor"):
        sgs_para_dataframe([{"data": "01/01/2024", "VLR": "1.32"}], 21083)


def test_para_se_a_api_nao_devolver_nada():
    with pytest.raises(ValueError, match="nenhum registro"):
        validar_colunas([], ["AnoMes"], "Pix")


def test_encontra_mes_faltando_no_meio_da_serie():
    datas = pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01", "2024-04-01"]))
    assert meses_faltando(datas) == ["2024-03"]
    completas = pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01", "2024-02-01"]))  # repetidas: Pix tem várias linhas por mês
    assert meses_faltando(completas) == []


class RespostaFalsa:
    """Imita uma resposta HTTP, sem acessar a internet."""

    def __init__(self, texto: str, status: int = 200, tipo: str = "text/html"):
        self.text, self.content, self.status_code = texto, texto.encode(), status
        self.headers = {"Content-Type": tipo}

    def raise_for_status(self):
        pass

    def json(self):
        import json
        return json.loads(self.text)


def test_erro_mostra_o_que_a_api_devolveu_quando_nao_e_json(monkeypatch):
    # Caso real da 1ª execução no GitHub Actions: HTTP 200, mas uma página HTML no lugar do JSON.
    monkeypatch.setattr("coletar_dados.requests.get", lambda *a, **k: RespostaFalsa("<html>Acesso negado</html>"))
    with pytest.raises(RuntimeError, match="não é JSON.*HTTP 200.*text/html.*Acesso negado"):
        buscar_json("https://exemplo", {}, tentativas=1)


def test_requisicao_se_identifica_com_user_agent_do_projeto(monkeypatch):
    enviados = {}

    def get_falso(url, params=None, timeout=None, headers=None):
        enviados.update(headers or {})
        return RespostaFalsa("[]", tipo="application/json")

    monkeypatch.setattr("coletar_dados.requests.get", get_falso)
    assert buscar_json("https://exemplo", {}) == []
    assert enviados["User-Agent"].startswith("bcb-credito-pagamentos/")
