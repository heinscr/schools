# Teacher Salary Data Tables
#
# Single table design optimized for efficient cross-district salary queries
# with intelligent fallback matching (finds closest match when exact match unavailable)
#
# Main Table Structure:
# - PK: DISTRICT#<districtId>
# - SK: SCHEDULE#<yyyy>#<period>#EDU#<edu>#CR#<credits>#STEP#<step>
#
# Metadata Items:
# - PK: METADATA#SCHEDULES
# - SK: YEAR#<yyyy>#PERIOD#<period>
#
# GSI1 - Exact Match Query:
# - PK: YEAR#<yyyy>#PERIOD#<period>#EDU#<edu>#CR#<credits>#STEP#<step>
# - SK: DISTRICT#<districtId>
# Purpose: Fast lookup of all districts at a specific edu/credits/step for a year/period
#
# GSI2 - Fallback Query:
# - PK: YEAR#<yyyy>#PERIOD#<period>#DISTRICT#<districtId>
# - SK: EDU#<edu>#CR#<credits>#STEP#<step>
# Purpose: Get all salary entries for a district's specific year/period schedule

resource "aws_dynamodb_table" "teacher_salaries" {
  name           = "${var.project_name}-teacher-salaries"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # GSI1: Exact match query across all districts
  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  # GSI2: Fallback query for specific district's schedule
  attribute {
    name = "GSI2PK"
    type = "S"
  }

  attribute {
    name = "GSI2SK"
    type = "S"
  }

  global_secondary_index {
    name            = "ExactMatchIndex"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "FallbackQueryIndex"
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

# Outputs
output "teacher_salaries_table_name" {
  value       = aws_dynamodb_table.teacher_salaries.name
  description = "Name of the teacher salaries table"
}

output "teacher_salaries_table_arn" {
  value       = aws_dynamodb_table.teacher_salaries.arn
  description = "ARN of the teacher salaries table"
}