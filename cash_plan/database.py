"""数据库连接与会话管理 (SQLAlchemy, 默认SQLite, 可切换PostgreSQL/MySQL)"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db():
    from . import models  # noqa: F401

    models.Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    """事务性会话上下文: 正常提交, 异常回滚"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
