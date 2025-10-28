# Create a placeholder Lambda deployment package
# This allows Lambda to be created even before the real code is uploaded

# Zip the placeholder
data "archive_file" "placeholder_lambda" {
  type        = "zip"
  output_path = "${path.module}/placeholder/lambda-placeholder.zip"

  source {
    content  = <<-EOT
def handler(event, context):
    return {
        'statusCode': 503,
        'body': 'Service not deployed yet. Please run deploy.sh'
    }
EOT
    filename = "main.py"
  }
}

# Upload placeholder to S3 (only if the real deployment doesn't exist)
resource "aws_s3_object" "lambda_placeholder" {
  bucket = aws_s3_bucket.main.id
  key    = "backend/lambda-deployment.zip"
  source = data.archive_file.placeholder_lambda.output_path
  etag   = data.archive_file.placeholder_lambda.output_md5

  # This will be replaced when deploy.sh runs
  lifecycle {
    ignore_changes = [
      etag,
      source
    ]
  }
}
