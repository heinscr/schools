# Lambda function for salary API endpoints

# Create a placeholder for salary Lambda deployment package
data "archive_file" "placeholder_salary_lambda" {
  type        = "zip"
  output_path = "${path.module}/placeholder/salary-lambda-placeholder.zip"

  source {
    content  = <<-EOT
def handler(event, context):
    return {
        'statusCode': 503,
        'headers': {'Content-Type': 'application/json'},
        'body': '{"error": "Service not deployed yet. Please run deploy.sh"}'
    }
EOT
    filename = "salaries.py"
  }
}

# Upload placeholder to S3
resource "aws_s3_object" "salary_lambda_placeholder" {
  bucket = aws_s3_bucket.main.id
  key    = "backend/salaries.zip"
  source = data.archive_file.placeholder_salary_lambda.output_path
  etag   = data.archive_file.placeholder_salary_lambda.output_md5

  # This will be replaced when deploy.sh runs
  lifecycle {
    ignore_changes = [
      etag,
      source
    ]
  }
}

# IAM role for salary Lambda
resource "aws_iam_role" "salary_lambda_role" {
  name = "${var.project_name}-salary-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "Salary Lambda Role"
    }
  )
}

# Policy for CloudWatch Logs
resource "aws_iam_role_policy" "salary_lambda_logs" {
  name = "${var.project_name}-salary-lambda-logs"
  role = aws_iam_role.salary_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Policy for DynamoDB access
resource "aws_iam_role_policy" "salary_lambda_dynamodb" {
  name = "${var.project_name}-salary-lambda-dynamodb"
  role = aws_iam_role.salary_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem"
        ]
        Resource = [
          aws_dynamodb_table.teacher_salaries.arn,
          "${aws_dynamodb_table.teacher_salaries.arn}/index/*",
          aws_dynamodb_table.teacher_salary_schedules.arn,
          "${aws_dynamodb_table.teacher_salary_schedules.arn}/index/*",
          aws_dynamodb_table.districts.arn,
          "${aws_dynamodb_table.districts.arn}/index/*"
        ]
      }
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "salaries" {
  s3_bucket        = aws_s3_bucket.main.id
  s3_key           = "backend/salaries.zip"
  function_name    = "${var.project_name}-salaries-api"
  role            = aws_iam_role.salary_lambda_role.arn
  handler         = "salaries.handler"
  runtime         = "python3.12"
  timeout         = 30
  memory_size     = 512

  environment {
    variables = {
      SALARIES_TABLE_NAME  = aws_dynamodb_table.teacher_salaries.name
      SCHEDULES_TABLE_NAME = aws_dynamodb_table.teacher_salary_schedules.name
      DISTRICTS_TABLE_NAME = aws_dynamodb_table.districts.name
    }
  }

  tags = merge(
    local.common_tags,
    {
      Name = "Salaries API Lambda"
    }
  )

  # This allows Terraform to create the function even if the zip doesn't exist yet
  # The deploy script will upload it
  lifecycle {
    ignore_changes = [
      source_code_hash
    ]
  }

  depends_on = [
    aws_s3_object.salary_lambda_placeholder,
    aws_iam_role_policy.salary_lambda_logs,
    aws_iam_role_policy.salary_lambda_dynamodb
  ]
}

# Note: CloudWatch Log Group will be created automatically by Lambda
# when the function is first invoked

# HTTP API Gateway for salary endpoints
resource "aws_apigatewayv2_api" "salaries" {
  name          = "${var.project_name}-salaries-api"
  protocol_type = "HTTP"
  description   = "HTTP API for teacher salary data"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["*"]
    max_age       = 300
  }

  tags = merge(
    local.common_tags,
    {
      Name = "Salaries HTTP API"
    }
  )
}

# API Gateway stage
resource "aws_apigatewayv2_stage" "salaries" {
  api_id      = aws_apigatewayv2_api.salaries.id
  name        = "$default"
  auto_deploy = true

  tags = merge(
    local.common_tags,
    {
      Name = "Salaries API Stage"
    }
  )
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "salaries_api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.salaries.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.salaries.execution_arn}/*/*"
}

# API Gateway integration
resource "aws_apigatewayv2_integration" "salaries" {
  api_id           = aws_apigatewayv2_api.salaries.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.salaries.invoke_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

# Routes

# GET /api/salary-schedule/{districtId}
resource "aws_apigatewayv2_route" "salary_schedule" {
  api_id    = aws_apigatewayv2_api.salaries.id
  route_key = "GET /api/salary-schedule/{districtId}"
  target    = "integrations/${aws_apigatewayv2_integration.salaries.id}"
}

# GET /api/salary-schedule/{districtId}/{year}
resource "aws_apigatewayv2_route" "salary_schedule_year" {
  api_id    = aws_apigatewayv2_api.salaries.id
  route_key = "GET /api/salary-schedule/{districtId}/{year}"
  target    = "integrations/${aws_apigatewayv2_integration.salaries.id}"
}

# GET /api/salary-compare
resource "aws_apigatewayv2_route" "salary_compare" {
  api_id    = aws_apigatewayv2_api.salaries.id
  route_key = "GET /api/salary-compare"
  target    = "integrations/${aws_apigatewayv2_integration.salaries.id}"
}

# GET /api/salary-heatmap
resource "aws_apigatewayv2_route" "salary_heatmap" {
  api_id    = aws_apigatewayv2_api.salaries.id
  route_key = "GET /api/salary-heatmap"
  target    = "integrations/${aws_apigatewayv2_integration.salaries.id}"
}

# GET /api/districts/{id}/salary-metadata
resource "aws_apigatewayv2_route" "district_salary_metadata" {
  api_id    = aws_apigatewayv2_api.salaries.id
  route_key = "GET /api/districts/{id}/salary-metadata"
  target    = "integrations/${aws_apigatewayv2_integration.salaries.id}"
}

# Outputs
output "salaries_lambda_function_name" {
  value       = aws_lambda_function.salaries.function_name
  description = "Name of the salaries Lambda function"
}

output "salaries_lambda_function_arn" {
  value       = aws_lambda_function.salaries.arn
  description = "ARN of the salaries Lambda function"
}

output "salaries_api_endpoint" {
  value       = aws_apigatewayv2_stage.salaries.invoke_url
  description = "Salary API endpoint URL"
}

output "salaries_api_id" {
  value       = aws_apigatewayv2_api.salaries.id
  description = "Salary HTTP API Gateway ID"
}
