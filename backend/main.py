from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
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

# Configure CORS
# Get allowed origins from environment or use defaults
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://school.crackpow.com"
]

# Add CloudFront domain from environment if set
cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
if cloudfront_domain:
    allowed_origins.append(f"https://{cloudfront_domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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


# District endpoints
@app.get("/api/districts", response_model=DistrictListResponse)
async def list_districts(
    name: Optional[str] = Query(None, description="Filter by district name (partial match)"),
    town: Optional[str] = Query(None, description="Filter by town name (partial match)"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    table = Depends(get_table)
):
    """List all districts with optional filtering"""
    districts, total = DynamoDBDistrictService.get_districts(
        table=table,
        name=name,
        town=town,
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
async def search_districts(
    q: Optional[str] = Query(None, description="Search query (searches both district names and towns)"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    table = Depends(get_table)
):
    """Search districts by name or town"""
    districts, total = DynamoDBDistrictService.search_districts(
        table=table,
        query_text=q,
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
async def get_district(
    district_id: str,
    table = Depends(get_table)
):
    """Get a specific district by ID"""
    district = DynamoDBDistrictService.get_district(table=table, district_id=district_id)
    if not district:
        raise HTTPException(status_code=404, detail="District not found")

    return DistrictResponse(**district)


@app.post("/api/districts", response_model=DistrictResponse, status_code=201)
async def create_district(
    district: DistrictCreate,
    table = Depends(get_table)
):
    """Create a new district"""
    try:
        district_dict = DynamoDBDistrictService.create_district(table=table, district_data=district)
        return DistrictResponse(**district_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/districts/{district_id}", response_model=DistrictResponse)
async def update_district(
    district_id: str,
    district: DistrictUpdate,
    table = Depends(get_table)
):
    """Update a district"""
    district_dict = DynamoDBDistrictService.update_district(
        table=table,
        district_id=district_id,
        district_data=district
    )
    if not district_dict:
        raise HTTPException(status_code=404, detail="District not found")

    return DistrictResponse(**district_dict)


@app.delete("/api/districts/{district_id}", status_code=204)
async def delete_district(
    district_id: str,
    table = Depends(get_table)
):
    """Delete a district"""
    success = DynamoDBDistrictService.delete_district(table=table, district_id=district_id)
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
async def get_salary_schedule(district_id: str, year: Optional[str] = None):
    """Get salary schedule(s) for a district"""
    # Set the table references in the salaries module
    salaries.schedules_table = schedules_table
    result = salaries.get_salary_schedule(district_id, year)

    # Convert Lambda response to FastAPI response
    if result['statusCode'] != 200:
        raise HTTPException(status_code=result['statusCode'], detail=json.loads(result['body']))
    return json.loads(result['body'])


@app.get("/api/salary-compare")
async def compare_salaries(
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
async def get_salary_heatmap(
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
async def get_salary_metadata(district_id: str):
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
