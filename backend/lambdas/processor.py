"""
Lambda function to process uploaded PDF contracts
Uses HybridContractExtractor (pdfplumber + AWS Textract)
"""
import json
import os
import logging
import boto3
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Get environment variables
TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']

# Initialize table
table = dynamodb.Table(TABLE_NAME)

# Import hybrid extractor (assuming it's packaged with the Lambda)
from services.hybrid_extractor import HybridContractExtractor


def handler(event, context):
    """
    Lambda handler for processing PDF contracts

    Event format (from SQS):
    {
        "Records": [{
            "body": "{\"job_id\": \"...\", \"district_id\": \"...\", \"s3_pdf_key\": \"...\", \"s3_json_key\": \"...\"}"
        }]
    }
    """
    logger.info(f"Processing event: {json.dumps(event)}")

    # Process each SQS record
    for record in event.get('Records', []):
        try:
            # Parse message body
            message = json.loads(record['body'])
            job_id = message['job_id']
            district_id = message['district_id']
            s3_pdf_key = message['s3_pdf_key']
            s3_json_key = message['s3_json_key']

            logger.info(f"Processing job {job_id} for district {district_id}")

            # Update job status to processing
            update_job_status(job_id, 'processing')

            try:
                # Download PDF from S3
                logger.info(f"Downloading PDF from s3://{S3_BUCKET_NAME}/{s3_pdf_key}")
                pdf_response = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_pdf_key)
                pdf_bytes = pdf_response['Body'].read()

                # Extract data using HybridContractExtractor
                logger.info("Extracting data from PDF...")
                extractor = HybridContractExtractor()

                # Extract with pdfplumber or Textract
                records = extractor.extract_from_s3(S3_BUCKET_NAME, s3_pdf_key)

                if not records:
                    # No tables found
                    logger.warning(f"No tables found in PDF for job {job_id}")
                    update_job_status(
                        job_id,
                        'failed',
                        error_message="No salary tables could be extracted from the PDF"
                    )
                    continue

                logger.info(f"Extracted {len(records)} salary records")

                # Get unique years
                years_found = sorted(list(set(r['school_year'] for r in records)))
                logger.info(f"Years found: {years_found}")

                # Convert Decimal to float for JSON serialization
                json_records = []
                for record in records:
                    json_record = dict(record)
                    if isinstance(json_record.get('salary'), Decimal):
                        json_record['salary'] = float(json_record['salary'])
                    json_records.append(json_record)

                # Save JSON to S3
                logger.info(f"Saving extracted data to s3://{S3_BUCKET_NAME}/{s3_json_key}")
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=s3_json_key,
                    Body=json.dumps(json_records, indent=2),
                    ContentType='application/json'
                )

                # Update job status to completed
                update_job_status(
                    job_id,
                    'completed',
                    extracted_records_count=len(records),
                    years_found=years_found
                )

                logger.info(f"Successfully processed job {job_id}")

            except Exception as e:
                # Update job status to failed
                error_message = str(e)
                logger.error(f"Error processing job {job_id}: {error_message}")
                update_job_status(job_id, 'failed', error_message=error_message)

        except Exception as e:
            logger.error(f"Error processing SQS record: {str(e)}")
            # Don't raise - let other records process
            continue

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Processing complete'})
    }


def update_job_status(
    job_id: str,
    status: str,
    extracted_records_count: int = None,
    years_found: list = None,
    error_message: str = None
):
    """Update job status in DynamoDB"""
    from datetime import datetime

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

    table.update_item(
        Key={'PK': f'JOB#{job_id}', 'SK': 'METADATA'},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values
    )

    logger.info(f"Updated job {job_id} status to {status}")
