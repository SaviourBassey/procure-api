import os

from msflib.api.deps import get_keystore_factory, get_session_factory
from msflib.db.sqlite import enable_savepoints
from sqlmodel import create_engine

from app.core.config import settings

core = settings.scope("CORE")

use_sqlite = os.getenv("USE_SQLITE", "true").lower() == "true"

if use_sqlite:
    database_url = core.SQLITE_DATABASE_URI
    connect_args = {"check_same_thread": False}
else:
    database_url = os.environ["DATABASE_URL"]
    database_url = database_url.replace(
        "postgres://", "postgresql://", 1
    )
    connect_args = {}

engine = create_engine(
    database_url,
    connect_args=connect_args,
)

if use_sqlite:
    engine = enable_savepoints(engine)

get_session = get_session_factory(engine)
get_keystore = get_keystore_factory()
