from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from msflib.documents.services.pipeline import register_text_document_pipeline
from msflib.eventbus import bind_app_emitter
from msflib.tenancy.resolver import resolve_default_tenant_id
from sqlmodel import Session, SQLModel

import app.models  # Registers application and msflib tables
from app.api.router import api_router
from app.core.config import settings
from app.db.session import engine
from app.events.escrow import register_escrow_listeners
from app.events.platform import register_platform_listeners


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        resolve_default_tenant_id(session, settings=settings.scope("TENANCY"))
        session.commit()
    register_text_document_pipeline()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Procurement platform API for buyers and vendors",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app_emitter = bind_app_emitter(app)
register_escrow_listeners(app_emitter)
register_platform_listeners(app_emitter)
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Health"])
def root():
    return {"message": "Procure API is running", "docs": "/docs"}
