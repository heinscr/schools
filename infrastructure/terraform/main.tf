# Main Terraform Configuration
# Infrastructure for MA Teachers Contracts application

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }

  # Optional: Uncomment to use S3 backend for state
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "ma-teachers-contracts/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

# Get current AWS account ID
data "aws_caller_identity" "current" {}

# Local variables
locals {
  account_id      = data.aws_caller_identity.current.account_id
  s3_bucket_name  = "${var.project_name}-${local.account_id}"
  function_name   = "${var.project_name}-api"

  # Flag to enable salary processing features (check if resources will exist)
  enable_salary_processing = true

  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
    }
  )
}

# S3 Bucket (single bucket for frontend and backend)
resource "aws_s3_bucket" "main" {
  bucket = local.s3_bucket_name

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-bucket"
    }
  )
}

# Block public access to S3 bucket
resource "aws_s3_bucket_public_access_block" "main" {
  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = false  # CloudFront needs bucket policy
  ignore_public_acls      = true
  restrict_public_buckets = false  # CloudFront needs access
}

# CloudFront Origin Access Control
resource "aws_cloudfront_origin_access_control" "main" {
  name                              = "${var.project_name}-oac"
  description                       = "OAC for ${var.project_name} S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} frontend distribution"
  default_root_object = "index.html"

  # Custom domain aliases (if provided)
  aliases = var.cloudfront_domain_name != "" ? concat([var.cloudfront_domain_name], var.cloudfront_aliases) : []

  origin {
    domain_name              = aws_s3_bucket.main.bucket_regional_domain_name
    origin_id                = aws_s3_bucket.main.id
    origin_path              = "/frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.main.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = aws_s3_bucket.main.id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # Use AWS managed cache policy
    cache_policy_id          = "658327ea-f89d-4fab-a63d-7e88639e58f6"  # CachingOptimized
    origin_request_policy_id = "88a5eaf4-2fd4-4709-b370-b4c650ea3fcf"  # CORS-S3Origin
  }

  # Custom error response for SPA routing
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
    error_caching_min_ttl = 300
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    # Use custom certificate if domain is specified, otherwise use CloudFront default
    cloudfront_default_certificate = var.cloudfront_domain_name == ""
    acm_certificate_arn            = var.cloudfront_domain_name != "" ? var.cloudfront_certificate_arn : null
    ssl_support_method             = var.cloudfront_domain_name != "" ? "sni-only" : null
    minimum_protocol_version       = var.cloudfront_domain_name != "" ? "TLSv1.2_2021" : "TLSv1"
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-cloudfront"
    }
  )
}

# S3 Bucket Policy to allow CloudFront access
resource "aws_s3_bucket_policy" "main" {
  bucket = aws_s3_bucket.main.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.main.arn}/frontend/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.main]
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project_name}-api"
  description = "API for ${var.project_name}"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-api"
    }
  )
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda-role"

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
      Name = "${var.project_name}-lambda-role"
    }
  )
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Combined DynamoDB Table (Districts + Teacher Salaries)
#
# Single-table design optimized for efficient queries across districts and salary data
# with intelligent fallback matching for missing education/credit combinations
#
# Main Table Structure:
#
# District Metadata:
# - PK: DISTRICT#{districtId}
# - SK: METADATA
#
# District-Town Relationships:
# - PK: DISTRICT#{districtId}
# - SK: TOWN#{townName}
# - GSI_TOWN_PK: TOWN#{townName}
# - GSI_TOWN_SK: DISTRICT#{districtName}
#
# Salary Schedules:
# - PK: DISTRICT#{districtId}
# - SK: SCHEDULE#{yyyy}#{period}#EDU#{edu}#CR#{credits}#STEP#{step}
#
# Salary Metadata:
# - PK: METADATA#SCHEDULES | METADATA#AVAILABILITY | METADATA#MAXVALUES
# - SK: YEAR#{yyyy}#PERIOD#{period} | GLOBAL
#
# GSI1 - ExactMatchIndex (Salary comparisons across districts):
# - PK: YEAR#{yyyy}#PERIOD#{period}#EDU#{edu}#CR#{credits}
# - SK: STEP#{step}#DISTRICT#{districtId}
#
# GSI2 - FallbackQueryIndex (All salary entries for a district's schedule):
# - PK: YEAR#{yyyy}#PERIOD#{period}#DISTRICT#{districtId}
# - SK: EDU#{edu}#CR#{credits}#STEP#{step}
#
# GSI3 - GSI_TOWN (District search by town):
# - PK: TOWN#{townName}
# - SK: DISTRICT#{districtName}

