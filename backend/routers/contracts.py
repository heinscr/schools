"""
Contract PDF endpoints for districts
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from typing import Optional
import boto3
import os
from botocore.exceptions import ClientError

from database import get_table
from cognito_auth import require_admin_role
from rate_limiter import limiter, GENERAL_RATE_LIMIT, WRITE_RATE_LIMIT
from services.dynamodb_district_service import DynamoDBDistrictService

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

# S3 client
s3_client = boto3.client('s3')
S3_BUCKET = os.getenv('S3_BUCKET_NAME')
CONTRACT_PDF_PREFIX = 'contracts/district_pdfs/'


def get_contract_s3_key(district_name: str) -> str:
    """Generate S3 key for a district's contract PDF"""
    return f"{CONTRACT_PDF_PREFIX}{district_name}.pdf"


@router.get("/{district_name}")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_contract_pdf(
    request: Request,
    district_name: str,
):
    """
    Get presigned URL for a district's contract PDF (unauthenticated).
    Looks up district by name (case-insensitive) via GSI_METADATA.
    """
    if not S3_BUCKET:
        raise HTTPException(status_code=500, detail="S3 bucket not configured")

    # Lookup district by name using GSI_METADATA to get the actual stored name
    table = get_table()

    # Query GSI_METADATA: SK=METADATA, name_lower=<district_name_lower>
    try:
        response = table.query(
            IndexName='GSI_METADATA',
            KeyConditionExpression='SK = :sk AND name_lower = :name_lower',
            ExpressionAttributeValues={
                ':sk': 'METADATA',
                ':name_lower': district_name.lower()
            },
            Limit=1
        )

        if not response.get('Items'):
            raise HTTPException(status_code=404, detail="District not found")

        district = response['Items'][0]
        stored_name = district.get('name')

        if not stored_name:
            raise HTTPException(status_code=404, detail="District name not found")

        # Check if contract_pdf field exists in metadata
        contract_pdf_key = district.get('contract_pdf')

        if not contract_pdf_key:
            raise HTTPException(status_code=404, detail="Contract PDF not available for this district")

        # Generate presigned URL for download (valid for 1 hour)
        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': S3_BUCKET,
                    'Key': contract_pdf_key
                },
                ExpiresIn=3600  # 1 hour
            )

            return {
                "district_name": stored_name,
                "download_url": presigned_url,
                "expires_in": 3600
            }

        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate download URL: {str(e)}")

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.put("/{district_id}")
@limiter.limit(WRITE_RATE_LIMIT)
async def upload_contract_pdf(
    request: Request,
    district_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_admin_role),
):
    """
    Upload a contract PDF for a district (admin only).
    Updates S3 and DynamoDB metadata.
    """
    if not S3_BUCKET:
        raise HTTPException(status_code=500, detail="S3 bucket not configured")

    # Validate file type
    if not file.content_type == 'application/pdf':
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Get district to verify it exists and get the name
    table = get_table()
    district = DynamoDBDistrictService.get_district(table=table, district_id=district_id)

    if not district:
        raise HTTPException(status_code=404, detail="District not found")

    district_name = district.get('name')
    if not district_name:
        raise HTTPException(status_code=500, detail="District name not found")

    # Generate S3 key using the district's actual name
    s3_key = get_contract_s3_key(district_name)

    try:
        # Read file content
        file_content = await file.read()

        # Upload to S3 (this will overwrite any existing file)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_content,
            ContentType='application/pdf',
            Metadata={
                'district_id': district_id,
                'district_name': district_name,
                'uploaded_by': user.get('username', 'unknown')
            }
        )

        # Update DynamoDB metadata: PK=DISTRICT#<district_id>, SK=METADATA
        pk = f"DISTRICT#{district_id}"
        sk = "METADATA"

        table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression='SET contract_pdf = :contract_pdf',
            ExpressionAttributeValues={
                ':contract_pdf': s3_key
            }
        )

        return {
            "message": "Contract PDF uploaded successfully",
            "district_id": district_id,
            "district_name": district_name,
            "s3_key": s3_key
        }

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
