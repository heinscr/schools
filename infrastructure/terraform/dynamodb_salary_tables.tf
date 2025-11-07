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
# - PK: METADATA#AVAILABILITY
# - SK: YEAR#<yyyy>#PERIOD#<period>
#   districts: {
#     "district_id": {
#       "M+30": {"max_step": 10},
#       "B+0": {"max_step": 15},
#       ...
#     }
#   }
# Purpose: Fast lookup of which districts have which edu+credit combos for a year/period
#
# - PK: METADATA#MAXVALUES
# - SK: GLOBAL
#   max_step: 15
#   edu_credit_combos: ["B+0", "B+15", "M+30", "D+45"]  (only combos that exist in data)
# Purpose: Track global max step and edu+credit combinations that exist anywhere in data
#          Used for normalization: every district gets all existing combos × max_step entries
#          Example: If only B+0, B+15, M+30, D+45 exist globally, query for M+45 falls back to B+15
#
# GSI1 - Education/Credits Query with Step Sorting:
# - PK: YEAR#<yyyy>#PERIOD#<period>#EDU#<edu>#CR#<credits>
# - SK: STEP#<step>#DISTRICT#<districtId>
# Purpose: Get all districts with given edu/credits (any step), sorted by step
#          Enables fallback: find highest step <= target for each district
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