"""
Helper functions for routers
"""
import logging
import time
from typing import List, Any

from config import BACKUP_PROCESSING_DELAY

logger = logging.getLogger(__name__)


def process_backup_reapply_job_sync(salary_jobs_service: Any, job_id: str, filenames: List[str]) -> None:
    """
    Background thread to process backup reapply job

    Iterates through a list of backup filenames, re-applying each one to DynamoDB.
    Updates job progress after each file (success or failure) and implements
    rate limiting delays between files.

    Args:
        salary_jobs_service: SalaryJobsService instance for database operations
        job_id: Unique identifier for this batch reapply job
        filenames: List of S3 backup file keys to process

    Side Effects:
        - Updates job progress in DynamoDB after each file
        - Logs errors for failed files
        - Marks job as complete when all files are processed
        - Sleeps 0.5s between files to avoid rate limiting
    """
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
            time.sleep(BACKUP_PROCESSING_DELAY)

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
            time.sleep(BACKUP_PROCESSING_DELAY)

    # Mark job as complete
    salary_jobs_service.complete_backup_reapply_job(job_id)
