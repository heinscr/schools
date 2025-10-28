# Outputs - Values needed by deployment scripts

output "project_name" {
  description = "Project name"
  value       = var.project_name
}

output "aws_account_id" {
  description = "AWS Account ID"
  value       = local.account_id
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

output "s3_bucket" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.main.id
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.main.arn
}

output "frontend_s3_prefix" {
  description = "S3 prefix for frontend files"
  value       = "frontend/"
}

output "backend_s3_prefix" {
  description = "S3 prefix for backend deployment packages"
  value       = "backend/"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain" {
  description = "CloudFront domain name"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_arn" {
  description = "CloudFront ARN"
  value       = aws_cloudfront_distribution.frontend.arn
}

output "website_url" {
  description = "Website URL"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "api_gateway_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.main.id
}

output "api_gateway_root_resource_id" {
  description = "API Gateway root resource ID"
  value       = aws_api_gateway_rest_api.main.root_resource_id
}

output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.api.arn
}

output "lambda_role_arn" {
  description = "Lambda execution role ARN"
  value       = aws_iam_role.lambda.arn
}

output "lambda_role_name" {
  description = "Lambda execution role name"
  value       = aws_iam_role.lambda.name
}

output "lambda_function_name" {
  description = "Lambda function name (for deployment scripts)"
  value       = local.function_name
}

output "dynamodb_districts_table_name" {
  description = "DynamoDB districts table name"
  value       = aws_dynamodb_table.districts.name
}

output "dynamodb_districts_table_arn" {
  description = "DynamoDB districts table ARN"
  value       = aws_dynamodb_table.districts.arn
}

# Combined output for easy reference
output "deployment_config" {
  description = "Complete configuration for deployment scripts"
  value = {
    project_name   = var.project_name
    aws_account_id = local.account_id
    region         = var.aws_region
    s3_bucket      = aws_s3_bucket.main.id
    frontend = {
      s3_prefix              = "frontend/"
      cloudfront_distribution_id = aws_cloudfront_distribution.frontend.id
      cloudfront_domain      = aws_cloudfront_distribution.frontend.domain_name
      cloudfront_arn         = aws_cloudfront_distribution.frontend.arn
      website_url            = "https://${aws_cloudfront_distribution.frontend.domain_name}"
    }
    backend = {
      s3_prefix                     = "backend/"
      api_gateway_id                = aws_api_gateway_rest_api.main.id
      api_gateway_root_resource_id  = aws_api_gateway_rest_api.main.root_resource_id
      api_endpoint                  = "https://${aws_api_gateway_rest_api.main.id}.execute-api.${var.aws_region}.amazonaws.com/prod"
      lambda_role_arn               = aws_iam_role.lambda.arn
      lambda_function_name          = local.function_name
    }
    database = {
      dynamodb_districts_table_name = aws_dynamodb_table.districts.name
      dynamodb_districts_table_arn  = aws_dynamodb_table.districts.arn
    }
  }
  sensitive = false
}
