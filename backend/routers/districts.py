"""
District CRUD endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional

from database import get_table
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
from cognito_auth import require_admin_role
from validation import (
    validate_search_query,
    validate_name_filter,
    validate_town_filter,
    validate_district_id
)
from error_handlers import safe_create_district_error
from rate_limiter import limiter, GENERAL_RATE_LIMIT, SEARCH_RATE_LIMIT, WRITE_RATE_LIMIT

router = APIRouter(prefix="/api/districts", tags=["districts"])


@router.get("", response_model=DistrictListResponse)
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


@router.get("/search", response_model=DistrictListResponse)
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


@router.get("/{district_id}", response_model=DistrictResponse)
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


@router.post("", response_model=DistrictResponse, status_code=201)
@limiter.limit(WRITE_RATE_LIMIT)
async def create_district(
    request: Request,
    district: DistrictCreate,
    user: dict = Depends(require_admin_role),
):
    """Create a new district (requires admin authentication)"""
    try:
        # Lazily get the table after auth to avoid accessing DynamoDB for unauthorized requests
        table = get_table()
        district_dict = DynamoDBDistrictService.create_district(table=table, district_data=district)
        return DistrictResponse(**district_dict)
    except Exception as e:
        raise safe_create_district_error(e)


@router.put("/{district_id}", response_model=DistrictResponse)
@limiter.limit(WRITE_RATE_LIMIT)
async def update_district(
    request: Request,
    district_id: str,
    district: DistrictUpdate,
    user: dict = Depends(require_admin_role),
):
    """Update a district (requires admin authentication)"""
    # Validate district ID
    validated_district_id = validate_district_id(district_id)

    table = get_table()
    district_dict = DynamoDBDistrictService.update_district(
        table=table,
        district_id=validated_district_id,
        district_data=district
    )
    if not district_dict:
        raise HTTPException(status_code=404, detail="District not found")

    return DistrictResponse(**district_dict)


@router.delete("/{district_id}", status_code=204)
@limiter.limit(WRITE_RATE_LIMIT)
async def delete_district(
    request: Request,
    district_id: str,
    user: dict = Depends(require_admin_role),
):
    """Delete a district (requires admin authentication)"""
    # Validate district ID
    validated_district_id = validate_district_id(district_id)

    table = get_table()
    success = DynamoDBDistrictService.delete_district(table=table, district_id=validated_district_id)
    if not success:
        raise HTTPException(status_code=404, detail="District not found")
    return None
