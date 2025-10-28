# Massachusetts Teachers Contracts Lookup

A web application for looking up details about Massachusetts teachers contracts. Users can search and view contract information for teachers across different school districts.

## Project Structure

```
school/
├── backend/                      # Python FastAPI backend
│   ├── main.py                   # API entry point with Lambda handler and CORS
│   ├── database.py               # DynamoDB client configuration
│   ├── schemas.py                # Pydantic request/response schemas
│   ├── services/                 # Business logic layer
│   │   ├── district_service.py          # SQLAlchemy district service (legacy)
│   │   └── dynamodb_district_service.py # DynamoDB district operations
│   ├── import_districts.py       # Import districts from JSON to DynamoDB
│   ├── init_dynamodb_sample_data.py  # Sample data loader
│   ├── models.py                 # SQLAlchemy models (legacy, unused)
│   ├── init_sample_data.py       # Legacy sample data (unused)
│   ├── requirements.txt          # Python dependencies
│   └── .env.example              # Environment template
│
├── frontend/                     # React frontend (Vite)
│   ├── src/
│   │   ├── components/           # React components
│   │   │   ├── DistrictBrowser.jsx   # Main district browser with search
│   │   │   ├── DistrictBrowser.css   # Browser styles
│   │   │   ├── DistrictMap.jsx       # Interactive Leaflet map
│   │   │   └── DistrictMap.css       # Map styles
│   │   ├── services/             # API integration
│   │   │   └── api.js
│   │   ├── App.jsx               # Main app component
│   │   ├── App.css               # App styles
│   │   ├── main.jsx              # Entry point
│   │   └── index.css             # Global styles
│   ├── .env.example              # Environment template
│   ├── .env.production           # Production API config (deprecated - use deploy.sh)
│   ├── package.json              # Node dependencies
│   └── vite.config.js            # Vite configuration
│
├── infrastructure/               # AWS deployment (Terraform)
│   ├── terraform/                # Infrastructure as Code
│   │   ├── main.tf               # Main resources (S3, CloudFront, DynamoDB, IAM, Lambda, API Gateway)
│   │   ├── placeholder_lambda.tf # Placeholder Lambda package for initial deployment
│   │   ├── frontend_config.tf    # Runtime config file for frontend
│   │   ├── frontend_build.tf.example  # Optional: Build frontend with Terraform
│   │   ├── variables.tf          # Input variables
│   │   ├── outputs.tf            # Output values
│   │   ├── terraform.tfvars      # Configuration values (gitignored)
│   │   └── terraform.tfvars.example  # Configuration template
│   └── scripts/                  # Legacy deployment scripts
│       ├── deploy-backend-tf.sh
│       └── deploy-frontend-tf.sh
│
├── data/                         # District data files
│   ├── districts.json            # Massachusetts school districts with addresses
│   └── all_districts.json        # Complete districts dataset
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
├── deploy.sh                     # Main deployment script (deploys backend + frontend)
├── deploy-simple.sh              # Legacy simplified deployment
├── LICENSE                       # MIT License
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

**Step 1: Initialize Terraform**
```bash
cd infrastructure/terraform
terraform init
```

**Step 2: Configure variables**
```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

**Step 3: Deploy infrastructure**
```bash
terraform apply
```

**Step 4: Deploy application code**
```bash
cd ../../
./deploy.sh
```

The deploy script will:
- Package and upload Lambda backend code
- Build frontend with correct API endpoint from Terraform
- Upload frontend to S3
- Invalidate CloudFront cache

**Step 5: Import district data (optional)**
```bash
cd backend
source venv/bin/activate
python import_districts.py --file ../data/districts.json
```

See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for detailed deployment instructions.

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
- **Leaflet.js** - Interactive maps
- **OpenStreetMap** - Free map tiles and geocoding
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
- **District Browser** - Browse all Massachusetts school districts (356 districts)
- **Interactive Map** - View district locations on OpenStreetMap (powered by Leaflet.js)
- **Smart Geocoding** - Automatic address-to-coordinates conversion with fallback
- **Search by District** - Filter by district name
- **Search by Town** - Find districts by town name
- **District Details** - View detailed information in JSON format
- **Full-Screen Layout** - Responsive design that fills the entire viewport
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
- District browser: `frontend/src/components/DistrictBrowser.jsx`
- Interactive map: `frontend/src/components/DistrictMap.jsx`
- API service: `frontend/src/services/api.js`
- Styling: Component-scoped CSS files
- Build: Vite with production optimizations
- Map: Leaflet.js + OpenStreetMap (no API key required)

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

MIT License - See [LICENSE](LICENSE) file for details
