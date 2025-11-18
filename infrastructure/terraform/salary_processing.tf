# Salary Schedule Processing Infrastructure
# Handles PDF upload, extraction, and global normalization

# =============================================================================
# Placeholder Lambda Packages
# =============================================================================

# Placeholder for salary processor Lambda
data "archive_file" "placeholder_salary_processor" {
  type        = "zip"
  output_path = "${path.module}/placeholder/salary-processor-placeholder.zip"

  source {
    content  = <<-EOT
def handler(event, context):
    return {
        'statusCode': 503,
        'body': 'Salary processor not deployed yet. Please run deploy.sh'
    }
EOT
    filename = "processor.py"
  }
}

# Upload placeholder to S3
resource "aws_s3_object" "salary_processor_placeholder" {
  bucket = aws_s3_bucket.main.id
  key    = "backend/salary-processor.zip"
  source = data.archive_file.placeholder_salary_processor.output_path
  etag   = data.archive_file.placeholder_salary_processor.output_md5

  # This will be replaced when deploy.sh runs
  lifecycle {
    ignore_changes = [
      etag,
      source
    ]
  }
}

# Placeholder for salary normalizer Lambda
data "archive_file" "placeholder_salary_normalizer" {
  type        = "zip"
  output_path = "${path.module}/placeholder/salary-normalizer-placeholder.zip"

  source {
    content  = <<-EOT
def handler(event, context):
    return {
        'statusCode': 503,
        'body': 'Salary normalizer not deployed yet. Please run deploy.sh'
    }
EOT
    filename = "normalizer.py"
  }
}

# Upload placeholder to S3
resource "aws_s3_object" "salary_normalizer_placeholder" {
  bucket = aws_s3_bucket.main.id
  key    = "backend/salary-normalizer.zip"
  source = data.archive_file.placeholder_salary_normalizer.output_path
  etag   = data.archive_file.placeholder_salary_normalizer.output_md5

  # This will be replaced when deploy.sh runs
  lifecycle {
    ignore_changes = [
      etag,
      source
    ]
  }
}

# Placeholder for backup reapply worker Lambda
data "archive_file" "placeholder_backup_reapply_worker" {
  type        = "zip"
  output_path = "${path.module}/placeholder/backup-reapply-worker-placeholder.zip"

  source {
    content  = <<-EOT
def handler(event, context):
    return {
        'statusCode': 503,
        'body': 'Backup reapply worker not deployed yet. Please run deploy.sh'
    }
EOT
    filename = "backup_reapply_worker.py"
  }
}

# Upload placeholder to S3
resource "aws_s3_object" "backup_reapply_worker_placeholder" {
  bucket = aws_s3_bucket.main.id
  key    = "backend/backup-reapply-worker.zip"
  source = data.archive_file.placeholder_backup_reapply_worker.output_path
  etag   = data.archive_file.placeholder_backup_reapply_worker.output_md5

  # This will be replaced when deploy.sh runs
  lifecycle {
    ignore_changes = [
      etag,
      source
    ]
  }
}

# =============================================================================
# SQS Queue for PDF Processing
# =============================================================================

# Main processing queue
resource "aws_sqs_queue" "salary_processing" {
  name                       = "${var.project_name}-salary-processing"
  visibility_timeout_seconds = 900  # 15 minutes (Lambda max timeout)
  message_retention_seconds  = 1209600  # 14 days
  receive_wait_time_seconds  = 20  # Enable long polling

  # Dead letter queue configuration
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.salary_processing_dlq.arn
    maxReceiveCount     = 3
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-salary-processing-queue"
    }
  )
}

# Dead letter queue for failed messages
resource "aws_sqs_queue" "salary_processing_dlq" {
  name                      = "${var.project_name}-salary-processing-dlq"
  message_retention_seconds = 1209600  # 14 days

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-salary-processing-dlq"
    }
  )
}

# =============================================================================
# Lambda Function: PDF Processing
# =============================================================================

