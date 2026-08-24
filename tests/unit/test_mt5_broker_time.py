"""Fuso do servidor da corretora: MT5 -> Sao Paulo -> UTC."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from cashinho.adapters.providers.metatrader import BrokerTimeNormalizer, resolve_timezone

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def raw_for(wall_clock: datetime) -> float:
    """O inteiro que o MT5 devolveria para esse relogio de parede."""
    return wall_clock.replace(tzinfo=UTC).timestamp()


def test_o_relogio_do_servidor_vira_utc_sem_deslocamento() -> None:
    """A cadeia do enunciado: 17:05 MT5 -> 17:05 Sao Paulo -> 20:05 UTC."""
    normalizer = BrokerTimeNormalizer()

    moment = normalizer.to_utc(raw_for(datetime(2026, 8, 21, 17, 5)))

    assert (moment.hour, moment.minute) == (20, 5)
    assert moment.tzinfo is UTC
    assert moment.astimezone(SAO_PAULO).hour == 17


def test_a_conversao_ingenua_erraria_em_tres_horas() -> None:
    """O erro que este normalizador existe para impedir, escrito como teste."""
    normalizer = BrokerTimeNormalizer()
    raw = raw_for(datetime(2026, 8, 21, 17, 5))

    correto = normalizer.to_utc(raw).astimezone(SAO_PAULO)
    ingenuo = datetime.fromtimestamp(raw, tz=UTC).astimezone(SAO_PAULO)

    assert correto.hour == 17
    assert ingenuo.hour == 14
    assert correto.hour - ingenuo.hour == 3


def test_milissegundos_sao_normalizados_igual() -> None:
    """O tick real veio com 17:32:41.596."""
    normalizer = BrokerTimeNormalizer()
    raw_msc = raw_for(datetime(2026, 8, 20, 17, 32, 41)) * 1000 + 596

    moment = normalizer.to_utc_msc(raw_msc).astimezone(SAO_PAULO)

    assert (moment.hour, moment.minute, moment.second) == (17, 32, 41)
    assert 590 <= moment.microsecond / 1000 <= 600


def test_todo_resultado_e_aware_em_utc() -> None:
    """Regra 2 do projeto: nada de datetime naive circulando."""
    normalizer = BrokerTimeNormalizer()

    for hour in (10, 13, 17, 23):
        moment = normalizer.to_utc(raw_for(datetime(2026, 8, 21, hour, 0)))
        assert moment.tzinfo is not None
        assert moment.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_a_ida_e_a_volta_batem() -> None:
    normalizer = BrokerTimeNormalizer()
    raw = raw_for(datetime(2026, 8, 21, 14, 30))

    moment = normalizer.to_utc(raw)

    assert normalizer.from_utc(moment) == datetime(2026, 8, 21, 14, 30)


def test_horario_naive_e_recusado_na_volta() -> None:
    with pytest.raises(ValueError, match="sem fuso"):
        BrokerTimeNormalizer().from_utc(datetime(2026, 8, 21, 14, 30))


def test_o_fuso_do_servidor_e_configuravel() -> None:
    lisboa = BrokerTimeNormalizer("Europe/Lisbon")

    moment = lisboa.to_utc(raw_for(datetime(2026, 8, 21, 17, 5)))

    assert moment.astimezone(ZoneInfo("Europe/Lisbon")).hour == 17


def test_fuso_desconhecido_falha_com_instrucao() -> None:
    with pytest.raises(ValueError, match="tzdata"):
        resolve_timezone("Marte/Olympus")
