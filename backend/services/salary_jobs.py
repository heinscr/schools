"""
Service layer for salary processing jobs
Handles PDF upload, job tracking, and data replacement
"""
import uuid
import time
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import boto3
from boto3.dynamodb.conditions import Key
import logging

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
        now = datetime.utcnow().isoformat()
        ttl = int(time.time()) + (30 * 24 * 60 * 60)  # 30 days

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
            ':updated_at': datetime.utcnow().isoformat()
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

    def get_extracted_data_preview(self, job_id: str, limit: int = 10) -> Optional[List[Dict]]:
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
            return data[:limit]
        except Exception as e:
            logger.error(f"Error reading extracted data for job {job_id}: {e}")
            return None

    def apply_salary_data(self, job_id: str, district_id: str) -> Tuple[bool, Dict]:
        """
        Apply salary data from job to district

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

        # Check if metadata will change
        metadata_changed, needs_normalization = self._check_metadata_change(records)

        # Delete existing salary data for this district
        self._delete_district_salary_data(district_id)

        # Load new salary data
        records_added = self._load_salary_records(district_id, records)

        # Update metadata if changed
        if metadata_changed:
            self._update_global_metadata(records)

            # Set normalization flag
            self._set_normalization_status(needs_normalization, job_id)

        logger.info(f"Applied salary data for district {district_id}: {records_added} records")

        return True, {
            'records_added': records_added,
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
            'last_updated': datetime.utcnow().isoformat()
        })

        logger.info(f"Updated global metadata: max_step={final_max_step}, combos={len(final_combos)}")

    def _set_normalization_status(self, needs_normalization: bool, triggered_by_job_id: str):
        """Set global normalization status"""
        self.table.put_item(Item={
            'PK': 'METADATA#NORMALIZATION',
            'SK': 'STATUS',
            'needs_normalization': needs_normalization,
            'triggered_by_job_id': triggered_by_job_id,
            'last_checked': datetime.utcnow().isoformat()
        })

    def get_normalization_status(self) -> Dict:
        """Get current normalization status"""
        response = self.table.get_item(
            Key={'PK': 'METADATA#NORMALIZATION', 'SK': 'STATUS'}
        )

        if 'Item' not in response:
            return {
                'needs_normalization': False,
                'last_normalized_at': None
            }

        return response['Item']

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
        ttl = int(time.time()) + (30 * 24 * 60 * 60)  # 30 days

        job = {
            'PK': 'NORMALIZATION_JOB#RUNNING',
            'SK': 'METADATA',
            'job_id': job_id,
            'status': 'running',
            'started_at': datetime.utcnow().isoformat(),
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

    def get_normalization_job(self) -> Optional[Dict]:
        """Get current running normalization job"""
        response = self.table.get_item(
            Key={'PK': 'NORMALIZATION_JOB#RUNNING', 'SK': 'METADATA'}
        )
        return response.get('Item')


def pad_number(num: int, width: int) -> str:
    """Pad a number with leading zeros"""
    return str(num).zfill(width)
