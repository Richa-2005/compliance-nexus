from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.seed import seed_database_if_empty

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