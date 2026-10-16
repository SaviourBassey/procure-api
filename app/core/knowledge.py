"""Process-wide knowledge engine backed by this app's database session."""

from msflib.knowledge.deps import get_knowledge_dependencies
from msflib.knowledge.service import KnowledgeEngine
from sqlmodel import Session

from app.core.config import settings
from app.db.session import engine

_knowledge_engine: KnowledgeEngine | None = None


def get_knowledge_engine() -> KnowledgeEngine:
    global _knowledge_engine
    if _knowledge_engine is None:
        _knowledge_engine = get_knowledge_dependencies(
            settings,
            session_factory=lambda: Session(engine),
        ).build_knowledge_engine()
    return _knowledge_engine
