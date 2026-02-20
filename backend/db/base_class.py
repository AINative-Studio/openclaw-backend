"""
SQLAlchemy base class for models

Re-exports the declarative base from base.py for model inheritance.
"""
from backend.db.base import Base

__all__ = ["Base"]
