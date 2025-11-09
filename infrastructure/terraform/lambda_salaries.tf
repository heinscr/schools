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
          "dynamodb:Scan",
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem"
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*"
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
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.main.name
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

# REST API Gateway resources for salary endpoints (added to main API Gateway)

# API Gateway resource for salary-schedule proxy
resource "aws_api_gateway_resource" "salary_schedule" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "api"
}

resource "aws_api_gateway_resource" "salary_schedule_path" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.salary_schedule.id
  path_part   = "salary-schedule"
}

resource "aws_api_gateway_resource" "salary_schedule_proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.salary_schedule_path.id
  path_part   = "{proxy+}"
}

# API Gateway resource for salary-compare
resource "aws_api_gateway_resource" "salary_compare" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.salary_schedule.id
  path_part   = "salary-compare"
}

# API Gateway resource for salary-heatmap
resource "aws_api_gateway_resource" "salary_heatmap" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.salary_schedule.id
  path_part   = "salary-heatmap"
}

# Methods for salary-schedule proxy
resource "aws_api_gateway_method" "salary_schedule_proxy" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.salary_schedule_proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

# Methods for salary-compare
resource "aws_api_gateway_method" "salary_compare" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.salary_compare.id
  http_method   = "GET"
  authorization = "NONE"
}

# Methods for salary-heatmap
resource "aws_api_gateway_method" "salary_heatmap" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.salary_heatmap.id
  http_method   = "GET"
  authorization = "NONE"
}

# Integrations with salaries Lambda
resource "aws_api_gateway_integration" "salary_schedule_lambda" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.salary_schedule_proxy.id
  http_method = aws_api_gateway_method.salary_schedule_proxy.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.salaries.invoke_arn
}

resource "aws_api_gateway_integration" "salary_compare_lambda" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.salary_compare.id
  http_method = aws_api_gateway_method.salary_compare.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.salaries.invoke_arn
}

resource "aws_api_gateway_integration" "salary_heatmap_lambda" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.salary_heatmap.id
  http_method = aws_api_gateway_method.salary_heatmap.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.salaries.invoke_arn
}

# Lambda permission for API Gateway to invoke salaries Lambda
resource "aws_lambda_permission" "salaries_api_gateway" {
  statement_id  = "AllowAPIGatewayInvokeSalaries"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.salaries.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
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