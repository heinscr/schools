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
import os
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

app = FastAPI(
    title="MA Teachers Contracts API",
    description="API for looking up Massachusetts teachers contracts",
    version="0.1.0"
)

# Load environment from .env for local development
load_dotenv()

# Configure CORS
# Allow CloudFront domains (*.cloudfront.net) and custom domain
import os

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

# Lambda handler (only needed for AWS deployment)
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not installed - fine for local development
    pass

# ==========================
# Local salary API endpoints
# ==========================

# Resolve tables for local use (or AWS if no local endpoint)
SALARIES_TABLE_NAME = os.environ.get("SALARIES_TABLE_NAME") or os.environ.get("teacher_salaries_table_name") or "crackpow-schools-teacher-salaries"
SCHEDULES_TABLE_NAME = os.environ.get("SCHEDULES_TABLE_NAME") or os.environ.get("teacher_salary_schedules_table_name") or "crackpow-schools-teacher-salary-schedules"
DISTRICTS_TABLE_NAME = os.environ.get("DYNAMODB_DISTRICTS_TABLE") or os.environ.get("dynamodb_districts_table_name") or "crackpow-schools-districts"

_dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-2'))
_dynamodb_client = boto3.client('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-2'))

_salaries_table = _dynamodb.Table(SALARIES_TABLE_NAME) if SALARIES_TABLE_NAME else None
_schedules_table = _dynamodb.Table(SCHEDULES_TABLE_NAME) if SCHEDULES_TABLE_NAME else None
_districts_table_name = DISTRICTS_TABLE_NAME


