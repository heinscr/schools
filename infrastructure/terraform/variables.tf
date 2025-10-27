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
