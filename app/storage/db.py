"""Database placeholders."""

from sqlalchemy import create_engine


def create_db_engine(database_url: str):
    return create_engine(database_url, future=True)
