from sqlalchemy import text
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


async def migrate_orders_table(engine) -> None:
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(orders)"))
        existing_columns = {row[1] for row in result.fetchall()}

        wanted_columns: dict[str, str] = {
            "payment_confirmed_at": "DATETIME",
            "provisioning_started_at": "DATETIME",
            "last_error": "TEXT",
            "last_warning_sent_at": "DATETIME",
        }

        for column_name, column_sql_type in wanted_columns.items():
            if column_name not in existing_columns:
                await conn.execute(
                    text(f"ALTER TABLE orders ADD COLUMN {column_name} {column_sql_type}")
                )


async def init_db(engine):
    from app.models import Order, User  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await migrate_orders_table(engine)