# Teacher Salary Data Tables

# Main Table: Normalized salary data (one item per salary cell)
resource "aws_dynamodb_table" "teacher_salaries" {
  name           = "${var.project_name}-teacher-salaries"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "district_id"
  range_key      = "composite_key"

  attribute {
    name = "district_id"
    type = "S"
  }

  attribute {
    name = "composite_key"
    type = "S"
  }

  # GSI1: For finding top-paying districts by type
  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  # GSI2: For comparing all districts at a specific education/credits/step
  attribute {
    name = "GSI2PK"
    type = "S"
  }

  attribute {
    name = "GSI2SK"
    type = "S"
  }

  global_secondary_index {
    name            = "SalaryByTypeIndex"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "CompareDistrictsIndex"
    hash_key        = "GSI2PK"
    range_key       = "GSI2SK"
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

  tags = merge(
    local.common_tags,
    {
      Name = "Teacher Salaries"
    }
  )
}

# Cache Table: Aggregated salary schedules (one item per schedule)
resource "aws_dynamodb_table" "teacher_salary_schedules" {
  name           = "${var.project_name}-teacher-salary-schedules"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "district_id"
  range_key      = "schedule_key"

  attribute {
    name = "district_id"
    type = "S"
  }

  attribute {
    name = "schedule_key"
    type = "S"
  }

  # GSI1: For querying by district type and year
  attribute {
    name = "district_type"
    type = "S"
  }

  attribute {
    name = "school_year"
    type = "S"
  }

  global_secondary_index {
    name            = "ByDistrictTypeIndex"
    hash_key        = "district_type"
    range_key       = "school_year"
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

  tags = merge(
    local.common_tags,
    {
      Name = "Teacher Salary Schedules Cache"
    }
  )
}

# Outputs
output "teacher_salaries_table_name" {
  value       = aws_dynamodb_table.teacher_salaries.name
  description = "Name of the teacher salaries table"
}

output "teacher_salary_schedules_table_name" {
  value       = aws_dynamodb_table.teacher_salary_schedules.name
  description = "Name of the teacher salary schedules cache table"
}

output "teacher_salaries_table_arn" {
  value       = aws_dynamodb_table.teacher_salaries.arn
  description = "ARN of the teacher salaries table"
}

output "teacher_salary_schedules_table_arn" {
  value       = aws_dynamodb_table.teacher_salary_schedules.arn
  description = "ARN of the teacher salary schedules cache table"
}