def _dec2float(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def _get_district_towns(district_ids):
    if not _districts_table_name or not district_ids:
        return {}
    result = {}
    try:
        for i in range(0, len(district_ids), 100):
            batch = district_ids[i:i+100]
            keys = [
                {'PK': {'S': f'DISTRICT#{did}'}, 'SK': {'S': 'METADATA'}}
                for did in batch if did
            ]
            if not keys:
                continue
            resp = _dynamodb_client.batch_get_item(RequestItems={_districts_table_name: {'Keys': keys}})
            items = resp.get('Responses', {}).get(_districts_table_name, [])
            for item in items:
                did_attr = item.get('district_id', {})
                did = did_attr.get('S') if isinstance(did_attr, dict) else None
                towns_attr = item.get('towns', {})
                towns = []
                if isinstance(towns_attr, dict) and 'L' in towns_attr:
                    towns = [t.get('S', '') for t in towns_attr['L'] if isinstance(t, dict)]
                if did:
                    result[did] = towns
    except Exception:
        # Fail soft for local
        return {}
    return result


@app.get("/api/salary-compare")
async def api_salary_compare(
    education: str = Query(...),
    credits: int = Query(...),
    step: int = Query(...),
    districtType: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
):
    if not _salaries_table:
        raise HTTPException(status_code=503, detail="Salaries table not configured")
    try:
        query_params = {
            'IndexName': 'CompareDistrictsIndex',
            'KeyConditionExpression': Key('GSI2PK').eq(f'COMPARE#{education}#{credits}#{step}'),
            'ScanIndexForward': False
        }
        filter_parts = []
        expr_vals = {}
        if year:
            filter_parts.append('school_year = :year')
            expr_vals[':year'] = year
        if districtType:
            filter_parts.append('district_type = :dtype')
            expr_vals[':dtype'] = districtType
        if filter_parts:
            query_params['FilterExpression'] = ' AND '.join(filter_parts)
            query_params['ExpressionAttributeValues'] = expr_vals

        resp = _salaries_table.query(**query_params)
        items = resp.get('Items', [])

        # Deduplicate per district by most recent (year, period)
        district_map = {}
        for item in items:
            did = item.get('district_id')
            yr = item.get('school_year', '')
            per = item.get('period', '')
            if did not in district_map or (yr, per) > (
                district_map[did].get('school_year', ''), district_map[did].get('period', '')
            ):
                district_map[did] = item

        dedup = sorted(district_map.values(), key=lambda x: float(x.get('salary', 0)), reverse=True)
        district_ids = [x.get('district_id') for x in dedup]
        towns_map = _get_district_towns(district_ids)

        results = [
            {
                'rank': idx + 1,
                'district_id': it.get('district_id'),
                'district_name': it.get('district_name'),
                'district_type': it.get('district_type'),
                'school_year': it.get('school_year'),
                'period': it.get('period'),
                'education': it.get('education'),
                'credits': it.get('credits'),
                'step': it.get('step'),
                'salary': _dec2float(it.get('salary', 0)),
                'towns': towns_map.get(it.get('district_id'), []),
            }
            for idx, it in enumerate(dedup)
        ]
        return {
            'query': {
                'education': education,
                'credits': credits,
                'step': step,
                'districtType': districtType,
                'year': year,
            },
            'results': results,
            'total': len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/salary-heatmap")
async def api_salary_heatmap(
    education: str = Query(...),
    credits: int = Query(...),
    step: int = Query(...),
    year: Optional[str] = Query(None),
):
    if not _salaries_table:
        raise HTTPException(status_code=503, detail="Salaries table not configured")
    try:
        query_params = {
            'IndexName': 'CompareDistrictsIndex',
            'KeyConditionExpression': Key('GSI2PK').eq(f'COMPARE#{education}#{credits}#{step}')
        }
        # Optional year filter
        if year:
            query_params['FilterExpression'] = Key('school_year').eq(year)

        resp = _salaries_table.query(**query_params)
        items = resp.get('Items', [])
        data = [
            {
                'district_id': it.get('district_id'),
                'district_name': it.get('district_name'),
                'district_type': it.get('district_type'),
                'salary': _dec2float(it.get('salary', 0)),
            }
            for it in items
        ]
        if data:
            vals = [d['salary'] for d in data]
            stats = {
                'min': min(vals),
                'max': max(vals),
                'avg': sum(vals) / len(vals),
                'median': sorted(vals)[len(vals)//2],
            }
        else:
            stats = {'min': None, 'max': None, 'avg': None, 'median': None}

        return {
            'query': {'education': education, 'credits': credits, 'step': step, 'year': year},
            'statistics': stats,
            'data': data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/salary-schedule/{district_id}")
@app.get("/api/salary-schedule/{district_id}/{year}")
async def api_salary_schedule(district_id: str, year: Optional[str] = None):
    if not _schedules_table:
        raise HTTPException(status_code=503, detail="Schedules table not configured")
    try:
        key_cond = Key('district_id').eq(district_id)
        if year:
            key_cond = key_cond & Key('schedule_key').begins_with(year)
        resp = _schedules_table.query(KeyConditionExpression=key_cond)
        items = resp.get('Items', [])
        if not items:
            raise HTTPException(status_code=404, detail='Schedule not found')
        # Convert Decimals
        def conv(x):
            if isinstance(x, list):
                return [conv(v) for v in x]
            if isinstance(x, dict):
                return {k: conv(v) for k, v in x.items()}
            return _dec2float(x)
        return conv(items)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/districts/{district_id}/salary-metadata")
async def api_salary_metadata(district_id: str):
    if not _schedules_table:
        raise HTTPException(status_code=503, detail="Schedules table not configured")
    try:
        resp = _schedules_table.query(KeyConditionExpression=Key('district_id').eq(district_id))
        items = resp.get('Items', [])
        if not items:
            raise HTTPException(status_code=404, detail='No salary data found for district')
        years = sorted(list(set(item.get('school_year') for item in items)))
        latest = max(items, key=lambda x: x.get('school_year', ''))
        min_salary = float('inf')
        max_salary = float('-inf')
        for entry in latest.get('salaries', []) or []:
            try:
                sal = float(entry.get('salary', 0))
            except Exception:
                sal = 0.0
            min_salary = min(min_salary, sal)
            max_salary = max(max_salary, sal)
        return {
            'district_id': district_id,
            'district_name': latest.get('district_name'),
            'available_years': years,
            'latest_year': years[-1] if years else None,
            'salary_range': {
                'min': (None if min_salary == float('inf') else min_salary),
                'max': (None if max_salary == float('-inf') else max_salary),
            },
            'schedules': [
                {
                    'school_year': it.get('school_year'),
                    'period': it.get('period'),
                    'contract_term': it.get('contract_term'),
                    'contract_expiration': it.get('contract_expiration'),
                }
                for it in items
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
