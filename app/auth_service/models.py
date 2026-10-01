from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from auth_service.database import Base


class User(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)