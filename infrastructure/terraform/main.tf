# Main Terraform Configuration
# Infrastructure for MA Teachers Contracts application

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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
    cloudfront_default_certificate = true
    # To use custom domain:
    # acm_certificate_arn      = aws_acm_certificate.cert.arn
    # ssl_support_method       = "sni-only"
    # minimum_protocol_version = "TLSv1.2_2021"
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

# Note: Lambda function itself is created by deployment script
# This is because the function code changes frequently and shouldn't be in Terraform
