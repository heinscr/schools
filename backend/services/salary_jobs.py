"""
Service layer for salary processing jobs
Handles PDF upload, job tracking, and data replacement
"""
import uuid
import time
import json
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import boto3
from boto3.dynamodb.conditions import Key
import logging
from utils.normalization import generate_calculated_entries, pad_number, pad_salary
from config import JOB_TTL_SECONDS

logger = logging.getLogger(__name__)


class SalaryJobsService:
    """Service for managing salary processing jobs"""

    def __init__(self, dynamodb_table, s3_client, sqs_client, queue_url: str, bucket_name: str):
        self.table = dynamodb_table
        self.s3 = s3_client
        self.sqs = sqs_client
        self.queue_url = queue_url
        self.bucket_name = bucket_name
        self.contracts_prefix = "contracts"

    def create_job(
        self,
        district_id: str,
        district_name: str,
        pdf_content: bytes,
        filename: str,
        uploaded_by: str
    ) -> Dict:
        """
        Create a new processing job and upload PDF to S3

        Args:
            district_id: District UUID
            district_name: District name
            pdf_content: PDF file content
            filename: Original filename
            uploaded_by: Cognito user sub

        Returns:
            Job metadata dict
        """
        job_id = str(uuid.uuid4())

        # Upload PDF to S3
        pdf_key = f"{self.contracts_prefix}/pdfs/{district_id}.pdf"
        logger.info(f"Uploading PDF to S3: {len(pdf_content)} bytes, type: {type(pdf_content)}")

        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=pdf_key,
            Body=pdf_content,
            ContentType='application/pdf',
            Metadata={
                'district_id': district_id,
                'job_id': job_id,
                'uploaded_by': uploaded_by
            }
        )

        logger.info(f"Successfully uploaded PDF to S3: {pdf_key}")

        # Create job record
        now = datetime.now(UTC).isoformat()
        ttl = int(time.time()) + JOB_TTL_SECONDS

        job = {
            'PK': f'JOB#{job_id}',
            'SK': 'METADATA',
            'job_id': job_id,
            'district_id': district_id,
            'district_name': district_name,
            'status': 'pending',
            's3_pdf_key': pdf_key,
            's3_json_key': f"{self.contracts_prefix}/json/{district_id}.json",
            'original_filename': filename,
            'uploaded_by': uploaded_by,
            'created_at': now,
            'updated_at': now,
            'ttl': ttl
        }

        self.table.put_item(Item=job)

        # Send message to SQS for processing
        self.sqs.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps({
                'job_id': job_id,
                'district_id': district_id,
                'district_name': district_name,
                's3_pdf_key': pdf_key,
                's3_json_key': job['s3_json_key']
            })
        )

        logger.info(f"Created job {job_id} for district {district_id}")
        return job

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        response = self.table.get_item(
            Key={'PK': f'JOB#{job_id}', 'SK': 'METADATA'}
        )
        return response.get('Item')

    def update_job_status(
        self,
        job_id: str,
        status: str,
        extracted_records_count: Optional[int] = None,
        years_found: Optional[List[str]] = None,
        error_message: Optional[str] = None
    ):
        """Update job status"""
        update_expr = "SET #status = :status, updated_at = :updated_at"
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {
            ':status': status,
            ':updated_at': datetime.now(UTC).isoformat()
        }

        if extracted_records_count is not None:
            update_expr += ", extracted_records_count = :count"
            expr_attr_values[':count'] = extracted_records_count

        if years_found is not None:
            update_expr += ", years_found = :years"
            expr_attr_values[':years'] = years_found

        if error_message is not None:
            update_expr += ", error_message = :error"
            expr_attr_values[':error'] = error_message

        self.table.update_item(
            Key={'PK': f'JOB#{job_id}', 'SK': 'METADATA'},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )

    def delete_job(self, job_id: str):
        """Delete job and associated S3 files"""
        job = self.get_job(job_id)
        if not job:
            return

        # Delete S3 files
        try:
            if 's3_pdf_key' in job:
                self.s3.delete_object(Bucket=self.bucket_name, Key=job['s3_pdf_key'])
            if 's3_json_key' in job:
                self.s3.delete_object(Bucket=self.bucket_name, Key=job['s3_json_key'])
        except Exception as e:
            logger.error(f"Error deleting S3 files for job {job_id}: {e}")

        # Delete job record
        self.table.delete_item(Key={'PK': f'JOB#{job_id}', 'SK': 'METADATA'})
        logger.info(f"Deleted job {job_id}")

    def get_extracted_data_preview(self, job_id: str, limit: Optional[int] = 10) -> Optional[List[Dict]]:
        """Get preview of extracted data from S3 JSON"""
        job = self.get_job(job_id)
        if not job or job['status'] != 'completed':
            return None

        try:
            response = self.s3.get_object(
                Bucket=self.bucket_name,
                Key=job['s3_json_key']
            )
            data = json.loads(response['Body'].read())
            return data[:limit] if limit else data
        except Exception as e:
            logger.error(f"Error reading extracted data for job {job_id}: {e}")
            return None

    def _get_edu_key(self, education: str, credits: int) -> str:
        """Get education column key (e.g., 'B', 'B+15', 'M+30')"""
        if credits > 0:
            return f"{education}+{credits}"
        return education

    def apply_salary_data(self, job_id: str, district_id: str, exclusions: Optional[Dict] = None) -> Tuple[bool, Dict]:
        """
        Apply salary data from job to district

        Args:
            job_id: Job ID
            district_id: District ID
            exclusions: Optional dict with 'excluded_steps' and 'excluded_columns' lists

        Returns:
            (success, metadata_info)
            metadata_info contains:
                - records_added
                - metadata_changed (bool)
                - needs_global_normalization (bool)
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError("Job not found")

        if job['status'] != 'completed':
            raise ValueError("Job is not completed")

        if job['district_id'] != district_id:
            raise ValueError("Job district_id does not match")

        # Load extracted data from S3
        try:
            response = self.s3.get_object(
                Bucket=self.bucket_name,
                Key=job['s3_json_key']
            )
            records = json.loads(response['Body'].read())
        except Exception as e:
            logger.error(f"Error loading extracted data: {e}")
            raise

        # Apply exclusions if provided
        if exclusions:
            excluded_steps = set(exclusions.get('excluded_steps', []))
            excluded_columns = set(exclusions.get('excluded_columns', []))

            original_count = len(records)
            records = [
                r for r in records
                if r['step'] not in excluded_steps
                and self._get_edu_key(r['education'], r['credits']) not in excluded_columns
            ]
            logger.info(f"Applied exclusions: {original_count} -> {len(records)} records (excluded {original_count - len(records)})")

        # Run common apply pipeline
        return self._apply_records_pipeline(district_id=district_id, records=records, normalization_trigger_id=job_id)

    def apply_salary_records(self, district_id: str, records: List[Dict]) -> Tuple[bool, Dict]:
        """
        Apply salary data directly from provided records (no job/exclusions).

        Args:
            district_id: District ID to apply records to
            records: List of salary records in extractor format

        Returns:
            (success, metadata_info) same as apply_salary_data
        """
        return self._apply_records_pipeline(district_id=district_id, records=records, normalization_trigger_id="manual-apply")

    def _apply_records_pipeline(self, district_id: str, records: List[Dict], normalization_trigger_id: Optional[str]) -> Tuple[bool, Dict]:
        """
        Common pipeline to apply a list of records to a district.
        Performs: metadata check, delete old, load new, update metadata, normalize, backup.
        """
        # Ensure each record includes district identifiers for downstream writes and backup
        district_name = self._get_district_name(district_id)
        for r in records:
            r.setdefault('district_id', district_id)
            r.setdefault('district_name', district_name)

        # Check if metadata will change
        metadata_changed, needs_normalization = self._check_metadata_change(records)

        # Delete existing salary data for this district
        self._delete_district_salary_data(district_id)

        # Load new salary data
        records_added = self._load_salary_records(district_id, records)

        # Update schedules metadata for year/period combinations
        self._update_schedules_metadata(records)

        # Update availability metadata for year/period combinations
        self._update_availability_metadata(district_id, records)

        # Normalize this specific district immediately
        normalized_count = self._normalize_district(district_id, records)
        logger.info(f"Normalized district {district_id}: {normalized_count} calculated entries created")

        # Update metadata if changed
        if metadata_changed:
            self._update_global_metadata(records)

            # Set normalization flag (for other districts that might need it)
            self._set_normalization_status(needs_normalization, normalization_trigger_id or "manual-apply")

        logger.info(f"Applied salary data for district {district_id}: {records_added} records, {normalized_count} calculated")

        # Save backup to S3
        try:
            self._save_applied_backup(district_id, records)
        except Exception as e:
            logger.error(f"Error saving backup for district {district_id}: {e}")
            # Don't fail the apply operation if backup fails

        return True, {
            'records_added': records_added,
            'calculated_entries': normalized_count,
            'metadata_changed': metadata_changed,
            'needs_global_normalization': needs_normalization
        }

    def _check_metadata_change(self, records: List[Dict]) -> Tuple[bool, bool]:
        """
        Check if new records would change global metadata

        Returns:
            (metadata_changed, needs_normalization)
        """
        # Get current metadata
        response = self.table.get_item(
            Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'}
        )

        if 'Item' not in response:
            # No metadata yet, this is first data
            return True, False

        current_meta = response['Item']
        current_max_step = int(current_meta.get('max_step', 0))
        current_combos = set(current_meta.get('edu_credit_combos', []))

        # Calculate new values
        new_max_step = max(int(r['step']) for r in records)
        new_combos = set(f"{r['education']}+{r['credits']}" for r in records)

        # Check if changed
        max_step_increased = new_max_step > current_max_step
        new_combos_added = not new_combos.issubset(current_combos)

        metadata_changed = max_step_increased or new_combos_added
        needs_normalization = metadata_changed  # If metadata changed, need to normalize

        return metadata_changed, needs_normalization

    def _delete_district_salary_data(self, district_id: str):
        """Delete all salary schedule records for a district"""
        # Query all salary records for this district
        response = self.table.query(
            KeyConditionExpression=Key('PK').eq(f'DISTRICT#{district_id}') &
                                 Key('SK').begins_with('SCHEDULE#')
        )

        items = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = self.table.query(
                KeyConditionExpression=Key('PK').eq(f'DISTRICT#{district_id}') &
                                     Key('SK').begins_with('SCHEDULE#'),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        # Delete in batches
        if items:
            with self.table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

            logger.info(f"Deleted {len(items)} salary records for district {district_id}")

    def _load_salary_records(self, district_id: str, records: List[Dict]) -> int:
        """Load salary records into DynamoDB"""
        items = []
        for record in records:
            school_year = record['school_year']
            period = record['period']
            education = record['education']
            credits = int(record['credits'])
            step = int(record['step'])
            salary = Decimal(str(record['salary']))
            district_name = record['district_name']

            # Pad numbers for proper sorting
            credits_padded = pad_number(credits, 3)
            step_padded = pad_number(step, 2)
            salary_padded = pad_salary(salary)

            item = {
                'PK': f'DISTRICT#{district_id}',
                'SK': f'SCHEDULE#{school_year}#{period}#EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',
                'district_id': district_id,
                'district_name': district_name,
                'school_year': school_year,
                'period': period,
                'education': education,
                'credits': credits,
                'step': step,
                'salary': salary,
                'GSI1PK': f'YEAR#{school_year}#PERIOD#{period}#EDU#{education}#CR#{credits_padded}',
                'GSI1SK': f'STEP#{step_padded}#DISTRICT#{district_id}',
                'GSI2PK': f'YEAR#{school_year}#PERIOD#{period}#DISTRICT#{district_id}',
                'GSI2SK': f'EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',
                'GSI_COMP_PK': f'EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',
                'GSI_COMP_SK': f'SALARY#{salary_padded}#YEAR#{school_year}#DISTRICT#{district_id}',
            }
            items.append(item)

        # Write in batches
        with self.table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

        return len(items)

    def _update_global_metadata(self, records: List[Dict]):
        """Update global metadata with new max values"""
        # Get current metadata
        response = self.table.get_item(
            Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'}
        )

        current_max_step = 0
        current_combos = set()

        if 'Item' in response:
            current_meta = response['Item']
            current_max_step = int(current_meta.get('max_step', 0))
            current_combos = set(current_meta.get('edu_credit_combos', []))

        # Calculate new values
        new_max_step = max(int(r['step']) for r in records)
        new_combos = set(f"{r['education']}+{r['credits']}" for r in records)

        # Merge with existing
        final_max_step = max(current_max_step, new_max_step)
        final_combos = current_combos.union(new_combos)

        # Update metadata
        self.table.put_item(Item={
            'PK': 'METADATA#MAXVALUES',
            'SK': 'GLOBAL',
            'max_step': final_max_step,
            'edu_credit_combos': sorted(list(final_combos)),
            'last_updated': datetime.now(UTC).isoformat()
        })

    def list_backups(self) -> List[Dict]:
        """
        List all backup files in S3
        Returns list of backup metadata
        """
        backups = []
        prefix = f"{self.contracts_prefix}/applied_data/"

        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            if 'Contents' in response:
                for obj in response['Contents']:
                    # Extract district name from filename
                    key = obj['Key']
                    filename = key.split('/')[-1]
                    if filename.endswith('.json'):
                        district_name = filename[:-5]  # Remove .json extension

                        backups.append({
                            'filename': filename,
                            'district_name': district_name,
                            'key': key,
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat()
                        })

            logger.info(f"Found {len(backups)} backup files")
            return backups

        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            raise

    def re_apply_from_backup(self, backup_filename: str) -> Tuple[bool, Dict]:
        """
        Re-apply salary data from a backup file

        Args:
            backup_filename: Filename of the backup (e.g., "Springfield.json")

        Returns:
            (success, result_info)
        """
        # Load backup from S3
        backup_key = f"{self.contracts_prefix}/applied_data/{backup_filename}"

        try:
            response = self.s3.get_object(
                Bucket=self.bucket_name,
                Key=backup_key
            )
            backup_data = json.loads(response['Body'].read())
        except Exception as e:
            logger.error(f"Error loading backup {backup_filename}: {e}")
            raise ValueError(f"Backup file not found: {backup_filename}")

        # Extract data
        district_name = backup_data.get('district_name')
        records = backup_data.get('records', [])

        if not district_name or not records:
            raise ValueError(f"Invalid backup file: missing district_name or records")

        district_id = self._get_district_id_by_name(district_name)
        
        if district_id: 
            logger.info(f"Re-applying backup for {district_name} ({district_id}): {len(records)} records")
        else:
            raise ValueError(f"District not found: {district_name}")
        
        # Check if metadata will change
        metadata_changed, needs_normalization = self._check_metadata_change(records)

        # Delete existing salary data for this district
        self._delete_district_salary_data(district_id)

        # Load salary data
        records_added = self._load_salary_records(district_id, records)

        # Update schedules metadata
        self._update_schedules_metadata(records)

        # Update availability metadata
        self._update_availability_metadata(district_id, records)

        # Normalize this specific district
        normalized_count = self._normalize_district(district_id, records)

        # Update metadata if changed
        if metadata_changed:
            self._update_global_metadata(records)
            self._set_normalization_status(needs_normalization, f"backup-reapply-{backup_filename}")

        logger.info(f"Re-applied backup for {district_name}: {records_added} records, {normalized_count} calculated")

        return True, {
            'district_id': district_id,
            'district_name': district_name,
            'records_added': records_added,
            'calculated_entries': normalized_count,
            'metadata_changed': metadata_changed
        }

    def _get_district_id_by_name(self, district_name: str) -> Optional[str]:
        """
        Look up district_id by district name using GSI_METADATA index
        Queries on SK='METADATA' and name_lower for efficient lookup
        """
        try:
            # Query GSI_METADATA using SK (hash key) and name_lower (range key)
            response = self.table.query(
                IndexName='GSI_METADATA',
                KeyConditionExpression=Key('SK').eq('METADATA') & Key('name_lower').eq(district_name.lower())
            )

            items = response.get('Items', [])
            if items:
                district_id = items[0].get('district_id')
                if district_id:
                    logger.info(f"Found district_id {district_id} for name {district_name}")
                    return district_id

        except Exception as e:
            logger.error(f"Error looking up district by name: {e}")

        return None

    def _get_district_name(self, district_id: str) -> str:
        """Get district name from DynamoDB"""
        try:
            response = self.table.get_item(
                Key={'PK': f'DISTRICT#{district_id}', 'SK': 'METADATA'}
            )
            if 'Item' in response:
                return response['Item'].get('name', district_id)
        except Exception as e:
            logger.error(f"Error getting district name: {e}")
        return district_id

    def _save_applied_backup(self, district_id: str, records: List[Dict]):
        """
        Save a backup of applied salary data to S3
        Filename format: contracts/applied_data/<district_name>.json
        """
        from datetime import timezone

        # Get district name
        district_name = self._get_district_name(district_id)

        # Create backup object
        now_utc = datetime.now(timezone.utc).isoformat()
        backup_data = {
            'district_id': district_id,
            'district_name': district_name,
            'applied_at': now_utc,
            'records_count': len(records),
            'records': records
        }

        # Save to S3
        backup_key = f"{self.contracts_prefix}/applied_data/{district_name}.json"
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=backup_key,
            Body=json.dumps(backup_data, indent=2, default=str),
            ContentType='application/json',
            Metadata={
                'district_id': district_id,
                'district_name': district_name,
                'applied_at': now_utc
            }
        )

        logger.info(f"Saved backup to S3: {backup_key} ({len(records)} records)")

    def _update_availability_metadata(self, district_id: str, records: List[Dict]):
        """Update availability metadata to include this district for each year/period"""
        # Group records by year/period
        year_periods = {}
        for record in records:
            year = record['school_year']
            period = record['period']
            key = (year, period)

            if key not in year_periods:
                year_periods[key] = set()

            # Track edu+credit combo
            edu_credit = f"{record['education']}+{record['credits']}"
            year_periods[key].add(edu_credit)

        # Update availability metadata for each year/period
        for (year, period), edu_credits in year_periods.items():
            pk = 'METADATA#AVAILABILITY'
            sk = f'YEAR#{year}#PERIOD#{period}'

            # Get existing availability metadata
            response = self.table.get_item(Key={'PK': pk, 'SK': sk})

            if 'Item' in response:
                # Update existing item
                item = response['Item']
                districts = item.get('districts', {})

                # Add this district with its edu+credit combos
                districts[district_id] = {combo: True for combo in edu_credits}

                item['districts'] = districts
                item['last_updated'] = datetime.now(UTC).isoformat()
            else:
                # Create new availability metadata
                item = {
                    'PK': pk,
                    'SK': sk,
                    'school_year': year,
                    'period': period,
                    'districts': {
                        district_id: {combo: True for combo in edu_credits}
                    },
                    'created_at': datetime.now(UTC).isoformat()
                }

            # Save updated metadata
            self.table.put_item(Item=item)
            logger.info(f"Updated availability metadata for {year}/{period} to include district {district_id}")

    def _update_schedules_metadata(self, records: List[Dict]):
        """
        Update METADATA#SCHEDULES to track year/period combinations
        This is used by salary_service.py and normalization scripts to find available schedules
        """
        # Collect unique year/period combinations
        year_periods = set()
        for record in records:
            year = record['school_year']
            period = record['period']
            year_periods.add((year, period))

        # Create or update METADATA#SCHEDULES items
        for year, period in year_periods:
            pk = 'METADATA#SCHEDULES'
            sk = f'YEAR#{year}#PERIOD#{period}'

            # Check if this schedule metadata already exists
            response = self.table.get_item(Key={'PK': pk, 'SK': sk})

            if 'Item' not in response:
                # Create new schedule metadata item
                item = {
                    'PK': pk,
                    'SK': sk,
                    'school_year': year,
                    'period': period,
                    'created_at': datetime.now(UTC).isoformat()
                }
                self.table.put_item(Item=item)
                logger.info(f"Created schedule metadata for {year}/{period}")

    def _normalize_district(self, district_id: str, records: List[Dict]) -> int:
        """
        Normalize salary data for a specific district

        Args:
            district_id: District UUID
            records: List of salary records that were just loaded

        Returns:
            Number of calculated entries created
        """
        from collections import defaultdict

        # Get global metadata for normalization
        response = self.table.get_item(
            Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'}
        )

        if 'Item' not in response:
            logger.warning(f"No global metadata found, skipping normalization for {district_id}")
            return 0

        metadata = response['Item']
        max_step = int(metadata.get('max_step', 15))
        edu_credit_combos = metadata.get('edu_credit_combos', [])

        # Get district name from first record
        district_name = records[0]['district_name'] if records else district_id

        # Group records by year/period
        by_year_period = defaultdict(list)
        for record in records:
            key = (record['school_year'], record['period'])
            by_year_period[key].append(record)

        total_calculated = 0

        # Use shared normalization utility
        edu_order = {'B': 1, 'M': 2, 'D': 3}

        for (year, period), year_records in by_year_period.items():
            calculated_items = generate_calculated_entries(
                district_id, district_name, year, period,
                year_records, max_step, edu_credit_combos, edu_order
            )

            # Write calculated entries in batches
            if calculated_items:
                with self.table.batch_writer() as batch:
                    for item in calculated_items:
                        batch.put_item(Item=item)

                total_calculated += len(calculated_items)
                logger.info(f"Created {len(calculated_items)} calculated entries for {district_id} {year}/{period}")

        return total_calculated

    def _set_normalization_status(self, needs_normalization: bool, triggered_by_job_id: str):
        """Set global normalization status"""
        from datetime import timezone
        self.table.put_item(Item={
            'PK': 'METADATA#NORMALIZATION',
            'SK': 'STATUS',
            'needs_normalization': needs_normalization,
            'triggered_by_job_id': triggered_by_job_id,
            'last_checked': datetime.now(timezone.utc).isoformat()
        })

    def get_normalization_status(self) -> Dict:
        """Get current normalization status from the table"""
        try:
            response = self.table.get_item(
                Key={'PK': 'METADATA#NORMALIZATION', 'SK': 'STATUS'}
            )
        except Exception as e:
            logger.error(f"Error fetching normalization status: {e}")
            return {
                'needs_normalization': False,
                'last_normalized_at': None
            }

        if 'Item' not in response:
            return {
                'needs_normalization': False,
                'last_normalized_at': None
            }

        return response['Item']

    def get_normalization_job(self) -> Optional[Dict]:
        """Get current running normalization job"""
        try:
            response = self.table.get_item(
                Key={'PK': 'NORMALIZATION_JOB#RUNNING', 'SK': 'METADATA'}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error fetching normalization job: {e}")
            return None


    def start_normalization_job(self, lambda_client, normalizer_arn: str, triggered_by: str) -> str:
        """
        Start a global normalization job

        Returns:
            job_id of the normalization job
        """
        # Check if already running
        response = self.table.get_item(
            Key={'PK': 'NORMALIZATION_JOB#RUNNING', 'SK': 'METADATA'}
        )

        if 'Item' in response:
            raise ValueError("Normalization job already running")

        job_id = str(uuid.uuid4())

        # Create normalization job record
        ttl = int(time.time()) + JOB_TTL_SECONDS

        job = {
            'PK': 'NORMALIZATION_JOB#RUNNING',
            'SK': 'METADATA',
            'job_id': job_id,
            'status': 'running',
            'started_at': datetime.now(UTC).isoformat(),
            'triggered_by': triggered_by,
            'ttl': ttl
        }

        self.table.put_item(Item=job)

        # Invoke normalizer Lambda asynchronously
        lambda_client.invoke(
            FunctionName=normalizer_arn,
            InvocationType='Event',  # Async invocation
            Payload=json.dumps({'job_id': job_id})
        )

        logger.info(f"Started normalization job {job_id}")
        return job_id

    def start_backup_reapply_job(self, filenames: List[str], triggered_by: str) -> str:
        """
        Start a backup reapply job

        Args:
            filenames: List of backup filenames to re-apply
            triggered_by: Cognito user sub

        Returns:
            job_id of the backup reapply job
        """
        # Check if already running
        response = self.table.get_item(
            Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
        )

        if 'Item' in response:
            raise ValueError("Backup reapply job already running")

        job_id = str(uuid.uuid4())

        # Create backup reapply job record
        ttl = int(time.time()) + (7 * 24 * 60 * 60)  # 7 days

        job = {
            'PK': 'BACKUP_REAPPLY_JOB#RUNNING',
            'SK': 'METADATA',
            'job_id': job_id,
            'status': 'running',
            'started_at': datetime.now(UTC).isoformat(),
            'triggered_by': triggered_by,
            'filenames': filenames,
            'total': len(filenames),
            'processed': 0,
            'succeeded': 0,
            'failed': 0,
            'current_file': '',
            'results': [],
            'errors': [],
            'ttl': ttl
        }

        self.table.put_item(Item=job)

        logger.info(f"Started backup reapply job {job_id} with {len(filenames)} files")
        return job_id

    def get_backup_reapply_job(self) -> Optional[Dict]:
        """Get current running backup reapply job"""
        try:
            response = self.table.get_item(
                Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error fetching backup reapply job: {e}")
            return None

    def update_backup_reapply_progress(
        self,
        job_id: str,
        processed: int,
        succeeded: int,
        failed: int,
        current_file: str,
        result: Optional[Dict] = None,
        error: Optional[Dict] = None
    ) -> None:
        """Update progress of backup reapply job"""
        try:
            # Use ExpressionAttributeNames for reserved keywords
            update_expr = "SET #proc = :proc, #succ = :succ, #fail = :fail, current_file = :curr, updated_at = :updated"
            expr_values = {
                ':proc': processed,
                ':succ': succeeded,
                ':fail': failed,
                ':curr': current_file,
                ':updated': datetime.now(UTC).isoformat()
            }
            expr_names = {
                '#proc': 'processed',
                '#succ': 'succeeded',
                '#fail': 'failed'
            }

            # Add result or error to lists
            if result:
                update_expr += ", results = list_append(if_not_exists(results, :empty_list), :result)"
                expr_values[':result'] = [result]
                if ':empty_list' not in expr_values:
                    expr_values[':empty_list'] = []

            if error:
                update_expr += ", errors = list_append(if_not_exists(errors, :empty_list2), :error)"
                expr_values[':error'] = [error]
                expr_values[':empty_list2'] = []

            expr_values[':jid'] = job_id

            self.table.update_item(
                Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ConditionExpression='attribute_exists(PK) AND job_id = :jid'
            )
        except Exception as e:
            logger.error(f"Error updating backup reapply progress: {e}")

    def complete_backup_reapply_job(self, job_id: str) -> None:
        """Mark backup reapply job as complete and remove from RUNNING"""
        try:
            logger.info(f"Completing backup reapply job: {job_id}")
            # Get the job
            response = self.table.get_item(
                Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
            )

            if 'Item' not in response or response['Item'].get('job_id') != job_id:
                logger.warning(f"Job {job_id} not found or mismatch when completing")
                return

            job = response['Item']
            job['status'] = 'completed'
            job['completed_at'] = datetime.now(UTC).isoformat()

            # Archive the completed job
            archive_pk = f'BACKUP_REAPPLY_JOB#{job_id}'
            job['PK'] = archive_pk
            logger.info(f"Archiving job {job_id} to PK={archive_pk}, SK={job.get('SK')}")
            logger.info(f"Job has job_id field: {job.get('job_id')}")
            self.table.put_item(Item=job)
            logger.info(f"Job {job_id} archived successfully")

            # Delete from RUNNING
            self.table.delete_item(
                Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
            )
            logger.info(f"Job {job_id} removed from RUNNING")

        except Exception as e:
            logger.error(f"Error completing backup reapply job: {e}")

    def fail_backup_reapply_job(self, job_id: str, error_message: str) -> None:
        """Mark backup reapply job as failed and remove from RUNNING"""
        try:
            # Get the job
            response = self.table.get_item(
                Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
            )

            if 'Item' not in response or response['Item'].get('job_id') != job_id:
                logger.warning(f"Job {job_id} not found or mismatch when failing")
                return

            job = response['Item']
            job['status'] = 'failed'
            job['error_message'] = error_message
            job['failed_at'] = datetime.now(UTC).isoformat()

            # Archive the failed job
            job['PK'] = f'BACKUP_REAPPLY_JOB#{job_id}'
            self.table.put_item(Item=job)

            # Delete from RUNNING
            self.table.delete_item(
                Key={'PK': 'BACKUP_REAPPLY_JOB#RUNNING', 'SK': 'METADATA'}
            )

            logger.info(f"Completed backup reapply job {job_id}")
        except Exception as e:
            logger.error(f"Error completing backup reapply job: {e}")


class LocalSalaryJobsService:
    """A lightweight, file-backed stub of SalaryJobsService for local development.

    - Stores uploaded PDFs and generated JSON under a local directory.
    - Creates a completed job immediately with a small sample extracted JSON so admin flows can be exercised
      without AWS resources (S3/SQS).
    """

    def __init__(self, storage_dir: Optional[str] = None, dynamodb_table=None):
        """Initialize local storage paths.

        By default the storage directory is set to <repo-root>/backend/local_data so files are
        written to a deterministic location regardless of the current working directory.

        If a storage_dir is provided and it's an absolute path, it will be used as-is. If it's
        a relative path, it will be resolved relative to the repository backend directory.
        """
        from pathlib import Path

        # Determine repository backend directory (two levels up from this file -> backend)
        repo_backend_dir = Path(__file__).resolve().parent.parent

        if storage_dir:
            p = Path(storage_dir)
            if not p.is_absolute():
                # Resolve relative paths against the backend directory
                p = (repo_backend_dir / p).resolve()
            self.storage_dir = p
        else:
            # Default deterministic location: <repo-root>/backend/local_data
            self.storage_dir = (repo_backend_dir / "local_data").resolve()

        self.contracts_dir = self.storage_dir / "contracts"
        self.pdfs_dir = self.contracts_dir / "pdfs"
        self.json_dir = self.contracts_dir / "json"
        self.jobs_file = self.storage_dir / "jobs.json"
        self.table = dynamodb_table

        # Ensure directories exist
        self.pdfs_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if not self.jobs_file.exists():
            self._write_jobs({})

    def _read_jobs(self) -> Dict[str, Dict]:
        try:
            with open(self.jobs_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_jobs(self, data: Dict[str, Dict]):
        with open(self.jobs_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def create_job(self, district_id: str, district_name: str, pdf_content: bytes, filename: str, uploaded_by: str) -> Dict:
        job_id = str(uuid.uuid4())
        pdf_path = self.pdfs_dir / f"{district_id}.pdf"
        json_path = self.json_dir / f"{district_id}.json"

        # Save PDF locally
        with open(pdf_path, "wb") as f:
            f.write(pdf_content)

        # Create a small sample extracted JSON so the admin preview flows work
        sample_records = [
            {
                'district_id': district_id,
                'district_name': district_name,
                'school_year': '2024-2025',
                'period': 'regular',
                'education': 'B',
                'credits': 0,
                'step': 1,
                'salary': 50000.0
            },
            {
                'district_id': district_id,
                'district_name': district_name,
                'school_year': '2024-2025',
                'period': 'regular',
                'education': 'B',
                'credits': 0,
                'step': 2,
                'salary': 52000.0
            }
        ]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sample_records, f)

        now = datetime.now(UTC).isoformat()
        ttl = int(time.time()) + JOB_TTL_SECONDS

        job = {
            'PK': f'JOB#{job_id}',
            'SK': 'METADATA',
            'job_id': job_id,
            'district_id': district_id,
            'district_name': district_name,
            'status': 'completed',
            's3_pdf_key': str(pdf_path),
            's3_json_key': str(json_path),
            'original_filename': filename,
            'uploaded_by': uploaded_by,
            'created_at': now,
            'updated_at': now,
            'ttl': ttl,
            'extracted_records_count': len(sample_records),
            'years_found': ['2024-2025']
        }

        jobs = self._read_jobs()
        jobs[job_id] = job
        self._write_jobs(jobs)

        logger.info(f"[LocalSalaryJobsService] Created local job {job_id} (district {district_id}) at {pdf_path}")
        return job

    def get_job(self, job_id: str) -> Optional[Dict]:
        jobs = self._read_jobs()
        return jobs.get(job_id)

    def delete_job(self, job_id: str):
        jobs = self._read_jobs()
        job = jobs.pop(job_id, None)
        if job:
            # Attempt to remove local files if present
            try:
                from pathlib import Path
                pdf_key = job.get('s3_pdf_key')
                json_key = job.get('s3_json_key')
                if pdf_key:
                    p = Path(pdf_key)
                    if p.exists():
                        p.unlink()
                if json_key:
                    j = Path(json_key)
                    if j.exists():
                        j.unlink()
            except Exception:
                pass
            self._write_jobs(jobs)

    def get_extracted_data_preview(self, job_id: str, limit: Optional[int] = 10) -> Optional[List[Dict]]:
        job = self.get_job(job_id)
        if not job or job.get('status') != 'completed':
            return None

        try:
            with open(job['s3_json_key'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data[:limit] if limit else data
        except Exception as e:
            logger.error(f"[LocalSalaryJobsService] Error reading local extracted data: {e}")
            return None

    def apply_salary_data(self, job_id: str, district_id: str, exclusions: Optional[Dict] = None) -> Tuple[bool, Dict]:
        # For local stub, pretend we applied the data and return counts based on saved JSON
        job = self.get_job(job_id)
        if not job:
            raise ValueError("Job not found")
        try:
            with open(job['s3_json_key'], 'r', encoding='utf-8') as f:
                records = json.load(f)
        except Exception as e:
            raise

        # Simple metadata result
        records_added = len(records)
        metadata_changed = True
        needs_normalization = False

        # Update job status
        jobs = self._read_jobs()
        job['status'] = 'completed'
        job['extracted_records_count'] = records_added
        jobs[job_id] = job
        self._write_jobs(jobs)

        logger.info(f"[LocalSalaryJobsService] Applied {records_added} local records for district {district_id}")
        return True, {
            'records_added': records_added,
            'metadata_changed': metadata_changed,
            'needs_global_normalization': needs_normalization
        }

    def list_backups(self) -> List[Dict]:
        """
        List all backup files in local storage
        Returns list of backup metadata
        """
        from pathlib import Path

        backups = []
        applied_data_dir = self.contracts_dir / "applied_data"

        # Create directory if it doesn't exist
        applied_data_dir.mkdir(parents=True, exist_ok=True)

        # List all JSON files in the applied_data directory
        for backup_file in applied_data_dir.glob("*.json"):
            try:
                # Get file stats
                stat = backup_file.stat()

                # Extract district name from filename
                district_name = backup_file.stem  # Remove .json extension

                backups.append({
                    'filename': backup_file.name,
                    'district_name': district_name,
                    'key': str(backup_file),
                    'size': stat.st_size,
                    'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            except Exception as e:
                logger.error(f"Error reading backup file {backup_file}: {e}")

        logger.info(f"[LocalSalaryJobsService] Found {len(backups)} backup files")
        return backups

    def re_apply_from_backup(self, backup_filename: str) -> Tuple[bool, Dict]:
        """
        Re-apply salary data from a backup file

        Args:
            backup_filename: Filename of the backup (e.g., "Springfield.json")

        Returns:
            (success, result_info)
        """
        from pathlib import Path

        # Load backup from local storage
        backup_path = self.contracts_dir / "applied_data" / backup_filename

        if not backup_path.exists():
            raise ValueError(f"Backup file not found: {backup_filename}")

        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading backup {backup_filename}: {e}")
            raise ValueError(f"Failed to read backup file: {backup_filename}")

        # Extract data
        district_id = backup_data.get('district_id')
        district_name = backup_data.get('district_name')
        records = backup_data.get('records', [])

        if not district_id or not records:
            raise ValueError(f"Invalid backup file: missing district_id or records")

        logger.info(f"[LocalSalaryJobsService] Re-applying backup for {district_name} ({district_id}): {len(records)} records")

        # For local stub, just return success with counts
        return True, {
            'district_id': district_id,
            'district_name': district_name,
            'records_added': len(records),
            'calculated_entries': 0,
            'metadata_changed': False
        }

    # Optional helper used by normalization endpoints
    def start_normalization_job(self, lambda_client=None, normalizer_arn: Optional[str] = None, triggered_by: Optional[str] = None) -> str:
        # No-op for local; return a deterministic job id
        jid = f"local-normalize-{int(time.time())}"
        logger.info(f"[LocalSalaryJobsService] start_normalization_job -> {jid}")
        return jid

    # Minimal implementations to satisfy admin endpoints in main.py
    def get_normalization_status(self) -> Dict:
        # Return a simple status object
        return {
            'job_running': False,
            'last_run': None
        }

    def get_normalization_job(self) -> Optional[Dict]:
        # No background job in local stub
        return None

    def apply_salary_records(self, district_id: str, records: List[Dict]) -> Tuple[bool, Dict]:
        """Apply manual salary records in local development.

        This does NOT persist to DynamoDB (not available locally by default). It simply
        validates records and returns a success payload so the frontend flow mirrors
        production behavior.
        """
        if not isinstance(records, list) or len(records) == 0:
            raise ValueError("'records' must be a non-empty list")

        valid = 0
        for r in records:
            if not isinstance(r, dict):
                continue
            try:
                amt = float(r.get('salary', 0))
            except Exception:
                continue
            if amt <= 0:
                continue
            required = ['school_year', 'period', 'education', 'credits', 'step']
            if all(k in r for k in required):
                valid += 1

        if valid == 0:
            raise ValueError("No valid records to apply")

        logger.info(f"[LocalSalaryJobsService] apply_salary_records received {len(records)} records, {valid} valid for district {district_id}")
        return True, {
            'records_added': valid,
            'metadata_changed': True,
            'needs_global_normalization': False
        }