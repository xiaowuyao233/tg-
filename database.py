import os
import datetime
import logging
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Text, Boolean, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.future import select

logger = logging.getLogger("yy_bot")

Base = declarative_base()

DB_PATH = "./data/bot.db"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class SystemConfig(Base):
    """系统配置表"""
    __tablename__ = 'system_config'
    key = Column(String(191), primary_key=True)
    value = Column(String(500))


class User(Base):
    """用户表"""
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    last_active_at = Column(DateTime, default=datetime.datetime.now)


class FileRecord(Base):
    """文件记录表"""
    __tablename__ = 'files'
    id = Column(Integer, primary_key=True)
    file_unique_id = Column(String(191), unique=True, index=True)
    file_id = Column(String(500))
    file_type = Column(String(50))
    file_name = Column(String(500), nullable=True)
    caption = Column(Text, nullable=True)
    media_group_id = Column(String(255), nullable=True)


class FileCode(Base):
    """文件码表"""
    __tablename__ = 'file_codes'
    code = Column(String(100), primary_key=True)
    creator_id = Column(BigInteger, index=True)
    file_ids = Column(Text)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    hits = Column(Integer, default=0)


def _create_engine():
    """创建 SQLite 异步引擎"""
    return create_async_engine(
        f"sqlite+aiosqlite:///{DB_PATH}",
        connect_args={"timeout": 30},
        echo=False
    )


engine = _create_engine()
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_local_session():
    """创建本地数据库会话，避免 event loop 不匹配问题"""
    local_engine = create_async_engine(
        f"sqlite+aiosqlite:///{DB_PATH}",
        connect_args={"timeout": 30},
        echo=False
    )
    LocalSession = sessionmaker(local_engine, class_=AsyncSession, expire_on_commit=False)
    session = LocalSession()
    return session, local_engine


async def init_db():
    """初始化数据库"""
    global engine, async_session

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=30000"))
        await conn.run_sync(Base.metadata.create_all)

        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS ix_file_codes_creator_id ON file_codes(creator_id)",
            "CREATE INDEX IF NOT EXISTS ix_file_codes_hits ON file_codes(hits)",
        ]:
            try:
                await conn.execute(text(idx_sql))
            except Exception:
                pass

    async with async_session() as session:
        defaults = {
            "page_cooldown": "3",
            "msgs_per_page": "1",
        }
        for k, v in defaults.items():
            res = await session.execute(select(SystemConfig).where(SystemConfig.key == k))
            if not res.scalar_one_or_none():
                session.add(SystemConfig(key=k, value=v))

        await session.commit()

    logger.info("✅ 数据库初始化完成 (SQLite)")
