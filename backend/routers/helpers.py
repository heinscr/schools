"""
Helper functions for routers
"""
import logging
import time
from typing import List

logger = logging.getLogger(__name__)


def process_backup_reapply_job_sync(salary_jobs_service, job_id: str, filenames: List[str]):
    """Background thread to process backup reapply job"""
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
