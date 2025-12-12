# Documentation

Complete documentation for the MA Teachers Contracts project.

## Core Documentation

### Getting Started
- **[Main README](../README.md)** - Project overview and setup
- **[Quick Start](QUICK_START.md)** - Fast setup guide for development

### Infrastructure & Deployment
- **[Infrastructure Guide](INFRASTRUCTURE.md)** - AWS infrastructure overview
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Step-by-step deployment instructions
- **[Custom Domain Setup](CUSTOM_DOMAIN_SETUP.md)** - CloudFront SSL configuration

### Database
- **[DynamoDB Setup](DYNAMODB_SETUP.md)** - District data schema and usage
- **[DynamoDB Layout](DYNAMODB_LAYOUT.md)** - Complete table structure reference

### Authentication
- **[Authentication](AUTHENTICATION.md)** - AWS Cognito setup and user management

### Salary Data
- **[Salary API Setup](SALARY_API_SETUP.md)** - Salary data API deployment and usage
- **[Contract Processing](S3_CONTRACT_PROCESSING.md)** - Automated PDF extraction with Textract

### Frontend
- **[Frontend README](../frontend/README.md)** - React app documentation

## Quick Links

### Development
- Backend: `cd backend && source venv/bin/activate && uvicorn main:app --reload`
- Frontend: `cd frontend && npm run dev`
- API Docs: http://localhost:8000/docs (when running locally)

### Deployment
```bash
# Deploy everything
./deploy.sh

# Or simplified with Terraform
./deploy-simple.sh
```

### Infrastructure Management
```bash
cd infrastructure/terraform
terraform plan
terraform apply
```

## Documentation Structure

```
docs/
├── README.md                           # This file - documentation index
├── QUICK_START.md                      # Fast development setup
├── DEPLOYMENT_GUIDE.md                 # Production deployment guide
├── INFRASTRUCTURE.md                   # AWS infrastructure overview
├── CUSTOM_DOMAIN_SETUP.md              # CloudFront custom domain setup
├── AUTHENTICATION.md                   # Cognito authentication setup
├── DYNAMODB_SETUP.md                   # Districts table documentation
├── DYNAMODB_LAYOUT.md                  # Complete table structure
├── SALARY_API_SETUP.md                 # Salary data API guide
├── S3_CONTRACT_PROCESSING.md           # PDF contract extraction
├── YEAR_PERIOD_FILTERING.md            # Salary data filtering logic
├── SALARY_SERVICE_OPTIMIZATION.md      # Performance optimization guide
└── archive/                            # Historical/reference documents
    ├── COGNITO_MIGRATION.md            # Cognito migration notes
    ├── TERRAFORM_IMPROVEMENTS.md       # Terraform migration notes
    ├── SALARY_TERRAFORM_INTEGRATION.md # Salary integration notes
    ├── SALARY_DATA_DESIGN.md           # Original salary design
    ├── SALARY_DATA_SUMMARY.md          # Salary implementation summary
    └── CONTRACT_SCRAPING_TEST_RESULTS.md # Contract extraction tests
```

## External Resources

- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Vite Documentation](https://vitejs.dev/)
- [DynamoDB Developer Guide](https://docs.aws.amazon.com/dynamodb/)
- [AWS Lambda Python](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)
