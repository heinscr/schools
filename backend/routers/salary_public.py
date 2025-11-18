"""
Public salary query endpoints
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import os
import boto3
import logging

from services.salary_service import (
    get_salary_schedule_for_district,
    compare_salaries_across_districts,
    get_district_salary_metadata,
    get_global_salary_metadata
)
from rate_limiter import limiter, GENERAL_RATE_LIMIT

# Configure logging
logger = logging.getLogger(__name__)

# Initialize DynamoDB for salary data
# AWS_REGION is automatically provided by Lambda runtime, fallback to us-east-1 for local dev
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME')

main_table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

router = APIRouter(prefix="/api", tags=["salary"])


@router.get("/salary-schedule/{district_id}")
@router.get("/salary-schedule/{district_id}/{year}")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_salary_schedule(request: Request, district_id: str, year: Optional[str] = None):
    """Get salary schedule(s) for a district"""
    try:
        result = get_salary_schedule_for_district(main_table, district_id, year)
        if not result:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salary-compare")
@limiter.limit(GENERAL_RATE_LIMIT)
async def compare_salaries(
    request: Request,
    education: str = Query(..., description="Education level (B, M, D)"),
    credits: int = Query(..., description="Additional credits"),
    step: int = Query(..., description="Experience step"),
    districtType: Optional[str] = Query(None, description="District type filter"),
    year: Optional[str] = Query(None, description="School year filter"),
    include_fallback: bool = Query(False, description="Enable cross-education fallback matching")
):
    """Compare salaries across districts"""
    try:
        result = compare_salaries_across_districts(
            main_table,
            education,
            credits,
            step,
            district_type=districtType,
            year_param=year,
            include_fallback=include_fallback
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salary-heatmap")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_salary_heatmap(
    request: Request,
    education: str = Query(..., description="Education level (B, M, D)"),
    credits: int = Query(..., description="Additional credits"),
    step: int = Query(..., description="Experience step"),
    year: Optional[str] = Query(None, description="School year"),
    include_fallback: bool = Query(False, description="Enable cross-education fallback matching")
):
    """Get salary heatmap data"""
    try:
        # Heatmap uses the same logic as comparison
        result = compare_salaries_across_districts(
            main_table,
            education,
            credits,
            step,
            year_param=year,
            include_fallback=include_fallback
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/districts/{district_id}/salary-metadata")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_salary_metadata(request: Request, district_id: str):
    """Get salary metadata for a district"""
    try:
        result = get_district_salary_metadata(main_table, district_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/salary-metadata")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_global_salary_metadata_route(request: Request):
    """Return global salary metadata (max_step and edu_credit_combos)"""
    try:
        result = get_global_salary_metadata(main_table)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
