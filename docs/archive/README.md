# Archive - Historical Documentation

This directory contains historical and reference documentation that documents completed migrations, design decisions, and implementation notes. These files are kept for reference but are no longer part of the active documentation.

## Migration Documentation

### [COGNITO_MIGRATION.md](COGNITO_MIGRATION.md)
Documents the migration from API key authentication to AWS Cognito JWT authentication. This migration was completed successfully. The file is kept for historical reference.

**Status:** ✅ Completed migration
**Reference:** See [AUTHENTICATION.md](../AUTHENTICATION.md) for current authentication documentation

### [TERRAFORM_IMPROVEMENTS.md](TERRAFORM_IMPROVEMENTS.md)
Documents the migration to complete infrastructure-as-code management with Terraform, including Lambda functions and API Gateway integration.

**Status:** ✅ Completed migration
**Reference:** The improvements are now integrated into the main Terraform configuration

### [SALARY_TERRAFORM_INTEGRATION.md](SALARY_TERRAFORM_INTEGRATION.md)
Documents the integration of salary data infrastructure into the main Terraform configuration, including table naming conventions and API Gateway consolidation.

**Status:** ✅ Completed integration
**Reference:** See [SALARY_API_SETUP.md](../SALARY_API_SETUP.md) for current salary API documentation

## Design Documentation

### [SALARY_DATA_DESIGN.md](SALARY_DATA_DESIGN.md)
Original design document for the teacher salary data schema, including the hybrid approach using both normalized and aggregated DynamoDB tables.

**Status:** 📚 Reference document
**Reference:** See [SALARY_API_SETUP.md](../SALARY_API_SETUP.md) for current implementation

### [SALARY_DATA_SUMMARY.md](SALARY_DATA_SUMMARY.md)
Implementation summary of the salary data feature, including data model, use cases, and deployment steps.

**Status:** 📚 Reference document
**Reference:** See [SALARY_API_SETUP.md](../SALARY_API_SETUP.md) for current implementation

## Test Results

### [CONTRACT_SCRAPING_TEST_RESULTS.md](CONTRACT_SCRAPING_TEST_RESULTS.md)
Results from testing the pdfplumber + regex contract extraction system, including findings about text-based vs image-based PDFs and recommendations for the hybrid approach.

**Status:** 📚 Reference document
**Reference:** See [S3_CONTRACT_PROCESSING.md](../S3_CONTRACT_PROCESSING.md) for current contract processing documentation

---

## Why Archive These Files?

These documents are moved to the archive because:

1. **Migration docs** - Describe completed one-time migrations that are now integrated
2. **Design docs** - Historical design decisions that have been implemented
3. **Test results** - Implementation testing notes that informed the final approach

They are kept for:
- Historical reference
- Understanding design decisions
- Troubleshooting context
- Onboarding new developers

## Active Documentation

For current, up-to-date documentation, see the [main docs directory](../README.md).
