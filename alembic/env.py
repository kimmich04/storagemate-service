"""Alembic env: lấy DATABASE_URL từ app/config.py, metadata từ app/models.py."""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import model của mọi domain để Base.metadata biết đủ bảng khi --autogenerate
from app.auth import models as _auth_models  # noqa: F401
from app.config import settings
from app.inventory import models as _inventory_models  # noqa: F401
from app.items import models as _items_models  # noqa: F401
from app.labels import models as _labels_models  # noqa: F401
from app.messaging import models as _messaging_models  # noqa: F401
from app.models import Base
from app.staff import models as _staff_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
