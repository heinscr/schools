# AWS Cognito User Pool and Configuration
# Provides user authentication and authorization for the application

# Cognito User Pool
resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-users"

  # Email as username
  username_attributes = ["email"]

  # Automatic email verification
  auto_verified_attributes = ["email"]

  # Password policy
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # User attributes
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = false

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    required            = false
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  # Custom attribute for admin role
  schema {
    name                = "role"
    attribute_data_type = "String"
    required            = false
    mutable             = true
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  # Email configuration
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # Enable user pool MFA (optional)
  mfa_configuration = "OPTIONAL"

  # Software token MFA configuration
  software_token_mfa_configuration {
    enabled = true
  }

  # User pool add-ons
  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.project_name}-user-pool"
    }
  )
}

# Cognito User Pool Client (for frontend)
resource "aws_cognito_user_pool_client" "frontend" {
  name         = "${var.project_name}-frontend-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # OAuth configuration
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code", "implicit"]
  allowed_oauth_scopes                 = ["email", "openid", "profile", "aws.cognito.signin.user.admin"]

  # Callback URLs for authentication flow
  callback_urls = concat(
    [
      "http://localhost:5173",
      "http://localhost:3000",
    ],
    var.cloudfront_domain_name != "" ? [
      "https://${var.cloudfront_domain_name}"
    ] : [],
    length(aws_cloudfront_distribution.frontend.domain_name) > 0 ? [
      "https://${aws_cloudfront_distribution.frontend.domain_name}"
    ] : []
  )

  # Logout URLs
  logout_urls = concat(
    [
      "http://localhost:5173",
      "http://localhost:3000",
    ],
    var.cloudfront_domain_name != "" ? [
      "https://${var.cloudfront_domain_name}"
    ] : [],
    length(aws_cloudfront_distribution.frontend.domain_name) > 0 ? [
      "https://${aws_cloudfront_distribution.frontend.domain_name}"
    ] : []
  )

  # Supported identity providers
  supported_identity_providers = ["COGNITO"]

  # Token validity
  id_token_validity      = 60  # minutes
  access_token_validity  = 60  # minutes
  refresh_token_validity = 30  # days

  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"

  # Read/write attributes
  read_attributes  = ["email", "name", "custom:role"]
  write_attributes = ["email", "name"]

  # Explicit auth flows
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH"
  ]
}

# Cognito User Pool Domain
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-${local.account_id}"
  user_pool_id = aws_cognito_user_pool.main.id
}

# Create admin user group
resource "aws_cognito_user_group" "admins" {
  name         = "admins"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Administrator users with write access to districts"
  precedence   = 10
}

# Outputs
output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN"
  value       = aws_cognito_user_pool.main.arn
}

output "cognito_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.frontend.id
}

output "cognito_domain" {
  description = "Cognito User Pool Domain"
  value       = aws_cognito_user_pool_domain.main.domain
}

output "cognito_issuer" {
  description = "Cognito token issuer URL (for JWT validation)"
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
}
