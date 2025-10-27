# Variables for MA Teachers Contracts Infrastructure

variable "project_name" {
  description = "Project name (lowercase, hyphens only)"
  type        = string
  default     = "ma-teachers-contracts"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must be lowercase letters, numbers, and hyphens only."
  }
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "lambda_runtime" {
  description = "Lambda runtime version"
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_memory" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 512
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "MA Teachers Contracts"
    ManagedBy   = "Terraform"
  }
}

# CloudFront custom domain configuration
variable "cloudfront_domain_name" {
  description = "Custom domain name for CloudFront distribution (e.g., www.example.com). Leave empty to use CloudFront default domain."
  type        = string
  default     = ""
}

variable "cloudfront_certificate_arn" {
  description = "ARN of ACM certificate in us-east-1 for custom domain. Required if cloudfront_domain_name is set."
  type        = string
  default     = ""

  validation {
    condition     = var.cloudfront_domain_name == "" || (var.cloudfront_domain_name != "" && var.cloudfront_certificate_arn != "")
    error_message = "cloudfront_certificate_arn is required when cloudfront_domain_name is specified."
  }

  validation {
    condition     = var.cloudfront_certificate_arn == "" || can(regex("^arn:aws:acm:us-east-1:[0-9]{12}:certificate/.+$", var.cloudfront_certificate_arn))
    error_message = "cloudfront_certificate_arn must be a valid ACM certificate ARN in us-east-1 region."
  }
}

variable "cloudfront_aliases" {
  description = "Additional domain aliases for CloudFront (e.g., ['example.com', 'www.example.com']). Leave empty to use only cloudfront_domain_name."
  type        = list(string)
  default     = []
}
