"""SQLAlchemy 声明基类回归测试。"""

from sqlalchemy.orm import DeclarativeBase

from app.database.base import Base


def test_model_base_uses_sqlalchemy_2_declarative_base() -> None:
    assert issubclass(Base, DeclarativeBase)
