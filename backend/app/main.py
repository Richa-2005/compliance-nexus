from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.seed import seed_database_if_empty
from app.api.v1.auth import auth_router
from app.api.v1.audits import audits_router
from app.api.v1.documents import documents_router
from app.api.v1.websockets import ws_router
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
  
    seed_database_if_empty()
    yield
    print("ComplianceNexus Engine Shutting Down...")

app = FastAPI(
    title="ComplianceNexus API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.API_V1_PREFIX, tags=["Auth"])
app.include_router(audits_router, prefix=settings.API_V1_PREFIX, tags=["Audit Engine"])
app.include_router(documents_router, prefix=settings.API_V1_PREFIX, tags=["Async Documents"])
app.include_router(ws_router, tags=["WebSocket Live Feed"])
