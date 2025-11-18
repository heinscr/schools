"""
MA Teachers Contracts API - Main Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import os
import logging
from dotenv import load_dotenv

from database import init_db
from error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler
)
from rate_limiter import limiter, get_rate_limit_handler
from slowapi.errors import RateLimitExceeded
from fastapi import HTTPException

# Import routers
from routers import districts, auth, salary_public, salary_admin

# Re-export commonly used items for backward compatibility with tests
from services.dynamodb_district_service import DynamoDBDistrictService
from cognito_auth import require_admin_role, get_current_user_optional

# Load environment from .env for local development
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown logic"""
    # Startup: Initialize database
    init_db()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="MA Teachers Contracts API",
    description="API for looking up Massachusetts teachers contracts",
    version="0.1.0",
    lifespan=lifespan
)

# Add rate limiter state
app.state.limiter = limiter

# Register error handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(RateLimitExceeded, get_rate_limit_handler())

# Configure CORS
# Get allowed origins from environment or use defaults
allowed_origins = [
    "http://localhost:3000",  # React dev server
    "http://localhost:5173",  # Vite dev server
]

# Add custom domain from environment (production)
custom_domain = os.getenv("CUSTOM_DOMAIN")
if custom_domain:
    allowed_origins.append(f"https://{custom_domain}")

# Add CloudFront domain from environment if set
cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
if cloudfront_domain:
    allowed_origins.append(f"https://{cloudfront_domain}")

# Allowed HTTP methods - only what's needed
allowed_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

# Allowed headers - whitelist common safe headers
allowed_headers = [
    "Content-Type",
    "Authorization",
    "Accept",
    "Origin",
    "User-Agent",
    "DNT",
    "Cache-Control",
    "X-Requested-With"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Specific origins only
    allow_credentials=False,  # Disable credentials to prevent CSRF attacks
    allow_methods=allowed_methods,  # Only necessary methods
    allow_headers=allowed_headers,  # Whitelist specific headers
    expose_headers=[],  # Don't expose any custom headers
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Register routers
app.include_router(districts.router)
app.include_router(auth.router)
app.include_router(salary_public.router)
app.include_router(salary_admin.router)


@app.get("/")
async def root():
    return {
        "message": "MA Teachers Contracts API",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Lambda handler (only needed for AWS deployment)
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not installed - fine for local development
    pass
