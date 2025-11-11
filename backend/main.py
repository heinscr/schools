from fastapi import FastAPI, Depends, HTTPException, Query, Request, UploadFile, File
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
from services.salary_jobs import SalaryJobsService
from config import (
    MAX_QUERY_LIMIT,
    DEFAULT_QUERY_LIMIT,
    MIN_QUERY_LIMIT,
    DEFAULT_OFFSET
)
from cognito_auth import require_admin_role, get_current_user_optional
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
    user: dict = Depends(require_admin_role)
):
    """Create a new district (requires admin authentication)"""
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
    user: dict = Depends(require_admin_role)
):
    """Update a district (requires admin authentication)"""
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
    user: dict = Depends(require_admin_role)
):
    """Delete a district (requires admin authentication)"""
    # Validate district ID
    validated_district_id = validate_district_id(district_id)

    success = DynamoDBDistrictService.delete_district(table=table, district_id=validated_district_id)
    if not success:
        raise HTTPException(status_code=404, detail="District not found")
    return None


@app.get("/api/auth/me")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_current_user(
    request: Request,
    user: dict = Depends(get_current_user_optional)
):
    """Get current authenticated user information"""
    if not user:
        return {
            "authenticated": False,
            "user": None
        }

    return {
        "authenticated": True,
        "user": {
            "email": user.get("email"),
            "username": user.get("username"),
            "is_admin": user.get("is_admin", False),
            "groups": user.get("groups", [])
        }
    }


# Salary endpoints - Native FastAPI implementation
# Initialize DynamoDB for salary data
# AWS_REGION is automatically provided by Lambda runtime, fallback to us-east-1 for local dev
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME')

main_table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# Initialize S3, SQS, and Lambda clients for salary processing
s3_client = boto3.client('s3', region_name=AWS_REGION)
sqs_client = boto3.client('sqs', region_name=AWS_REGION)
lambda_client = boto3.client('lambda', region_name=AWS_REGION)

# Get environment variables for salary processing
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
SQS_QUEUE_URL = os.getenv('SALARY_PROCESSING_QUEUE_URL')
NORMALIZER_LAMBDA_ARN = os.getenv('SALARY_NORMALIZER_LAMBDA_ARN')

# Initialize salary jobs service
salary_jobs_service = None
if main_table and S3_BUCKET_NAME and SQS_QUEUE_URL:
    salary_jobs_service = SalaryJobsService(
        dynamodb_table=main_table,
        s3_client=s3_client,
        sqs_client=sqs_client,
        queue_url=SQS_QUEUE_URL,
        bucket_name=S3_BUCKET_NAME
    )

# Import salary service functions
from services.salary_service import (
    get_salary_schedule_for_district,
    compare_salaries_across_districts,
    get_district_salary_metadata
)
from services.salary_service import get_global_salary_metadata


@app.get("/api/salary-schedule/{district_id}")
@app.get("/api/salary-schedule/{district_id}/{year}")
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


@app.get("/api/salary-compare")
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


@app.get("/api/salary-heatmap")
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


@app.get("/api/districts/{district_id}/salary-metadata")
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


@app.get("/api/salary-metadata")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_global_salary_metadata_route(request: Request):
    """Return global salary metadata (max_step and edu_credit_combos)"""
    try:
        result = get_global_salary_metadata(main_table)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Admin Salary Processing Endpoints
# ============================================================================

