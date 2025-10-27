# Massachusetts Teachers Contracts Lookup

A web application for looking up details about Massachusetts teachers contracts. Users can search and view contract information for teachers across different school districts.

## Project Structure

```
school/
├── backend/              # Python FastAPI backend
│   ├── main.py          # API entry point
│   └── requirements.txt
├── frontend/            # React frontend (Vite)
│   ├── src/
│   └── package.json
├── infrastructure/      # AWS deployment (Terraform)
│   ├── terraform/       # Infrastructure as Code
│   └── scripts/         # Deployment scripts
└── docs/                # Project documentation
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
- **SQLAlchemy** - Database ORM
- **Uvicorn** - ASGI server
- **Mangum** - Lambda adapter

### Frontend
- **React** - UI library
- **Vite 4.x** - Build tool (Node 18 compatible)
- **Modern JavaScript** (ES6+)

### Infrastructure
- **Terraform** - Infrastructure as Code
- **AWS Lambda** - Serverless backend
- **AWS S3** - Storage
- **AWS CloudFront** - CDN
- **AWS API Gateway** - REST API

## Features (Planned)

- Search teachers contracts by district, school, or teacher name
- View contract details including salary, benefits, and terms
- Filter and sort contract information
- Export contract data

## Documentation

- **[Quick Start](/docs/TERRAFORM_QUICKSTART.md)** - Get running in 5 minutes
- **[Terraform Guide](/docs/terraform-guide.md)** - Infrastructure management
- **[Infrastructure README](infrastructure/README.md)** - Deployment workflows

## Development

### Backend Development
- API endpoints in `backend/main.py`
- Database models in `backend/models.py` (future)
- Business logic in `backend/services/` (future)

### Frontend Development
- React components in `frontend/src/components/`
- API calls in `frontend/src/services/`
- Routing with React Router (to be added)

### Infrastructure Changes
- Edit `infrastructure/terraform/*.tf` files
- Run `terraform plan` to preview
- Run `terraform apply` to deploy

## API Documentation

When running locally, FastAPI auto-generates interactive API docs:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## License

TBD
