"""
Admin salary processing endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from typing import Optional, List
import os
import json
import logging
import boto3

from database import get_table
from cognito_auth import require_admin_role
from rate_limiter import limiter, GENERAL_RATE_LIMIT, WRITE_RATE_LIMIT
from services.salary_jobs import SalaryJobsService, LocalSalaryJobsService
from services.salary_service_optimized import invalidate_salary_cache
from validation import validate_district_id

# Configure logging
logger = logging.getLogger(__name__)

# Initialize AWS clients
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)
sqs_client = boto3.client('sqs', region_name=AWS_REGION)
lambda_client = boto3.client('lambda', region_name=AWS_REGION)

# Get environment variables
TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
SQS_QUEUE_URL = os.getenv('SALARY_PROCESSING_QUEUE_URL')
NORMALIZER_LAMBDA_ARN = os.getenv('SALARY_NORMALIZER_LAMBDA_ARN')

main_table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# Initialize salary jobs service
salary_jobs_service = None
if main_table and S3_BUCKET_NAME:
    # Allow running without SQS queue (manual apply & backups still work).
    if not SQS_QUEUE_URL:
        logger.warning("SALARY_PROCESSING_QUEUE_URL not set; PDF upload jobs disabled but manual apply will function.")
        SQS_QUEUE_URL = ""
    salary_jobs_service = SalaryJobsService(
        dynamodb_table=main_table,
        s3_client=s3_client,
        sqs_client=sqs_client,
        queue_url=SQS_QUEUE_URL,
        bucket_name=S3_BUCKET_NAME
    )
else:
    # Local development fallback
    local_storage = os.getenv("LOCAL_SALARY_STORAGE", "./backend/local_data")
    salary_jobs_service = LocalSalaryJobsService(storage_dir=local_storage, dynamodb_table=main_table)

router = APIRouter(prefix="/api/admin", tags=["salary-admin"])


@router.post("/districts/{district_id}/salary-schedule/upload")
@limiter.limit(WRITE_RATE_LIMIT)
async def upload_salary_schedule(
    request: Request,
    district_id: str,
    file: UploadFile = File(...),
    table = Depends(get_table),
    user: dict = Depends(require_admin_role)
):
    """Upload a PDF contract for processing"""
    # Validate district_id format
    district_id = validate_district_id(district_id)

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


@router.get("/districts/{district_id}/salary-schedule/jobs/{job_id}")
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


@router.put("/districts/{district_id}/salary-schedule/apply/{job_id}")
@limiter.limit(WRITE_RATE_LIMIT)
async def apply_salary_schedule(
    request: Request,
    district_id: str,
    job_id: str,
    user: dict = Depends(require_admin_role)
):
    """Apply extracted salary data to district"""
    # Validate inputs
    district_id = validate_district_id(district_id)

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

        # OPTIMIZATION: Invalidate salary cache for this district after applying new data
        invalidate_salary_cache(district_id)
        logger.info(f"Invalidated salary cache for district {district_id} after applying job {job_id}")

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


@router.post("/districts/{district_id}/salary-schedule/manual-apply")
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
    # Validate district_id
    district_id = validate_district_id(district_id)

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

        # OPTIMIZATION: Invalidate salary cache for this district after manual apply
        invalidate_salary_cache(district_id)
        logger.info(f"Invalidated salary cache for district {district_id} after manual apply")

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


@router.delete("/districts/{district_id}/salary-schedule/jobs/{job_id}")
@limiter.limit(WRITE_RATE_LIMIT)
async def reject_salary_schedule(
    request: Request,
    district_id: str,
    job_id: str,
    user: dict = Depends(require_admin_role)
):
    """Reject and delete a processing job"""
    # Validate district_id
    district_id = validate_district_id(district_id)

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


@router.get("/global/normalization/status")
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


@router.post("/global/normalize")
@limiter.limit(WRITE_RATE_LIMIT)
async def start_normalization(
    request: Request,
    user: dict = Depends(require_admin_role)
):
    """Start global normalization job

    Note: Cache is cleared when normalization starts. Frontend should avoid
    cached queries until normalization completes.
    """
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

        # OPTIMIZATION: Clear entire cache when normalization starts
        # Normalization updates calculated salaries across ALL districts
        invalidate_salary_cache()  # Clear all
        logger.info("Cleared entire salary cache due to global normalization start")

        return {
            "success": True,
            "job_id": job_id,
            "message": "Normalization job started, salary cache cleared"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start normalization: {str(e)}")


@router.get("/backup/list")
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


@router.post("/backup/reapply")
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


@router.post("/backup/reapply/start")
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
            from .helpers import process_backup_reapply_job_sync
            process_backup_reapply_job_sync(salary_jobs_service, job_id, filenames)

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


@router.get("/backup/reapply/status")
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


@router.get("/districts/missing-contracts")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_districts_without_contracts(
    request: Request,
    year: str = Query(..., description="School year in format YYYY-YYYY (e.g., 2025-2026)"),
    period: str = Query("Full Year", description="Contract period (e.g., 'Full Year')"),
    user: dict = Depends(require_admin_role),
    table = Depends(get_table)
):
    """
    Admin endpoint: Get a list of districts (Regional or Municipal only) that do NOT have
    contract data for the specified year and period.

    Query Parameters:
        year: School year (e.g., "2025-2026")
        period: Contract period (default: "Full Year")

    Returns:
        List of districts that are missing contracts for the given year/period
    """
    try:
        from services.dynamodb_district_service import DynamoDBDistrictService

        # Step 1: Get all districts using the search_districts method (which fetches all districts)
        all_districts, _ = DynamoDBDistrictService.search_districts(
            table=table,
            query_text=None,
            limit=10000,  # Large limit to get all districts
            offset=0
        )

        # Step 2: Filter to only Regional or Municipal districts
        regional_or_municipal = [
            d for d in all_districts
            if d.get('district_type', '').lower() in ['regional_academic', 'municipal']
        ]

        logger.info(f"Found {len(regional_or_municipal)} Regional/Municipal districts out of {len(all_districts)} total districts")

        # Step 3: Query METADATA#AVAILABILITY for the given year and period
        sk_value = f"YEAR#{year}#PERIOD#{period}"

        try:
            response = table.get_item(
                Key={
                    'PK': 'METADATA#AVAILABILITY',
                    'SK': sk_value
                }
            )

            availability_item = response.get('Item')

            if not availability_item:
                # No data for this year/period - all districts are missing contracts
                logger.info(f"No availability data found for {year} / {period}")
                return {
                    "year": year,
                    "period": period,
                    "total_districts": len(regional_or_municipal),
                    "missing_count": len(regional_or_municipal),
                    "districts": regional_or_municipal
                }

            # Step 4: Get the districts map from the availability item
            districts_with_data = availability_item.get('districts', {})
            district_ids_with_data = set(districts_with_data.keys())

            logger.info(f"Found {len(district_ids_with_data)} districts with data for {year} / {period}")

            # Step 5: Filter out districts that have data
            districts_without_contracts = [
                d for d in regional_or_municipal
                if d['id'] not in district_ids_with_data
            ]

            logger.info(f"Found {len(districts_without_contracts)} districts without contracts")

            return {
                "year": year,
                "period": period,
                "total_districts": len(regional_or_municipal),
                "missing_count": len(districts_without_contracts),
                "districts": districts_without_contracts
            }

        except Exception as e:
            logger.error(f"Error querying availability data: {e}")
            raise HTTPException(status_code=500, detail=f"Error querying availability data: {str(e)}")

    except Exception as e:
        logger.error(f"Error getting districts without contracts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
