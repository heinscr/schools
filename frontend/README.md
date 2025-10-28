# MA Teachers Contracts - Frontend

React-based frontend for browsing Massachusetts school district information and teacher contracts.

## Features

- **District Browser**: Browse all Massachusetts school districts (356 districts)
- **Interactive Map**: View district locations on an interactive map powered by Leaflet.js
- **Search & Filter**: Search by district name, town name, or both
- **District Details**: View detailed district information in JSON format
- **Smart Geocoding**: Automatic fallback from full address to city name for reliable mapping
- **Full-Screen Layout**: Optimized design that fills the entire viewport
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
│   │   ├── DistrictBrowser.css    # Browser component styles
│   │   ├── DistrictMap.jsx        # Interactive Leaflet map component
│   │   └── DistrictMap.css        # Map component styles
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
- List view of all districts (left panel)
- Search functionality (by name, town, or both)
- Click-to-view district details
- Interactive map display (top right)
- JSON display of selected district data (bottom right)

### DistrictMap

Interactive map component using Leaflet.js:
- **Free and Open**: Uses OpenStreetMap (no API key required)
- **Single Marker**: Shows one district location at a time
- **Auto-Pan & Zoom**: Smoothly animates to selected district
- **Info Popup**: Displays district name and address
- **Smart Geocoding**: Falls back to city name if full address not found
- **Massachusetts-Centered**: Initial view shows entire state

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
2. Map pans and zooms to district location with a marker
3. Full district information displays on the right in JSON format
4. Click another district to move the marker to new location

## Environment Variables

- `VITE_API_URL`: Backend API base URL (default: `http://localhost:8000`)

## Technologies

- **React 18**: UI library with hooks (useState, useEffect, useRef)
- **Vite**: Build tool and development server with HMR
- **Leaflet.js**: Interactive maps library
- **OpenStreetMap**: Free map tiles and Nominatim geocoding
- **CSS**: Vanilla CSS with responsive design and grid layout
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

### Map Not Loading

- Check browser console for Leaflet errors
- Ensure `leaflet` package is installed: `npm install leaflet`
- Verify Leaflet CSS is imported in `DistrictMap.jsx`
- Check for ad blockers blocking OpenStreetMap tiles

### Geocoding Issues

- Some new street addresses may not be in OpenStreetMap yet
- Component automatically falls back to city-level geocoding
- Check browser console for "trying city fallback" messages
- Nominatim has a 1 request/second rate limit (shouldn't affect normal usage)

## Map Feature Details

### How the Map Works

The interactive map uses **Leaflet.js** with **OpenStreetMap** tiles - completely free with no API key required!

**Technology Stack:**
- **Leaflet**: Open-source JavaScript library for interactive maps
- **OpenStreetMap**: Free, crowdsourced map data
- **Nominatim**: Free geocoding service (address → coordinates)

**Workflow:**
1. User clicks a district in the list
2. District's `main_address` is geocoded via Nominatim API
3. If full address not found, automatically falls back to city name
4. Map smoothly pans and zooms to location (zoom level 12)
5. Marker appears with popup showing district name and address
6. When another district is clicked, old marker is removed

### Nominatim Usage Policy

- **Free for fair use** - No API key needed
- **Rate limit**: 1 request per second
- **Attribution**: Must credit OpenStreetMap contributors
- **Heavy usage**: For >100k requests/day, host your own Nominatim instance

For this application, usage is minimal (only geocodes when user clicks a district), so well within free tier.

### Customization Options

**Change Map Tiles:**

Edit `DistrictMap.jsx` to use different tile providers:

```javascript
// Default: OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')

// CartoDB Positron (light theme)
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png')

// CartoDB Dark Matter
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png')
```

**Adjust Initial View:**

```javascript
const MA_CENTER = [42.4072, -71.3824];  // [latitude, longitude]
const map = L.map(mapRef.current).setView(MA_CENTER, 8); // zoom level
```

**Custom Marker Icon:**

```javascript
const customIcon = L.icon({
  iconUrl: '/path/to/icon.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
const marker = L.marker(latLng, { icon: customIcon });
```

### Why Not Google Maps?

| Solution | Cost | API Key | Free Tier |
|----------|------|---------|-----------|
| **Leaflet + OSM** | Free | No | Unlimited |
| Google Maps | $7/1k loads | Yes | $200/month credit |
| Mapbox | $0.50/1k loads | Yes | 50k loads/month |
| HERE Maps | $1/1k loads | Yes | Limited free tier |

**Leaflet + OpenStreetMap** was chosen for:
- Zero cost (truly free, not just free tier)
- No API key management
- No usage tracking or billing
- Community-driven open data
- Excellent documentation

### Resources

- [Leaflet Documentation](https://leafletjs.com/)
- [OpenStreetMap](https://www.openstreetmap.org/)
- [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
- [Leaflet Tile Providers](https://leaflet-extras.github.io/leaflet-providers/preview/)
