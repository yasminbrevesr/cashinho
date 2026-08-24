"""O log estruturado: grava, le, alimenta o painel - e nunca derruba quem chamou."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from cashinho.core.log import (
    EventoDeLog,
    Nivel,
    Registrador,
    RegistradorNulo,
    ler,
    nivel_de,
    pagina,
)
from cashinho.core.log.__main__ import main
from cashinho.core.saude import Telemetria
from cashinho.models import BRT

AGORA = datetime(2026, 8, 21, 14, 30, tzinfo=BRT)


def registrador(tmp_path, **campos):
    campos.setdefault("nivel_minimo", Nivel.DEBUG)
    return Registrador(pasta=tmp_path, relogio=lambda: AGORA, **campos)


# --- niveis ------------------------------------------------------------------


def test_os_quatro_niveis():
    assert [n.value for n in Nivel] == ["debug", "info", "aviso", "erro"]


def test_os_niveis_se_comparam():
    assert Nivel.ERRO > Nivel.AVISO > Nivel.INFO > Nivel.DEBUG


def test_nivel_de_aceita_texto_e_nivel():
    """Nivel herda de str: o argparse converte o proprio default de novo."""
    assert nivel_de("aviso") is Nivel.AVISO
    assert nivel_de(Nivel.AVISO) is Nivel.AVISO


def test_nivel_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="nivel desconhecido"):
        nivel_de("catastrofe")


# --- gravacao ------------------------------------------------------------------


def test_grava_uma_linha_por_evento(tmp_path):
    log = registrador(tmp_path)
    log.info("scanner", "varredura concluida", ativos=12)

    linhas = log.arquivo_do_dia().read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 1
    assert json.loads(linhas[0])["mensagem"] == "varredura concluida"


def test_o_arquivo_e_por_pregao(tmp_path):
    log = registrador(tmp_path)
    log.info("scanner", "x")

    assert log.arquivo_do_dia().name == "cashinho-2026-08-21.jsonl"


def test_os_dados_ficam_consultaveis(tmp_path):
    """Gravar so texto responde 'o que houve'; com dados responde 'quantas vezes'."""
    log = registrador(tmp_path)
    log.aviso("paper_broker", "ordem recusada", symbol="PETR4", necessario=3000.9)

    dados = json.loads(log.arquivo_do_dia().read_text(encoding="utf-8"))["dados"]
    assert dados == {"symbol": "PETR4", "necessario": 3000.9}


def test_append_only_nao_reescreve(tmp_path):
    log = registrador(tmp_path)
    log.info("a", "primeiro")
    log.info("a", "segundo")

    linhas = log.arquivo_do_dia().read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(l)["mensagem"] for l in linhas] == ["primeiro", "segundo"]


# --- limiar por componente ----------------------------------------------------------


def test_abaixo_do_limiar_nao_grava(tmp_path):
    log = registrador(tmp_path, nivel_minimo=Nivel.AVISO)

    assert log.info("scanner", "detalhe") is None
    assert log.aviso("scanner", "atencao") is not None


def test_o_limiar_pode_ser_por_componente(tmp_path):
    log = registrador(tmp_path, nivel_minimo=Nivel.ERRO,
                      niveis_por_componente={"market_data": Nivel.DEBUG})

    assert log.debug("market_data", "tick") is not None
    assert log.debug("scanner", "tick") is None


# --- nunca derruba quem chamou ------------------------------------------------------


def test_falha_de_escrita_nao_levanta(tmp_path):
    """Log que derruba o robo e' pior que log nenhum."""
    log = registrador(tmp_path)
    log.pasta = tmp_path / "arquivo-que-nao-e-pasta"
    log.pasta.write_text("sou um arquivo", encoding="utf-8")

    evento = log.erro("market_data", "feed caiu")  # nao levanta

    assert evento is not None
    assert log.falhas_de_escrita == 1
    assert log.gravando is False
    assert log.motivo_da_falha


def test_evento_continua_em_memoria_mesmo_sem_disco(tmp_path):
    log = Registrador(pasta=None, nivel_minimo=Nivel.DEBUG)
    log.info("scanner", "sem disco")

    assert len(log.recentes) == 1
    assert log.gravando is False


def test_a_memoria_nao_cresce_para_sempre(tmp_path):
    log = registrador(tmp_path, memoria=10)
    for i in range(50):
        log.info("scanner", f"evento {i}")

    assert len(log.recentes) == 10


def test_o_registrador_nulo_nao_grava_nada(tmp_path):
    log = RegistradorNulo()
    log.erro("market_data", "nada disso vai para disco")

    assert log.gravando is False
    assert log.arquivo_do_dia() is None


# --- ponte com o painel de saude -------------------------------------------------------


def test_erro_aparece_na_telemetria(tmp_path):
    """Antes disto, um erro so existia se alguem estivesse olhando na hora."""
    t = Telemetria()
    log = registrador(tmp_path, telemetria=t)

    log.erro("market_data", "feed nao respondeu")

    assert len(t.erros("market_data")) == 1


def test_aviso_nao_polui_a_telemetria(tmp_path):
    t = Telemetria()
    log = registrador(tmp_path, telemetria=t)

    log.aviso("market_data", "fonte lenta")

    assert t.erros("market_data") == []