@app.post("/api/admin/districts/{district_id}/salary-schedule/upload")
@limiter.limit(WRITE_RATE_LIMIT)
async def upload_salary_schedule(
    request: Request,
    district_id: str,
    file: UploadFile = File(...),
    table = Depends(get_table),
    user: dict = Depends(require_admin_role)
):
    """Upload a PDF contract for processing"""
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Validate district exists
    from services.dynamodb_district_service import DynamoDBDistrictService
    district = DynamoDBDistrictService.get_district(table=table, district_id=district_id)
    if not district:
        raise HTTPException(status_code=404, detail="District not found")

    try:
        # Read PDF content
        pdf_content = await file.read()

        # Create processing job
        job = salary_jobs_service.create_job(
            district_id=district_id,
            district_name=district['name'],
            pdf_content=pdf_content,
            filename=file.filename,
            uploaded_by=user['sub']
        )

        return {
            "job_id": job['job_id'],
            "status": job['status'],
            "district_id": district_id,
            "district_name": district['name']
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/api/admin/districts/{district_id}/salary-schedule/jobs/{job_id}")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_job_status(
    request: Request,
    district_id: str,
    job_id: str,
    user: dict = Depends(require_admin_role)
):
    """Get job status and extracted data preview"""
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    job = salary_jobs_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job['district_id'] != district_id:
        raise HTTPException(status_code=400, detail="Job district_id does not match")

    response = {
        "job_id": job['job_id'],
        "district_id": job['district_id'],
        "district_name": job['district_name'],
        "status": job['status'],
        "created_at": job['created_at'],
        "updated_at": job['updated_at']
    }

    if job['status'] == 'completed':
        response['records_count'] = job.get('extracted_records_count', 0)
        response['years_found'] = job.get('years_found', [])

        # Get preview data
        preview = salary_jobs_service.get_extracted_data_preview(job_id, limit=10)
        if preview:
            response['preview_records'] = preview

    elif job['status'] == 'failed':
        response['error'] = job.get('error_message', 'Unknown error')

    return response


@app.put("/api/admin/districts/{district_id}/salary-schedule/apply/{job_id}")
@limiter.limit(WRITE_RATE_LIMIT)
async def apply_salary_schedule(
    request: Request,
    district_id: str,
    job_id: str,
    user: dict = Depends(require_admin_role)
):
    """Apply extracted salary data to district"""
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    try:
        success, metadata = salary_jobs_service.apply_salary_data(job_id, district_id)

        return {
            "success": success,
            "records_added": metadata['records_added'],
            "metadata_changed": metadata['metadata_changed'],
            "needs_global_normalization": metadata['needs_global_normalization']
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(e)}")


@app.delete("/api/admin/districts/{district_id}/salary-schedule/jobs/{job_id}")
@limiter.limit(WRITE_RATE_LIMIT)
async def reject_salary_schedule(
    request: Request,
    district_id: str,
    job_id: str,
    user: dict = Depends(require_admin_role)
):
    """Reject and delete a processing job"""
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    job = salary_jobs_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job['district_id'] != district_id:
        raise HTTPException(status_code=400, detail="Job district_id does not match")

    try:
        salary_jobs_service.delete_job(job_id)
        return {"success": True, "message": "Job deleted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@app.get("/api/admin/global/normalization/status")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_normalization_status_route(
    request: Request,
    user: dict = Depends(require_admin_role)
):
    """Get global normalization status"""
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    try:
        status = salary_jobs_service.get_normalization_status()

        # Check if normalization job is running
        job = salary_jobs_service.get_normalization_job()
        if job:
            status['job_running'] = True
            status['job_started_at'] = job.get('started_at')
        else:
            status['job_running'] = False

        return status

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/global/normalize")
@limiter.limit(WRITE_RATE_LIMIT)
async def start_normalization(
    request: Request,
    user: dict = Depends(require_admin_role)
):
    """Start global normalization job"""
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    if not NORMALIZER_LAMBDA_ARN:
        raise HTTPException(status_code=503, detail="Normalizer Lambda not configured")

    try:
        job_id = salary_jobs_service.start_normalization_job(
            lambda_client=lambda_client,
            normalizer_arn=NORMALIZER_LAMBDA_ARN,
            triggered_by=user['sub']
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": "Normalization job started"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start normalization: {str(e)}")


# Lambda handler (only needed for AWS deployment)
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not installed - fine for local development
    pass