"""Repository layer for auth persistence operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.auth.settings import get_settings


class AuthRepositoryError(Exception):
    """Raised when SQL auth lookup fails."""


@dataclass(slots=True)
class ActiveUserRole:
    """Normalized active user record with role resolved from lookup table."""

    user_id: int
    email: str
    role_id: int
    role_name: str


@dataclass(slots=True)
class UserRecord:
    """Normalized user record mapped from users table."""

    user_id: int
    email: str
    role: str
    is_active: bool
    created_by: str
    created_at: datetime
    updated_by: str
    updated_at: datetime


@dataclass(slots=True)
class AuthRepository:
    """Lookup active users and roles from MySQL for auth decisions."""

    session_factory: sessionmaker[Session]

    def get_active_user_role_by_email(self, email: str) -> ActiveUserRole | None:
        query = text(
            """
            SELECT
                u.user_id,
                u.email,
                u.role_id,
                l.display_value AS role_name
            FROM users u
            INNER JOIN lookup l ON l.lookup_id = u.role_id
            WHERE LOWER(u.email) = LOWER(:email)
              AND u.is_active = TRUE
              AND l.category = 'Role'
              AND l.is_active = TRUE
            LIMIT 1
            """
        )

        try:
            with self.session_factory() as session:
                row = session.execute(query, {"email": email}).mappings().first()
        except OperationalError as exc:
            if "(1045" in str(exc) or "Access denied for user" in str(exc):
                raise AuthRepositoryError(
                    "MySQL authentication failed. Check MYSQL_USER/MYSQL_PASSWORD and user grants."
                ) from exc
            raise AuthRepositoryError("Failed to connect to MySQL for user validation") from exc
        except SQLAlchemyError as exc:
            raise AuthRepositoryError("Failed to validate user against MySQL") from exc

        if row is None:
            return None

        return ActiveUserRole(
            user_id=int(row["user_id"]),
            email=str(row["email"]),
            role_id=int(row["role_id"]),
            role_name=str(row["role_name"]),
        )

    def get_all_users(self) -> list[UserRecord]:
        query = text(
            """
            SELECT
                u.user_id,
                u.email,
                l.display_value AS role,
                u.is_active,
                u.created_by,
                u.created_at,
                u.updated_by,
                u.updated_at
            FROM users u
            INNER JOIN lookup l ON l.lookup_id = u.role_id
            WHERE l.category = 'Role'
            ORDER BY u.user_id ASC
            """
        )

        try:
            with self.session_factory() as session:
                rows = session.execute(query).mappings().all()
        except OperationalError as exc:
            if "(1045" in str(exc) or "Access denied for user" in str(exc):
                raise AuthRepositoryError(
                    "MySQL authentication failed. Check MYSQL_USER/MYSQL_PASSWORD and user grants."
                ) from exc
            raise AuthRepositoryError("Failed to connect to MySQL for users lookup") from exc
        except SQLAlchemyError as exc:
            raise AuthRepositoryError("Failed to fetch users from MySQL") from exc

        return [
            UserRecord(
                user_id=int(row["user_id"]),
                email=str(row["email"]),
                role=str(row["role"]),
                is_active=bool(row["is_active"]),
                created_by=str(row["created_by"]),
                created_at=row["created_at"],
                updated_by=str(row["updated_by"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return a cached SQLAlchemy session factory."""

    settings = get_settings()
    if settings.sqlalchemy_database_url:
        database_url = settings.sqlalchemy_database_url
    else:
        database_url = str(
            URL.create(
                drivername="mysql+pymysql",
                username=settings.mysql_user,
                password=settings.mysql_password,
                host=settings.mysql_host,
                port=settings.mysql_port,
                database=settings.mysql_database,
            )
        )

    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@lru_cache(maxsize=1)
def get_auth_repository() -> AuthRepository:
    """Return cached auth repository instance."""

    return AuthRepository(session_factory=get_session_factory())
