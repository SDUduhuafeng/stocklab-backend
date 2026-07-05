"""
StockLab 数据库模块 - SQLite 持久化存储
"""
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///stocklab.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class WatchlistStock(Base):
    """自选股表"""
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, unique=True)
    name = Column(String(50), nullable=False)
    group = Column(String(20), default="focus")  # focus / watch
    added_at = Column(String(20), default=lambda: datetime.now().strftime("%Y-%m-%d"))


class TradeLog(Base):
    """交易记录表"""
    __tablename__ = "trade_logs"
    id = Column(String(30), primary_key=True)
    stock = Column(String(100), nullable=False)  # "600519 贵州茅台"
    direction = Column(String(10), nullable=False)  # buy / sell
    price = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    fee = Column(Float, default=0)
    time = Column(String(20), nullable=False)
    note = Column(Text, default="")
    profit = Column(Float, nullable=True)


class TradePlan(Base):
    """交易方案表"""
    __tablename__ = "trade_plans"
    id = Column(String(30), primary_key=True)
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(String(20), nullable=False)


def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()