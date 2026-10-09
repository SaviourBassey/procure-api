from msflib.api.deps import get_keystore_factory, get_session_factory
from msflib.db.sqlite import enable_savepoints
from sqlmodel import create_engine

from app.core.config import settings

core = settings.scope("CORE")

engine = enable_savepoints(
    create_engine(
        core.SQLITE_DATABASE_URI,
        connect_args={"check_same_thread": False},
    )
)

get_session = get_session_factory(engine)
get_keystore = get_keystore_factory()
