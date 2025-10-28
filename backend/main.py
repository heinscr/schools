from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from database import get_table, init_db
from schemas import (
    DistrictCreate,
    DistrictUpdate,
    DistrictResponse,
    DistrictListResponse
)
from services.dynamodb_district_service import DynamoDBDistrictService

app = FastAPI(
    title="MA Teachers Contracts API",
    description="API for looking up Massachusetts teachers contracts",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://d3hl4i100v66fx.cloudfront.net",
        "https://school.crackpow.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()


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


# TODO: Add contract lookup endpoints
# @app.get("/api/contracts")
# @app.get("/api/contracts/{contract_id}")

# Lambda handler
from mangum import Mangum
handler = Mangum(app)
