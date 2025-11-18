from fastapi import FastAPI, Depends, HTTPException, Query, Request, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from typing import Optional, List
from contextlib import asynccontextmanager
import os
import json
import logging
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
from services.salary_jobs import SalaryJobsService, LocalSalaryJobsService
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


@app.put("/api/districts/{district_id}", response_model=DistrictResponse)
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


@app.delete("/api/districts/{district_id}", status_code=204)
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
if main_table and S3_BUCKET_NAME:
    # Allow running without SQS queue (manual apply & backups still work).
    if not SQS_QUEUE_URL:
        logger.warning("SALARY_PROCESSING_QUEUE_URL not set; PDF upload jobs disabled but manual apply will function.")
        # Provide a dummy queue url so create_job can fail gracefully if invoked
        SQS_QUEUE_URL = ""
    salary_jobs_service = SalaryJobsService(
        dynamodb_table=main_table,
        s3_client=s3_client,
        sqs_client=sqs_client,
        queue_url=SQS_QUEUE_URL,
        bucket_name=S3_BUCKET_NAME
    )
else:
    # Local development fallback: use a file-backed stub so uploads work without AWS
    local_storage = os.getenv("LOCAL_SALARY_STORAGE", "./backend/local_data")
    salary_jobs_service = LocalSalaryJobsService(storage_dir=local_storage, dynamodb_table=main_table)

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
        logger.info(f"Received PDF upload: filename='{file.filename}', content_type='{file.content_type}', size={len(pdf_content)} bytes, type={type(pdf_content)}")

        # Log first 20 bytes to diagnose encoding issues
        if len(pdf_content) > 0:
            first_bytes = pdf_content[:20]
            logger.info(f"First 20 bytes: {first_bytes}")

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
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
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

        # Get preview data (all records)
        preview = salary_jobs_service.get_extracted_data_preview(job_id, limit=None)
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

    # Parse optional exclusions from request body
    exclusions = None
    try:
        body = await request.json()
        if body:
            exclusions = {
                'excluded_steps': body.get('excluded_steps', []),
                'excluded_columns': body.get('excluded_columns', [])
            }
    except:
        # No body or invalid JSON - that's fine, no exclusions
        pass

    try:
        success, metadata = salary_jobs_service.apply_salary_data(job_id, district_id, exclusions)

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


