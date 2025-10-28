# Massachusetts Teachers Contracts Lookup

A web application for looking up details about Massachusetts teachers contracts. Users can search and view contract information for teachers across different school districts.

## Project Structure

```
school/
├── backend/                      # Python FastAPI backend
│   ├── main.py                   # API entry point with Lambda handler
│   ├── database.py               # DynamoDB client configuration
│   ├── models.py                 # SQLAlchemy models (legacy)
│   ├── schemas.py                # Pydantic request/response schemas
│   ├── services/                 # Business logic layer
│   │   ├── district_service.py  # SQLAlchemy district service (legacy)
│   │   └── dynamodb_district_service.py  # DynamoDB district operations
│   ├── init_dynamodb_sample_data.py  # Sample data loader
│   └── requirements.txt          # Python dependencies
│
├── frontend/                     # React frontend (Vite)
│   ├── src/
│   │   ├── components/           # React components
│   │   │   ├── DistrictBrowser.jsx
│   │   │   └── DistrictBrowser.css
│   │   ├── services/             # API integration
│   │   │   └── api.js
│   │   ├── App.jsx               # Main app component
│   │   └── main.jsx              # Entry point
│   ├── .env.example              # Environment template
│   ├── .env.production           # Production API config
│   └── package.json              # Node dependencies
│
├── infrastructure/               # AWS deployment (Terraform)
│   └── terraform/                # Infrastructure as Code
│       ├── main.tf               # Main resources (Lambda, API Gateway, DynamoDB, S3, CloudFront)
│       ├── variables.tf          # Input variables
│       ├── outputs.tf            # Output values
│       ├── terraform.tfvars      # Configuration values (gitignored)
│       └── terraform.tfvars.example
│
├── docs/                         # Project documentation
│   ├── README.md                 # Documentation index
│   ├── QUICK_START.md            # Development setup guide
│   ├── DEPLOYMENT_GUIDE.md       # Production deployment
│   ├── INFRASTRUCTURE.md         # AWS infrastructure overview
│   ├── TERRAFORM_IMPROVEMENTS.md # Terraform configuration details
│   ├── CUSTOM_DOMAIN_SETUP.md    # CloudFront SSL setup
│   └── DYNAMODB_SETUP.md         # Database schema and usage
│
├── deploy.sh                     # Full deployment script
├── deploy-simple.sh              # Simplified deployment with Terraform
└── README.md                     # This file
```

## Quick Start

### Local Development

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
API available at `http://localhost:8000`

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```
Website available at `http://localhost:5173`

### AWS Deployment

See [infrastructure/README.md](infrastructure/README.md) for deployment to AWS.

Quick version:
```bash
cd infrastructure/terraform
terraform init
terraform apply

cd ../scripts
./deploy-backend-tf.sh
./deploy-frontend-tf.sh
```

## Technology Stack

### Backend
- **Python 3.12** - Runtime
- **FastAPI** - Web framework
- **DynamoDB** - NoSQL database (pay-per-request)
- **Boto3** - AWS SDK for Python
- **Pydantic** - Data validation
- **Uvicorn** - ASGI server (development)
- **Mangum** - Lambda adapter (production)

### Frontend
- **React 18** - UI library
- **Vite 4.x** - Build tool and dev server
- **Modern JavaScript** (ES6+)
- **CSS** - Vanilla CSS with responsive design

### Infrastructure (AWS)
- **Terraform** - Infrastructure as Code
- **Lambda** - Serverless compute (Python 3.12)
- **API Gateway** - REST API with Lambda proxy
- **DynamoDB** - Managed NoSQL database
- **S3** - Static asset storage
- **CloudFront** - Global CDN with custom domain
- **IAM** - Permissions and roles

## Features

### Currently Implemented ✅
- **District Browser** - Browse all Massachusetts school districts
- **Search by District** - Filter by district name
- **Search by Town** - Find districts by town name
- **District Details** - View detailed information in JSON format
- **DynamoDB Backend** - Serverless NoSQL database
- **Live in AWS** - Fully deployed and accessible

### Planned 🚧
- Teacher contract database
- Search teachers by name, school, or district
- View contract details (salary, benefits, terms)
- Export contract data
- Authentication and admin features

## Documentation

- **[Documentation Index](docs/README.md)** - Complete documentation hub
- **[Quick Start](docs/QUICK_START.md)** - Development setup
- **[Deployment Guide](docs/DEPLOYMENT_GUIDE.md)** - Production deployment
- **[DynamoDB Setup](docs/DYNAMODB_SETUP.md)** - Database guide
- **[Terraform Guide](docs/TERRAFORM_IMPROVEMENTS.md)** - Infrastructure as code
- **[Custom Domain](docs/CUSTOM_DOMAIN_SETUP.md)** - SSL setup

## Development

### Backend Development
- API endpoints: `backend/main.py`
- Database client: `backend/database.py` (DynamoDB)
- Business logic: `backend/services/dynamodb_district_service.py`
- Schemas: `backend/schemas.py` (Pydantic validation)
- Sample data: `backend/init_dynamodb_sample_data.py`

### Frontend Development
- Main component: `frontend/src/components/DistrictBrowser.jsx`
- API service: `frontend/src/services/api.js`
- Styling: Component-scoped CSS files
- Build: Vite with production optimizations

### Infrastructure Management
```bash
cd infrastructure/terraform
terraform plan    # Preview changes
terraform apply   # Deploy infrastructure
```

### Deployment
```bash
./deploy.sh              # Full deployment
./deploy-simple.sh       # Simplified with Terraform
```

## API Documentation

When running locally, FastAPI auto-generates interactive API docs:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## License

TBD