def test_telemetria_quebrada_nao_quebra_o_log(tmp_path):
    class Ruim:
        def erro(self, *a, **k):
            raise RuntimeError("quebrei")

    log = registrador(tmp_path, telemetria=Ruim())

    assert log.erro("market_data", "feed caiu") is not None


# --- leitura -----------------------------------------------------------------------------


def test_le_de_volta_o_que_gravou(tmp_path):
    log = registrador(tmp_path)
    log.info("scanner", "primeiro", ativos=3)
    log.erro("market_data", "segundo")

    eventos, ruins = ler(log.arquivo_do_dia())

    assert [e.mensagem for e in eventos] == ["primeiro", "segundo"]
    assert eventos[0].dados == {"ativos": 3}
    assert ruins == ()


def test_linha_corrompida_e_reportada_e_nao_engolida(tmp_path):
    """O diario engole em silencio; aqui a linha ruim volta com o motivo."""
    log = registrador(tmp_path)
    log.info("scanner", "boa")
    with log.arquivo_do_dia().open("a", encoding="utf-8") as fh:
        fh.write("{isso nao e json\n")

    eventos, ruins = ler(log.arquivo_do_dia())

    assert len(eventos) == 1
    assert len(ruins) == 1
    assert "linha 2" in ruins[0]


def test_arquivo_inexistente_nao_e_linha_corrompida(tmp_path):
    eventos, ruins = ler(tmp_path / "nao-existe.jsonl")

    assert eventos == () and ruins == ()


def test_filtra_por_nivel_e_componente(tmp_path):
    log = registrador(tmp_path)
    log.info("scanner", "a")
    log.erro("market_data", "b")

    assert len(log.filtrar(nivel=Nivel.ERRO)) == 1
    assert len(log.filtrar(componente="scanner")) == 1


# --- tela e CLI ----------------------------------------------------------------------------


def test_a_tela_mostra_estado_e_eventos(tmp_path):
    log = registrador(tmp_path)
    log.erro("market_data", "feed caiu", tentativas=3)

    texto = pagina(log.recentes, log)

    assert "LOG" in texto and "gravando" in texto
    assert "feed caiu" in texto and "tentativas=3" in texto


def test_a_tela_denuncia_falha_de_escrita(tmp_path):
    log = registrador(tmp_path)
    log.pasta = tmp_path / "bloqueado"
    log.pasta.write_text("x", encoding="utf-8")
    log.erro("a", "b")

    assert "falha(s) de escrita" in pagina(log.recentes, log)


def test_cli_le_o_arquivo_do_dia(tmp_path, capsys):
    log = registrador(tmp_path)
    log.info("scanner", "varredura concluida")

    assert main(["--pasta", str(tmp_path), "--dia", "2026-08-21", "--sem-cor"]) == 0
    assert "varredura concluida" in capsys.readouterr().out


def test_cli_filtra_por_nivel(tmp_path, capsys):
    log = registrador(tmp_path)
    log.info("scanner", "rotina")
    log.erro("market_data", "falhou")

    main(["--pasta", str(tmp_path), "--dia", "2026-08-21", "--nivel", "erro", "--json"])
    dados = json.loads(capsys.readouterr().out)

    assert [e["mensagem"] for e in dados["eventos"]] == ["falhou"]


def test_cli_sem_arquivo_avisa_e_sai_com_codigo(tmp_path, capsys):
    codigo = main(["--pasta", str(tmp_path / "vazio"), "--sem-cor"])

    assert codigo == 1
    assert "sem log para" in capsys.readouterr().out


# --- integracao: o que a revisao apontou como cego ------------------------------------------


def test_divergencia_entre_risco_e_corretora_vai_para_o_log(tmp_path):
    """Era uma string numa lista em memoria que ninguem lia."""
    import inspect

    from cashinho.core.broker.risco import BrokerComRisco

    fonte = inspect.getsource(BrokerComRisco._sincronizar)
    assert "self.log.erro" in fonte


def test_kill_switch_do_paper_broker_e_registrado(tmp_path):
    from cashinho.core.broker import PaperBroker
    from cashinho.core.broker.paper import ConfigPaper

    log = registrador(tmp_path)
    PaperBroker(ConfigPaper(), log=log).acionar_kill_switch("teste")

    assert any("KILL SWITCH" in e.mensagem for e in log.recentes)


def test_kill_switch_do_risco_e_registrado(tmp_path):
    from cashinho.core.risk import RiskConfig, RiskManager

    log = registrador(tmp_path)
    RiskManager(RiskConfig(capital=10_000.0), log=log).acionar_kill_switch("teste")

    assert any("KILL SWITCH" in e.mensagem for e in log.recentes)


def test_sem_log_configurado_nada_muda(tmp_path):
    """A instrumentacao nao pode alterar comportamento de quem nao pediu log."""
    from cashinho.core.broker import PaperBroker
    from cashinho.core.broker.paper import ConfigPaper

    broker = PaperBroker(ConfigPaper())
    broker.acionar_kill_switch("sem log")

    assert broker.kill_switch_ativo is True
