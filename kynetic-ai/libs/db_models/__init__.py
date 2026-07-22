"""
libs/db_models — Shared SQLAlchemy 2.0 async models + Alembic migration setup.

All Kynetic AI services share one PostgreSQL database.
Tables are logically owned per service domain but physically in one DB.
"""
