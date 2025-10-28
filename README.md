# Massachusetts Teachers Contracts Lookup

A web application for looking up details about Massachusetts teachers contracts. Users can search and view contract information for teachers across different school districts.

## Project Structure

```
school/
├── backend/                      # Python FastAPI backend
│   ├── main.py                   # API entry point
│   ├── database.py               # DynamoDB client
│   ├── schemas.py                # Pydantic schemas
│   ├── services/
│   │   ├── district_service.py
│   │   └── dynamodb_district_service.py
│   ├── import_districts.py
│   ├── init_dynamodb_sample_data.py
│   ├── models.py
│   ├── requirements.txt
│   └── .env.example
│
├── data/                         # District and map data
│   ├── all_districts.json
│   ├── districts.json
│   ├── extract_town_geojson.py
│   ├── geojson.json              # Filtered GeoJSON for towns
│   ├── ma_municipalities.geojson # Source GeoJSON
│   └── README.md
│
├── docs/                         # Documentation
│   ├── CUSTOM_DOMAIN_SETUP.md
│   ├── DEPLOYMENT_GUIDE.md
│   ├── DYNAMODB_SETUP.md
│   ├── INFRASTRUCTURE.md
│   ├── QUICK_START.md
│   ├── README.md
│   └── TERRAFORM_IMPROVEMENTS.md
│
├── frontend/                     # React frontend (Vite)
│   ├── public/
│   │   ├── geojson.json          # Copied for deployment
│   │   └── vite.svg
│   ├── src/
│   │   ├── components/
│   │   │   ├── DistrictBrowser.jsx
│   │   │   ├── DistrictBrowser.css
│   │   │   ├── DistrictMap.jsx
│   │   │   └── DistrictMap.css
│   │   ├── services/
│   │   │   └── api.js
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── .env.example
│   ├── .env.production
│   └── README.md
│
├── infrastructure/
│   └── terraform/
│       ├── main.tf
│       ├── outputs.tf
│       ├── placeholder_lambda.tf
│       ├── frontend_config.tf
│       ├── frontend_build.tf.example
│       ├── variables.tf
│       ├── terraform.tfvars
│       ├── terraform.tfvars.example
│       ├── terraform.tfstate
│       ├── terraform.tfstate.backup
│       └── .gitignore
│
├── deploy.sh                     # Main deployment script
├── deploy-simple.sh              # Legacy deployment
├── LICENSE
└── README.md
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
- **Smart Highlight** - Selecting district will highlight all towns on map
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
