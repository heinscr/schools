from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from typing import Optional
from contextlib import asynccontextmanager
import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

from database import get_table, init_db
from schemas import (
    DistrictCreate,
    DistrictUpdate,
    DistrictResponse,
    DistrictListResponse
)
from services.dynamodb_district_service import DynamoDBDistrictService
from config import (
    MAX_QUERY_LIMIT,
    DEFAULT_QUERY_LIMIT,
    MIN_QUERY_LIMIT,
    DEFAULT_OFFSET
)
from auth import require_api_key
from validation import validate_search_query, validate_name_filter, validate_town_filter, validate_district_id
from error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
    safe_create_district_error
)
from rate_limiter import (
    limiter,
    get_rate_limit_handler,
    GENERAL_RATE_LIMIT,
    SEARCH_RATE_LIMIT,
    WRITE_RATE_LIMIT
)
from slowapi.errors import RateLimitExceeded

# Load environment from .env for local development
load_dotenv()


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
    "X-API-Key",  # Our custom API key header
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


@app.get("/")
async def root():
    return {
        "message": "MA Teachers Contracts API",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# District endpoints
@app.get("/api/districts", response_model=DistrictListResponse)
@limiter.limit(GENERAL_RATE_LIMIT)
async def list_districts(
    request: Request,
    name: Optional[str] = Query(None, description="Filter by district name (partial match)"),
    town: Optional[str] = Query(None, description="Filter by town name (partial match)"),
    limit: int = Query(DEFAULT_QUERY_LIMIT, ge=MIN_QUERY_LIMIT, le=MAX_QUERY_LIMIT, description="Number of results to return"),
    offset: int = Query(DEFAULT_OFFSET, ge=0, description="Number of results to skip"),
    table = Depends(get_table)
):
    """List all districts with optional filtering"""
    # Validate inputs
    validated_name = validate_name_filter(name)
    validated_town = validate_town_filter(town)

    districts, total = DynamoDBDistrictService.get_districts(
        table=table,
        name=validated_name,
        town=validated_town,
        limit=limit,
        offset=offset
    )

    # Convert districts to response format
    district_responses = [DistrictResponse(**district) for district in districts]

    return DistrictListResponse(
        data=district_responses,
        total=total,
        limit=limit,
        offset=offset
    )


@app.get("/api/districts/search", response_model=DistrictListResponse)
@limiter.limit(SEARCH_RATE_LIMIT)
async def search_districts(
    request: Request,
    q: Optional[str] = Query(None, description="Search query (searches both district names and towns)"),
    limit: int = Query(DEFAULT_QUERY_LIMIT, ge=MIN_QUERY_LIMIT, le=MAX_QUERY_LIMIT, description="Number of results to return"),
    offset: int = Query(DEFAULT_OFFSET, ge=0, description="Number of results to skip"),
    table = Depends(get_table)
):
    """Search districts by name or town"""
    # Validate search query input
    validated_query = validate_search_query(q)

    districts, total = DynamoDBDistrictService.search_districts(
        table=table,
        query_text=validated_query,
        limit=limit,
        offset=offset
    )

    # Convert districts to response format
    district_responses = [DistrictResponse(**district) for district in districts]

    return DistrictListResponse(
        data=district_responses,
        total=total,
        limit=limit,
        offset=offset
    )


@app.get("/api/districts/{district_id}", response_model=DistrictResponse)
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_district(
    request: Request,
    district_id: str,
    table = Depends(get_table)
):
    """Get a specific district by ID"""
    # Validate district ID
    validated_district_id = validate_district_id(district_id)

    district = DynamoDBDistrictService.get_district(table=table, district_id=validated_district_id)
    if not district:
        raise HTTPException(status_code=404, detail="District not found")

    return DistrictResponse(**district)


@app.post("/api/districts", response_model=DistrictResponse, status_code=201)
@limiter.limit(WRITE_RATE_LIMIT)
async def create_district(
    request: Request,
    district: DistrictCreate,
    table = Depends(get_table),
    api_key: str = Depends(require_api_key)
):
    """Create a new district (requires API key)"""
    try:
        district_dict = DynamoDBDistrictService.create_district(table=table, district_data=district)
        return DistrictResponse(**district_dict)
    except Exception as e:
        raise safe_create_district_error(e)


@app.put("/api/districts/{district_id}", response_model=DistrictResponse)
@limiter.limit(WRITE_RATE_LIMIT)
async def update_district(
    request: Request,
    district_id: str,
    district: DistrictUpdate,
    table = Depends(get_table),
    api_key: str = Depends(require_api_key)
):
    """Update a district (requires API key)"""
    # Validate district ID
    validated_district_id = validate_district_id(district_id)

    district_dict = DynamoDBDistrictService.update_district(
        table=table,
        district_id=validated_district_id,
        district_data=district
    )
    if not district_dict:
        raise HTTPException(status_code=404, detail="District not found")

    return DistrictResponse(**district_dict)


@app.delete("/api/districts/{district_id}", status_code=204)
@limiter.limit(WRITE_RATE_LIMIT)
async def delete_district(
    request: Request,
    district_id: str,
    table = Depends(get_table),
    api_key: str = Depends(require_api_key)
):
    """Delete a district (requires API key)"""
    # Validate district ID
    validated_district_id = validate_district_id(district_id)

    success = DynamoDBDistrictService.delete_district(table=table, district_id=validated_district_id)
    if not success:
        raise HTTPException(status_code=404, detail="District not found")
    return None


# Salary endpoints (delegating to salaries module functions)
# Initialize DynamoDB for salary data
dynamodb = boto3.resource('dynamodb')
SALARIES_TABLE_NAME = os.getenv('SALARIES_TABLE_NAME')
SCHEDULES_TABLE_NAME = os.getenv('SCHEDULES_TABLE_NAME')
DISTRICTS_TABLE_NAME = os.getenv('DISTRICTS_TABLE_NAME')

salaries_table = dynamodb.Table(SALARIES_TABLE_NAME) if SALARIES_TABLE_NAME else None
schedules_table = dynamodb.Table(SCHEDULES_TABLE_NAME) if SCHEDULES_TABLE_NAME else None


# Import salary functions from salaries module
import salaries


@app.get("/api/salary-schedule/{district_id}")
@app.get("/api/salary-schedule/{district_id}/{year}")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_salary_schedule(request: Request, district_id: str, year: Optional[str] = None):
    """Get salary schedule(s) for a district"""
    # Set the table references in the salaries module
    salaries.schedules_table = schedules_table
    result = salaries.get_salary_schedule(district_id, year)

    # Convert Lambda response to FastAPI response
    if result['statusCode'] != 200:
        raise HTTPException(status_code=result['statusCode'], detail=json.loads(result['body']))
    return json.loads(result['body'])


@app.get("/api/salary-compare")
@limiter.limit(GENERAL_RATE_LIMIT)
async def compare_salaries(
    request: Request,
    education: str = Query(..., description="Education level (B, M, D)"),
    credits: int = Query(..., description="Additional credits"),
    step: int = Query(..., description="Experience step"),
    districtType: Optional[str] = Query(None, description="District type filter"),
    year: Optional[str] = Query(None, description="School year filter"),
    limit: Optional[int] = Query(None, description="Result limit")
):
    """Compare salaries across districts"""
    # Set the table references in the salaries module
    salaries.salaries_table = salaries_table
    salaries.DISTRICTS_TABLE_NAME = DISTRICTS_TABLE_NAME

    params = {
        'education': education,
        'credits': str(credits),
        'step': str(step)
    }
    if districtType:
        params['districtType'] = districtType
    if year:
        params['year'] = year
    if limit:
        params['limit'] = str(limit)

    result = salaries.compare_salaries(params)

    # Convert Lambda response to FastAPI response
    if result['statusCode'] != 200:
        raise HTTPException(status_code=result['statusCode'], detail=json.loads(result['body']))
    return json.loads(result['body'])


@app.get("/api/salary-heatmap")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_salary_heatmap(
    request: Request,
    education: str = Query(..., description="Education level (B, M, D)"),
    credits: int = Query(..., description="Additional credits"),
    step: int = Query(..., description="Experience step"),
    year: Optional[str] = Query('2021-2022', description="School year")
):
    """Get salary heatmap data"""
    # Set the table references in the salaries module
    salaries.salaries_table = salaries_table

    params = {
        'education': education,
        'credits': str(credits),
        'step': str(step),
        'year': year
    }

    result = salaries.get_salary_heatmap(params)

    # Convert Lambda response to FastAPI response
    if result['statusCode'] != 200:
        raise HTTPException(status_code=result['statusCode'], detail=json.loads(result['body']))
    return json.loads(result['body'])


@app.get("/api/districts/{district_id}/salary-metadata")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_salary_metadata(request: Request, district_id: str):
    """Get salary metadata for a district"""
    # Set the table references in the salaries module
    salaries.schedules_table = schedules_table

    result = salaries.get_salary_metadata(district_id)

    # Convert Lambda response to FastAPI response
    if result['statusCode'] != 200:
        raise HTTPException(status_code=result['statusCode'], detail=json.loads(result['body']))
    return json.loads(result['body'])


# Lambda handler (only needed for AWS deployment)
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not installed - fine for local development
    pass
