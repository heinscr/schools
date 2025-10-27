from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="MA Teachers Contracts API",
    description="API for looking up Massachusetts teachers contracts",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "MA Teachers Contracts API",
        "version": "0.1.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# TODO: Add contract lookup endpoints
# @app.get("/api/contracts")
# @app.get("/api/contracts/{contract_id}")
# @app.get("/api/districts")