# IAM role for PDF processor Lambda
resource "aws_iam_role" "salary_processor_lambda" {
  name = "${var.project_name}-salary-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-salary-processor-role"
    }
  )
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "salary_processor_basic" {
  role       = aws_iam_role.salary_processor_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for S3, DynamoDB, Textract, and SQS access
resource "aws_iam_role_policy" "salary_processor_access" {
  name = "${var.project_name}-salary-processor-access"
  role = aws_iam_role.salary_processor_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 access for contracts bucket
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "${aws_s3_bucket.main.arn}/contracts/*"
        ]
      },
      # DynamoDB access
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*"
        ]
      },
      # Textract access for image-based PDFs
      {
        Effect = "Allow"
        Action = [
          "textract:StartDocumentAnalysis",
          "textract:GetDocumentAnalysis"
        ]
        Resource = "*"
      },
      # SQS access
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.salary_processing.arn
      }
    ]
  })
}

# Lambda function for PDF processing
resource "aws_lambda_function" "salary_processor" {
  function_name = "${var.project_name}-salary-processor"
  role          = aws_iam_role.salary_processor_lambda.arn
  handler       = "processor.handler"
  runtime       = var.lambda_runtime
  timeout       = 900  # 15 minutes max
  memory_size   = 2048  # 2GB for PDF processing

  # Code must be uploaded via S3 by deployment script
  s3_bucket = aws_s3_bucket.main.id
  s3_key    = "backend/salary-processor.zip"

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.main.name
      S3_BUCKET_NAME      = aws_s3_bucket.main.id
      CONTRACTS_PREFIX    = "contracts"
    }
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-salary-processor"
    }
  )

  depends_on = [
    aws_iam_role_policy_attachment.salary_processor_basic,
    aws_iam_role_policy.salary_processor_access,
    aws_s3_object.salary_processor_placeholder
  ]

  # Ignore changes to source code hash since deploy.sh will update the code
  lifecycle {
    ignore_changes = [
      source_code_hash
    ]
  }
}

# SQS trigger for processor Lambda
resource "aws_lambda_event_source_mapping" "salary_processor_sqs" {
  event_source_arn = aws_sqs_queue.salary_processing.arn
  function_name    = aws_lambda_function.salary_processor.arn
  batch_size       = 1  # Process one job at a time
  enabled          = true
}

# =============================================================================
# Lambda Function: Global Normalization
# =============================================================================

# IAM role for normalizer Lambda
resource "aws_iam_role" "salary_normalizer_lambda" {
  name = "${var.project_name}-salary-normalizer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-salary-normalizer-role"
    }
  )
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "salary_normalizer_basic" {
  role       = aws_iam_role.salary_normalizer_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for DynamoDB access
resource "aws_iam_role_policy" "salary_normalizer_access" {
  name = "${var.project_name}-salary-normalizer-access"
  role = aws_iam_role.salary_normalizer_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*"
        ]
      }
    ]
  })
}

# Lambda function for global normalization
resource "aws_lambda_function" "salary_normalizer" {
  function_name = "${var.project_name}-salary-normalizer"
  role          = aws_iam_role.salary_normalizer_lambda.arn
  handler       = "normalizer.handler"
  runtime       = var.lambda_runtime
  timeout       = 900  # 15 minutes max
  memory_size   = 1024  # 1GB

  # Code must be uploaded via S3 by deployment script
  s3_bucket = aws_s3_bucket.main.id
  s3_key    = "backend/salary-normalizer.zip"

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.main.name
    }
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-salary-normalizer"
    }
  )

  depends_on = [
    aws_iam_role_policy_attachment.salary_normalizer_basic,
    aws_iam_role_policy.salary_normalizer_access,
    aws_s3_object.salary_normalizer_placeholder
  ]

  # Ignore changes to source code hash since deploy.sh will update the code
  lifecycle {
    ignore_changes = [
      source_code_hash
    ]
  }
}

# =============================================================================
# Lambda Function: Backup Reapply Worker
# =============================================================================

