# Generate a runtime config file that the frontend can fetch
# This allows the frontend to work with any API endpoint without rebuilding

resource "aws_s3_object" "frontend_config" {
  bucket       = aws_s3_bucket.main.id
  key          = "frontend/config.json"
  content_type = "application/json"

  content = jsonencode({
    apiUrl = aws_api_gateway_stage.prod.invoke_url
  })

  # Update config whenever API Gateway changes
  etag = md5(jsonencode({
    apiUrl = aws_api_gateway_stage.prod.invoke_url
  }))
}