resource "aws_dynamodb_table" "main" {
  name           = "${var.project_name}-data"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"

  # Primary key attributes
  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # GSI1: ExactMatchIndex - For salary comparisons across all districts
  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  # GSI2: FallbackQueryIndex - For fallback query on district's schedule
  attribute {
    name = "GSI2PK"
    type = "S"
  }

  attribute {
    name = "GSI2SK"
    type = "S"
  }

  # GSI3: GSI_TOWN - For town-based district searches
  attribute {
    name = "GSI_TOWN_PK"
    type = "S"
  }

  attribute {
    name = "GSI_TOWN_SK"
    type = "S"
  }

  # GSI1: Exact match query for salary comparisons
  global_secondary_index {
    name            = "ExactMatchIndex"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  # GSI2: Fallback query for specific district's schedule
  global_secondary_index {
    name            = "FallbackQueryIndex"
    hash_key        = "GSI2PK"
    range_key       = "GSI2SK"
    projection_type = "ALL"
  }

  # GSI3: Town-based district search
  global_secondary_index {
    name            = "GSI_TOWN"
    hash_key        = "GSI_TOWN_PK"
    range_key       = "GSI_TOWN_SK"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  # TTL for automatic cleanup of temporary items (jobs)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-combined-data"
    }
  )
}

# IAM Policy for Lambda to access DynamoDB
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${var.project_name}-lambda-dynamodb"
  role = aws_iam_role.lambda.id

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
          "dynamodb:BatchGetItem",
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

# IAM Policy for Lambda to access S3 (for salary processing PDFs and JSON)
resource "aws_iam_role_policy" "lambda_s3" {
  name = "${var.project_name}-lambda-s3"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.main.arn}/contracts/*"
      }
    ]
  })
}

# IAM Policy for Lambda to access SQS and invoke other Lambdas
resource "aws_iam_role_policy" "lambda_salary_processing" {
  count = local.enable_salary_processing ? 1 : 0
  name  = "${var.project_name}-lambda-salary-processing"
  role  = aws_iam_role.lambda.id

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
      },
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

# Lambda Function
resource "aws_lambda_function" "api" {
  function_name = local.function_name
  role          = aws_iam_role.lambda.arn
  handler       = "main.handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  # Code must be uploaded via S3 by deployment script
  s3_bucket = aws_s3_bucket.main.id
  s3_key    = "backend/lambda-deployment.zip"

  environment {
    variables = merge(
      {
        DYNAMODB_TABLE_NAME      = aws_dynamodb_table.main.name
        CLOUDFRONT_DOMAIN        = aws_cloudfront_distribution.frontend.domain_name
        S3_BUCKET_NAME           = aws_s3_bucket.main.id
        # Cognito configuration for JWT validation
        COGNITO_USER_POOL_ID     = aws_cognito_user_pool.main.id
        COGNITO_CLIENT_ID        = aws_cognito_user_pool_client.frontend.id
        COGNITO_REGION           = var.aws_region
      },
      # Add custom domain if configured
      var.cloudfront_domain_name != "" ? { CUSTOM_DOMAIN = var.cloudfront_domain_name } : {},
      # Add salary processing environment variables if enabled
      local.enable_salary_processing ? {
        SALARY_PROCESSING_QUEUE_URL = aws_sqs_queue.salary_processing.url
        SALARY_NORMALIZER_LAMBDA_ARN = aws_lambda_function.salary_normalizer.arn
      } : {}
    )
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-api-lambda"
    }
  )

  # Ensure the Lambda code exists in S3 before creating
  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_dynamodb,
    aws_s3_object.lambda_placeholder
  ]

  # Ignore changes to source code hash since deploy.sh will update the code
  lifecycle {
    ignore_changes = [
      source_code_hash
    ]
  }
}

# API Gateway Resources
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "{proxy+}"
}

# API Gateway Method - ANY for proxy
resource "aws_api_gateway_method" "proxy" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

# API Gateway Integration with Lambda
resource "aws_api_gateway_integration" "lambda" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# API Gateway Method - Root
resource "aws_api_gateway_method" "proxy_root" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_rest_api.main.root_resource_id
  http_method   = "ANY"
  authorization = "NONE"
}

# API Gateway Integration - Root
resource "aws_api_gateway_integration" "lambda_root" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_rest_api.main.root_resource_id
  http_method = aws_api_gateway_method.proxy_root.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy.id,
      aws_api_gateway_integration.lambda.id,
      aws_api_gateway_method.proxy_root.id,
      aws_api_gateway_integration.lambda_root.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.lambda,
    aws_api_gateway_integration.lambda_root
  ]
}

# API Gateway Stage
resource "aws_api_gateway_stage" "prod" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = "prod"

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-api-stage-prod"
    }
  )
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# Generate backend/.env file with configuration from Terraform
resource "local_file" "backend_env" {
  filename = "${path.module}/../../backend/.env"
  content = templatefile("${path.module}/backend_env.tftpl", {
    aws_region           = var.aws_region
    dynamodb_table_name  = aws_dynamodb_table.main.name
    cognito_user_pool_id = aws_cognito_user_pool.main.id
    cognito_client_id    = aws_cognito_user_pool_client.frontend.id
    cognito_region       = var.aws_region
    environment          = var.environment
  })

  file_permission = "0644"
}