# IAM role for backup reapply worker Lambda
resource "aws_iam_role" "backup_reapply_worker_lambda" {
  name = "${var.project_name}-backup-reapply-worker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-backup-reapply-worker-role"
    }
  )
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "backup_reapply_worker_basic" {
  role       = aws_iam_role.backup_reapply_worker_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for DynamoDB and S3 access
resource "aws_iam_role_policy" "backup_reapply_worker_access" {
  name = "${var.project_name}-backup-reapply-worker-access"
  role = aws_iam_role.backup_reapply_worker_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "${aws_s3_bucket.main.arn}/contracts/backups/*",
          "${aws_s3_bucket.main.arn}/contracts/applied_data/*",
          aws_s3_bucket.main.arn
        ]
      }
    ]
  })
}

# Lambda function for backup reapply worker
resource "aws_lambda_function" "backup_reapply_worker" {
  function_name = "${var.project_name}-backup-reapply-worker"
  role          = aws_iam_role.backup_reapply_worker_lambda.arn
  handler       = "backup_reapply_worker.handler"
  runtime       = var.lambda_runtime
  timeout       = 900  # 15 minutes max
  memory_size   = 512  # 512MB

  # Code must be uploaded via S3 by deployment script
  s3_bucket = aws_s3_bucket.main.id
  s3_key    = "backend/backup-reapply-worker.zip"

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.main.name
      S3_BUCKET_NAME      = aws_s3_bucket.main.id
    }
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-backup-reapply-worker"
    }
  )

  depends_on = [
    aws_iam_role_policy_attachment.backup_reapply_worker_basic,
    aws_iam_role_policy.backup_reapply_worker_access,
    aws_s3_object.backup_reapply_worker_placeholder
  ]

  # Ignore changes to source code hash since deploy.sh will update the code
  lifecycle {
    ignore_changes = [
      source_code_hash
    ]
  }
}

# =============================================================================
# IAM Policies for Main API Lambda
# =============================================================================

# Add S3 contracts access to main API Lambda
resource "aws_iam_role_policy" "api_lambda_s3_contracts" {
  name = "${var.project_name}-api-lambda-s3-contracts"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "${aws_s3_bucket.main.arn}/contracts/*"
        ]
      }
    ]
  })
}

# Add SQS send permission to main API Lambda
resource "aws_iam_role_policy" "api_lambda_sqs_send" {
  name = "${var.project_name}-api-lambda-sqs-send"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueUrl"
        ]
        Resource = aws_sqs_queue.salary_processing.arn
      }
    ]
  })
}

# Add Lambda invoke permission for normalizer
resource "aws_iam_role_policy" "api_lambda_invoke_normalizer" {
  name = "${var.project_name}-api-lambda-invoke-normalizer"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.salary_normalizer.arn
      }
    ]
  })
}

# Add Lambda invoke permission for backup reapply worker
resource "aws_iam_role_policy" "api_lambda_invoke_backup_worker" {
  name = "${var.project_name}-api-lambda-invoke-backup-worker"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.backup_reapply_worker.arn
      }
    ]
  })
}

# =============================================================================
# Outputs
# =============================================================================

output "salary_processing_queue_url" {
  description = "URL of the salary processing SQS queue"
  value       = aws_sqs_queue.salary_processing.url
}

output "salary_processor_lambda_name" {
  description = "Name of the salary processor Lambda function"
  value       = aws_lambda_function.salary_processor.function_name
}

output "salary_processor_lambda_arn" {
  description = "ARN of the salary processor Lambda function"
  value       = aws_lambda_function.salary_processor.arn
}

output "salary_normalizer_lambda_name" {
  description = "Name of the salary normalizer Lambda function"
  value       = aws_lambda_function.salary_normalizer.function_name
}

output "salary_normalizer_lambda_arn" {
  description = "ARN of the salary normalizer Lambda function"
  value       = aws_lambda_function.salary_normalizer.arn
}

output "backup_reapply_worker_lambda_name" {
  description = "Name of the backup reapply worker Lambda function"
  value       = aws_lambda_function.backup_reapply_worker.function_name
}

output "backup_reapply_worker_lambda_arn" {
  description = "ARN of the backup reapply worker Lambda function"
  value       = aws_lambda_function.backup_reapply_worker.arn
}
