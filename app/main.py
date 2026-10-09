import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from msflib.eventbus import bind_app_emitter
from sqlmodel import SQLModel

import app.models  # Registers Account and Profile tables
from app.api.router import api_router
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
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

bind_app_emitter(app)
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Health"])
def root():
    return {"message": "Procure API is running", "docs": "/docs"}
