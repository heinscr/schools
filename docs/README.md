# Documentation

Complete documentation for the MA Teachers Contracts project.

## Core Documentation

### Getting Started
- **[Main README](../README.md)** - Project overview and setup
- **[Quick Start](QUICK_START.md)** - Fast setup guide for development

### Infrastructure
- **[Infrastructure Guide](INFRASTRUCTURE.md)** - AWS infrastructure overview
- **[Terraform Improvements](TERRAFORM_IMPROVEMENTS.md)** - Complete Terraform setup and best practices
- **[Custom Domain Setup](CUSTOM_DOMAIN_SETUP.md)** - CloudFront SSL configuration

### Database
- **[DynamoDB Setup](DYNAMODB_SETUP.md)** - Database schema and usage guide

### Deployment
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Step-by-step deployment instructions

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
├── README.md                    # This file - documentation index
├── QUICK_START.md               # Fast development setup
├── DEPLOYMENT_GUIDE.md          # Production deployment guide
├── INFRASTRUCTURE.md            # AWS infrastructure overview
├── TERRAFORM_IMPROVEMENTS.md    # Terraform configuration details
├── CUSTOM_DOMAIN_SETUP.md       # CloudFront custom domain setup
└── DYNAMODB_SETUP.md           # Database documentation
```

## External Resources

- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Vite Documentation](https://vitejs.dev/)
- [DynamoDB Developer Guide](https://docs.aws.amazon.com/dynamodb/)
- [AWS Lambda Python](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)
