"""Escrita atomica e cache com teto."""

from __future__ import annotations

import json
import os

import pytest

from cashinho.core.arquivos import escrever_json, escrever_texto
from cashinho.core.cache import TETO_PADRAO, CacheLimitado


# --- escrita atomica ---------------------------------------------------------


def test_grava_o_conteudo(tmp_path):
    destino = escrever_texto(tmp_path / "a.txt", "conteudo")

    assert destino.read_text(encoding="utf-8") == "conteudo"


def test_cria_a_pasta_se_faltar(tmp_path):
    destino = escrever_json(tmp_path / "nova" / "b.json", {"x": 1})

    assert json.loads(destino.read_text(encoding="utf-8")) == {"x": 1}


def test_nao_deixa_temporario_para_tras(tmp_path):
    escrever_json(tmp_path / "c.json", {"x": 1})

    assert [p.name for p in tmp_path.iterdir()] == ["c.json"]


def test_o_temporario_fica_na_mesma_pasta(tmp_path, monkeypatch):
    """os.replace so e' atomico dentro do mesmo sistema de arquivos."""
    vistos = []
    import tempfile as t

    original = t.mkstemp

    def espiao(*args, **kwargs):
        vistos.append(kwargs.get("dir"))
        return original(*args, **kwargs)

    monkeypatch.setattr(t, "mkstemp", espiao)
    escrever_texto(tmp_path / "d.txt", "x")

    assert vistos == [tmp_path]


def test_falha_no_meio_preserva_o_arquivo_antigo(tmp_path, monkeypatch):
    destino = tmp_path / "estado.json"
    escrever_json(destino, {"versao": 1})

    def explode(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(OSError):
        escrever_json(destino, {"versao": 2})

    # o antigo continua inteiro, e nao sobrou lixo
    assert json.loads(destino.read_text(encoding="utf-8")) == {"versao": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["estado.json"]


def test_sobrescreve_arquivo_existente(tmp_path):
    escrever_json(tmp_path / "e.json", {"v": 1})
    escrever_json(tmp_path / "e.json", {"v": 2})

    assert json.loads((tmp_path / "e.json").read_text(encoding="utf-8")) == {"v": 2}


def test_o_diario_salva_de_forma_atomica():
    import inspect

    from cashinho.core.diario.diario import DiarioDeTrades

    assert "escrever_texto" in inspect.getsource(DiarioDeTrades.salvar)


def test_nenhum_estado_e_gravado_com_write_text_cru():
    import pathlib
    import re

    cruas = [str(p) for p in pathlib.Path("src/cashinho").rglob("*.py")
             if re.search(r"\.write_text\(json\.dumps\(", p.read_text())]

    assert cruas == []


# --- cache com teto -------------------------------------------------------------


def test_guarda_e_reaproveita():
    cache = CacheLimitado(teto=4)
    chamadas = []

    def calcular():
        chamadas.append(1)
        return "valor"

    assert cache.obter("a", calcular) == "valor"
    assert cache.obter("a", calcular) == "valor"
    assert len(chamadas) == 1
    assert cache.acertos == 1 and cache.faltas == 1


def test_o_teto_e_respeitado():
    cache = CacheLimitado(teto=3)
    for i in range(10):
        cache.obter(i, lambda: i)

    assert len(cache) == 3
    assert cache.despejos == 7


def test_despeja_o_menos_usado_recentemente():
    cache = CacheLimitado(teto=2)
    cache.obter("a", lambda: 1)
    cache.obter("b", lambda: 2)
    cache.obter("a", lambda: 1)   # 'a' volta a ser o mais recente
    cache.obter("c", lambda: 3)   # despeja 'b'

    assert "a" in cache and "c" in cache
    assert "b" not in cache


def test_despejar_nunca_muda_resultado():
    """O que esta guardado e' funcao deterministica da chave."""
    cache = CacheLimitado(teto=1)

    primeiro = cache.obter("k", lambda: 42)
    cache.obter("outra", lambda: 0)      # despeja 'k'
    segundo = cache.obter("k", lambda: 42)

    assert primeiro == segundo == 42


def test_aproveitamento_e_medivel():
    cache = CacheLimitado(teto=4)
    cache.obter("a", lambda: 1)
    cache.obter("a", lambda: 1)

    assert cache.aproveitamento == 0.5
    assert cache.para_dict()["entradas"] == 1


def test_teto_invalido_e_recusado():
    with pytest.raises(ValueError):
        CacheLimitado(teto=0)


def test_limpar_esvazia():
    cache = CacheLimitado(teto=4)
    cache.obter("a", lambda: 1)
    cache.limpar()

    assert len(cache) == 0


def test_os_motores_usam_cache_com_teto():
    from cashinho.core.auditor import ContrarianAuditor
    from cashinho.core.confluencia import MultiTimeframeEngine
    from cashinho.core.oportunidade import OpportunityEngine

    assert isinstance(OpportunityEngine()._cache_estrutura, CacheLimitado)
    assert isinstance(ContrarianAuditor()._cache_estrutura, CacheLimitado)
    assert isinstance(MultiTimeframeEngine()._cache, CacheLimitado)


def test_o_teto_padrao_nao_e_ilimitado():
    assert 1 <= TETO_PADRAO <= 4096
