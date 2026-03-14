from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_engine_and_session(database_url: str):
    engine = create_async_engine(database_url, echo=False, future=True)
    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_maker


async def init_db(engine):
    from app.models import User, Order  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)