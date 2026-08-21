"""Engine e sessao do banco.

Tres cuidados especificos de SQLite sob Streamlit (risco 5 do documento
de arquitetura):

- WAL ligado: leitura concorrente nao bloqueia durante escrita.
- `busy_timeout`: reexecucoes simultaneas do script esperam em vez de
  falhar imediatamente com "database is locked".
- Chaves estrangeiras: desligadas por padrao no SQLite, ligadas aqui.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from cashinho.adapters.persistence.models import Base
from cashinho.config.settings import PROJECT_ROOT, Settings, get_settings
from cashinho.observability.logging import get_logger

logger = get_logger(__name__)

_SQLITE_PREFIX = "sqlite:///"


def resolve_database_url(url: str, root: Path = PROJECT_ROOT) -> str:
    """Torna absoluto um caminho SQLite relativo e cria o diretorio.

    Sem isso, o banco mudaria de lugar conforme o diretorio de onde o
    Streamlit foi iniciado — e o diario ficaria espalhado em varios
    arquivos sem que ninguem percebesse.
    """
    if not url.startswith(_SQLITE_PREFIX):
        return url
    raw = url[len(_SQLITE_PREFIX) :]
    if raw in {"", ":memory:"}:
        return url
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{_SQLITE_PREFIX}{path}"


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Cria o engine configurado."""
    settings = settings or get_settings()
    url = resolve_database_url(settings.database_url)
    connect_args: dict[str, Any] = {}
    if url.startswith(_SQLITE_PREFIX):
        connect_args["check_same_thread"] = False

    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith(_SQLITE_PREFIX):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def init_db(engine: Engine) -> None:
    """Cria as tabelas ausentes.

    Provisorio: `create_all` nao versiona schema nem aplica alteracoes em
    tabelas existentes. O Alembic ja esta declarado nas dependencias e
    assume esta responsabilidade na Fase 6, antes de o diario acumular
    dados que nao possam ser perdidos.
    """
    Base.metadata.create_all(engine)
    logger.info("banco inicializado", extra={"tables": sorted(Base.metadata.tables)})


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Fabrica de sessoes vinculada ao engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transacao com commit ao final e rollback em caso de erro."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
