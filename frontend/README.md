# MA Teachers Contracts - Frontend

React-based frontend for browsing Massachusetts school district information and teacher contracts.

## Features

- **District Browser**: Browse all Massachusetts school districts
- **Search & Filter**: Search by district name, town name, or both
- **District Details**: View detailed district information in JSON format
- **Responsive Design**: Works on desktop and mobile devices

## Getting Started

### Prerequisites

- Node.js 16+ and npm
- Backend API running on port 8000

### Installation

```bash
npm install
```

### Development

1. Create environment configuration:
   ```bash
   cp .env.example .env
   ```

2. Update `.env` if your backend is running on a different URL:
   ```
   VITE_API_URL=http://localhost:8000
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

4. Open your browser to [http://localhost:5173](http://localhost:5173)

### Building for Production

```bash
npm run build
```

This creates an optimized production build in the `dist/` directory.

### Preview Production Build

```bash
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── DistrictBrowser.jsx    # Main district browsing component
│   │   └── DistrictBrowser.css    # Component styles
│   ├── services/
│   │   └── api.js                 # API service for backend communication
│   ├── App.jsx                    # Main app component
│   ├── App.css                    # Global app styles
│   ├── main.jsx                   # App entry point
│   └── index.css                  # Global CSS
├── public/                        # Static assets
├── .env.example                   # Environment variables template
└── package.json                   # Dependencies and scripts
```

## Available Components

### DistrictBrowser

The main component that provides:
- List view of all districts
- Search functionality (by name, town, or both)
- Click-to-view district details
- JSON display of selected district data

### API Service

The `api.js` service provides methods for:
- `getDistricts(params)` - Fetch districts with optional filters
- `searchDistricts(query, params)` - Search districts by name or town
- `getDistrict(districtId)` - Get specific district details
- `createDistrict(data)` - Create new district (admin feature)

## Usage

### Basic Search

1. **Search All**: Leave filter on "Search All" and type any district or town name
2. **District Name**: Select "District Name" filter and search for specific districts
3. **Town Name**: Select "Town Name" filter to find districts by town

### View District Details

1. Click on any district in the list
2. Full district information displays on the right in JSON format
3. Click "Close" to deselect

## Environment Variables

- `VITE_API_URL`: Backend API base URL (default: `http://localhost:8000`)

## Technologies

- **React 18**: UI library
- **Vite**: Build tool and development server
- **CSS**: Vanilla CSS with responsive design
- **Fetch API**: HTTP requests to backend

## Troubleshooting

### API Connection Errors

- Ensure backend is running on port 8000
- Check `VITE_API_URL` in `.env` matches your backend URL
- Verify CORS is configured correctly in the backend

### Build Errors

- Clear node_modules and reinstall: `rm -rf node_modules && npm install`
- Clear Vite cache: `rm -rf node_modules/.vite`

### Styling Issues

- Hard refresh browser: `Ctrl+Shift+R` or `Cmd+Shift+R`
- Clear browser cache
