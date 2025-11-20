"""
Lambda function to process backup reapply jobs
Processes all backup files in the background
"""
import json
import os
import sys
import logging
import boto3
import time
from datetime import datetime

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from services.salary_jobs import SalaryJobsService

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get environment variables
TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
BUCKET_NAME = os.environ['S3_BUCKET_NAME']
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

# Initialize service (without SQS since we don't need it here)
salary_service = SalaryJobsService(
    dynamodb_table=table,
    s3_client=s3_client,
    sqs_client=None,
    queue_url='',
    bucket_name=BUCKET_NAME
)


def handler(event, context):
    """
    Lambda handler for backup reapply worker

    Event format:
    {
        "job_id": "backup-reapply-job-uuid",
        "filenames": ["District1.json", "District2.json", ...]
    }
    """
    logger.info(f"Starting backup reapply: {json.dumps(event)}")

    job_id = event.get('job_id')
    filenames = event.get('filenames', [])

    if not job_id or not filenames:
        logger.error("Missing job_id or filenames in event")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing job_id or filenames'})
        }

    processed = 0
    succeeded = 0
    failed = 0

    try:
        for filename in filenames:
            try:
                # Update progress - current file
                salary_service.update_backup_reapply_progress(
                    job_id=job_id,
                    processed=processed,
                    succeeded=succeeded,
                    failed=failed,
                    current_file=filename
                )

                # Re-apply the backup
                success, result = salary_service.re_apply_from_backup(filename)

                processed += 1
                succeeded += 1

                # Update progress with success
                salary_service.update_backup_reapply_progress(
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

                logger.info(f"Successfully processed {filename}")

                # Small delay to avoid rate limiting
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")
                processed += 1
                failed += 1

                # Update progress with error
                salary_service.update_backup_reapply_progress(
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
        salary_service.complete_backup_reapply_job(job_id)

        logger.info(f"Backup reapply complete: {succeeded} succeeded, {failed} failed")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'job_id': job_id,
                'processed': processed,
                'succeeded': succeeded,
                'failed': failed
            })
        }

    except Exception as e:
        logger.error(f"Fatal error in backup reapply: {e}")
        # Mark job as failed
        try:
            salary_service.fail_backup_reapply_job(job_id, str(e))
        except Exception as fail_error:
            logger.error(f"Error marking job as failed: {fail_error}")
            # Last resort - delete the running job
            try:
                salary_service.table.delete_item(
                    Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
                )
            except:
                pass

        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