@app.post("/api/admin/districts/{district_id}/salary-schedule/manual-apply")
@limiter.limit(WRITE_RATE_LIMIT)
async def manual_apply_salary_schedule(
    request: Request,
    district_id: str,
    table = Depends(get_table),
    user: dict = Depends(require_admin_role)
):
    """Apply salary data directly from provided records (admin-only, no job).

    Body JSON: { "records": [ { school_year, period, education, credits, step, salary, (optional) district_name } ] }
    """
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    # Validate district exists
    from services.dynamodb_district_service import DynamoDBDistrictService
    district = DynamoDBDistrictService.get_district(table=table, district_id=district_id)
    if not district:
        raise HTTPException(status_code=404, detail="District not found")

    # Parse and validate body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    records = body.get('records') if isinstance(body, dict) else None
    if not records or not isinstance(records, list):
        raise HTTPException(status_code=400, detail="'records' must be a non-empty list")

    # Ensure district_name present when missing; types will be handled in service
    district_name = district['name']
    for r in records:
        if isinstance(r, dict) and 'district_name' not in r:
            r['district_name'] = district_name

    logger.info(f"Manual apply invoked for district {district_id} with {len(records)} records; service type={type(salary_jobs_service).__name__}")
    try:
        success, metadata = salary_jobs_service.apply_salary_records(district_id, records)
        return {
            "success": success,
            "records_added": metadata['records_added'],
            "metadata_changed": metadata['metadata_changed'],
            "needs_global_normalization": metadata['needs_global_normalization']
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manual apply failed: {str(e)}")


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


@app.get("/api/admin/backup/list")
@limiter.limit(GENERAL_RATE_LIMIT)
async def list_backups(
    request: Request,
    user: dict = Depends(require_admin_role)
):
    """
    List all salary data backup files
    Requires admin authentication
    """
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    try:
        backups = salary_jobs_service.list_backups()
        return {
            "success": True,
            "backups": backups,
            "count": len(backups)
        }

    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {str(e)}")


@app.post("/api/admin/backup/reapply")
@limiter.limit(WRITE_RATE_LIMIT)
async def reapply_backups(
    request: Request,
    filenames: List[str],
    user: dict = Depends(require_admin_role)
):
    """
    Re-apply salary data from backup files
    Requires admin authentication

    Body:
        filenames: List of backup filenames to re-apply (e.g., ["Springfield.json", "Boston.json"])
    """
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    if not filenames or len(filenames) == 0:
        raise HTTPException(status_code=400, detail="No files specified")

    results = []
    errors = []

    for filename in filenames:
        try:
            success, result = salary_jobs_service.re_apply_from_backup(filename)
            results.append({
                "filename": filename,
                "success": True,
                "district_id": result['district_id'],
                "district_name": result['district_name'],
                "records_added": result['records_added'],
                "calculated_entries": result['calculated_entries']
            })
        except Exception as e:
            logger.error(f"Error re-applying backup {filename}: {e}")
            errors.append({
                "filename": filename,
                "success": False,
                "error": str(e)
            })

    return {
        "success": len(errors) == 0,
        "results": results,
        "errors": errors,
        "total_processed": len(results),
        "total_errors": len(errors)
    }


@app.post("/api/admin/backup/reapply/start")
@limiter.limit(WRITE_RATE_LIMIT)
async def start_backup_reapply_job(
    request: Request,
    filenames: List[str],
    user: dict = Depends(require_admin_role)
):
    """
    Start a background job to re-apply backup files
    Returns job_id to poll for progress

    Note: For Lambda deployment, this should invoke a separate Lambda asynchronously.
    For local/EC2 deployment, this uses threading.
    """
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    if not filenames or len(filenames) == 0:
        raise HTTPException(status_code=400, detail="No files specified")

    # Check if already running
    existing_job = salary_jobs_service.get_backup_reapply_job()
    if existing_job:
        raise HTTPException(status_code=409, detail="A backup reapply job is already running")

    try:
        # Start the job
        job_id = salary_jobs_service.start_backup_reapply_job(
            filenames=filenames,
            triggered_by=user['sub']
        )

        # Get backup reapply worker Lambda ARN from environment
        backup_worker_arn = os.getenv('BACKUP_REAPPLY_WORKER_ARN')

        if backup_worker_arn:
            # Invoke worker Lambda asynchronously (for production)
            logger.info(f"Invoking backup worker Lambda: {backup_worker_arn}")
            lambda_client.invoke(
                FunctionName=backup_worker_arn,
                InvocationType='Event',  # Async invocation
                Payload=json.dumps({
                    'job_id': job_id,
                    'filenames': filenames
                })
            )
        else:
            # For local/testing: run synchronously
            logger.warning("No BACKUP_REAPPLY_WORKER_ARN set, running synchronously")
            process_backup_reapply_job_sync(job_id, filenames)

        return {
            "job_id": job_id,
            "status": "started",
            "total": len(filenames)
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting backup reapply job: {e}")
        # Clean up the job record if it failed
        try:
            salary_jobs_service.table.delete_item(
                Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
            )
        except:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/backup/reapply/status")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_backup_reapply_status(
    request: Request,
    user: dict = Depends(require_admin_role),
    job_id: Optional[str] = Query(None)
):
    """Get status of currently running backup reapply job or specific job by ID"""
    if not salary_jobs_service:
        raise HTTPException(status_code=503, detail="Salary processing service not configured")

    try:
        # Get table instance
        table = get_table()

        # First check for running job
        job = salary_jobs_service.get_backup_reapply_job()
        logger.info(f"get_backup_reapply_status called with job_id={job_id}, running_job={'found' if job else 'not found'}")

        # If we have a job_id, we should prefer looking up that specific job
        # This handles the case where the job just completed and moved from RUNNING to archived
        if job_id:
            try:
                # First check if it's the currently running job
                if job and job.get('job_id') == job_id:
                    logger.info(f"Job {job_id} is currently running")
                else:
                    # Not running, check archived
                    logger.info(f"Looking for archived job: {job_id}")
                    response = table.get_item(
                        Key={'PK': f'BACKUP_REAPPLY_JOB#{job_id}', 'SK': 'METADATA'}
                    )
                    if 'Item' in response:
                        job = response['Item']
                        logger.info(f"Found archived job: {job_id} with status {job.get('status')}, job_id field={job.get('job_id')}")
                    else:
                        logger.warning(f"Archived job not found: {job_id}")
                        job = None
            except Exception as e:
                logger.error(f"Error fetching archived job: {e}")
                job = None

        if not job:
            logger.warning(f"No job found for job_id={job_id}")
            return {
                "job_running": False,
                "job_id": None,
                "status": None
            }

        # Determine if job is still running
        job_status = job.get('status', 'running')
        is_running = job_status == 'running'

        response_data = {
            "job_running": is_running,
            "job_id": job.get('job_id'),
            "status": job_status,
            "started_at": job.get('started_at'),
            "total": job.get('total', 0),
            "processed": job.get('processed', 0),
            "succeeded": job.get('succeeded', 0),
            "failed": job.get('failed', 0),
            "current_file": job.get('current_file', ''),
            "results": job.get('results', []),
            "errors": job.get('errors', []),
            "error_message": job.get('error_message')  # Fatal error if job failed
        }
        logger.info(f"Returning status for job {job.get('job_id')}: running={is_running}, status={job_status}")
        return response_data
    except Exception as e:
        logger.error(f"Error getting backup reapply status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def process_backup_reapply_job_sync(job_id: str, filenames: List[str]):
    """Background thread to process backup reapply job"""
    import time

    processed = 0
    succeeded = 0
    failed = 0

    for filename in filenames:
        try:
            # Update current file
            salary_jobs_service.update_backup_reapply_progress(
                job_id=job_id,
                processed=processed,
                succeeded=succeeded,
                failed=failed,
                current_file=filename
            )

            # Re-apply the backup
            success, result = salary_jobs_service.re_apply_from_backup(filename)

            processed += 1
            succeeded += 1

            # Update with success result
            salary_jobs_service.update_backup_reapply_progress(
                job_id=job_id,
                processed=processed,
                succeeded=succeeded,
                failed=failed,
                current_file=filename,
                result={
                    "filename": filename,
                    "district_id": result['district_id'],
                    "district_name": result['district_name'],
                    "records_added": result['records_added'],
                    "calculated_entries": result['calculated_entries']
                }
            )

            # Small delay to avoid rate limiting
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error processing backup {filename}: {e}")
            processed += 1
            failed += 1

            # Update with error
            salary_jobs_service.update_backup_reapply_progress(
                job_id=job_id,
                processed=processed,
                succeeded=succeeded,
                failed=failed,
                current_file=filename,
                error={
                    "filename": filename,
                    "error": str(e)
                }
            )

            # Small delay even on error
            time.sleep(0.5)

    # Mark job as complete
    salary_jobs_service.complete_backup_reapply_job(job_id)


# Lambda handler (only needed for AWS deployment)
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not installed - fine for local development
    pass