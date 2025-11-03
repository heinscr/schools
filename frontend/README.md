# MA Teachers Contracts - Frontend

React-based frontend for browsing Massachusetts school district information and teacher contracts.

## Features

- **District Browser**: Browse all Massachusetts school districts (356 districts)
- **Choropleth Map**: Interactive D3-based map showing all Massachusetts towns with district highlighting
- **Search & Filter**: Search by district name, town name, or both
- **District Details**: View detailed district information in JSON format
- **Visual District Highlighting**: Towns belonging to selected districts highlighted in purple
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
   DISTRICT_API_URL=http://localhost:8000
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
│   │   ├── ChoroplethMap.jsx      # D3-based choropleth map component
│   │   └── ChoroplethMap.css      # Map component styles
│   ├── services/
│   │   └── api.js                 # API service for backend communication
│   ├── App.jsx                    # Main app component
│   ├── App.css                    # Global app styles
│   ├── main.jsx                   # App entry point
│   └── index.css                  # Global CSS
├── public/
│   └── geojson.json               # TopoJSON data for Massachusetts towns
├── .env.example                   # Environment variables template
└── package.json                   # Dependencies and scripts
```

## Available Components

### DistrictBrowser

The main component that provides:
- List view of all districts (left panel)
- Search functionality (by name, town, or both)
- Click-to-view district details
- Choropleth map display (top right)
- JSON display of selected district data (bottom right)

### ChoroplethMap

Interactive choropleth map component using D3.js:
- **All Towns Visible**: Displays all 351 Massachusetts towns as polygons
- **District Highlighting**: Selected district's towns highlighted in purple (#7a0177)
- **Hover Tooltips**: Town names appear on hover
- **TopoJSON Support**: Efficiently loads compressed geographic data
- **Responsive**: Automatically scales to container size
- **Datawrapper-Inspired**: Clean, modern visualization style

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
2. All towns belonging to the district are highlighted in purple on the map
3. Full district information displays on the right in JSON format
4. Hover over any town to see its name in a tooltip

## Environment Variables

- `DISTRICT_API_URL`: Backend API base URL (default: `http://localhost:8000`)

## Technologies

- **React 18**: UI library with hooks (useState, useEffect, useRef)
- **Vite**: Build tool and development server with HMR
- **D3.js**: Data visualization library for rendering SVG maps
- **TopoJSON**: Efficient geographic data format (converts to GeoJSON)
- **CSS**: Vanilla CSS with responsive design and grid layout
- **Fetch API**: HTTP requests to backend

## Troubleshooting

### API Connection Errors

- Ensure backend is running on port 8000
- Check `DISTRICT_API_URL` in `.env` matches your backend URL
- Verify CORS is configured correctly in the backend

### Build Errors

- Clear node_modules and reinstall: `rm -rf node_modules && npm install`
- Clear Vite cache: `rm -rf node_modules/.vite`

### Styling Issues

- Hard refresh browser: `Ctrl+Shift+R` or `Cmd+Shift+R`
- Clear browser cache

### Map Not Loading

- Check browser console for D3 or TopoJSON errors
- Ensure `d3` and `topojson-client` packages are installed
- Verify `/geojson.json` file exists in `public/` directory
- Check that GeoJSON data is loading properly in Network tab

### Geographic Data Issues

- The map uses TopoJSON format for efficient data storage
- Data is automatically converted to GeoJSON for rendering
- Town names use the `TOWN` property in the data
- Check console for "Converting TopoJSON" messages on load

## Map Feature Details

### How the Map Works

The choropleth map uses **D3.js** to render all Massachusetts towns as SVG polygons, creating a clean geographic visualization inspired by Datawrapper.

**Technology Stack:**
- **D3.js**: Data visualization library for creating SVG-based maps
- **TopoJSON**: Compressed geographic data format (2.2MB vs 7.3MB GeoJSON)
- **topojson-client**: Library to convert TopoJSON to GeoJSON for rendering
- **geoIdentity**: D3 projection that treats coordinates as 2D cartesian coordinates

**Workflow:**
1. TopoJSON file loads from `/geojson.json` (contains all MA towns)
2. Data is converted to GeoJSON format
3. All 351 towns render as SVG paths with gray fill
4. When user selects a district, matching towns change to purple
5. Hover tooltips show individual town names
6. Map automatically scales to fit viewport with minimal padding

### Data Format

The geographic data is stored in **TopoJSON format** which:
- Compresses data by ~70% compared to GeoJSON
- Shares arc topology between adjacent polygons
- Wrapped in a `content` object with metadata
- Contains `TOWN` property for each feature

### Customization Options

**Change Colors:**

Edit `ChoroplethMap.jsx` to customize the color scheme:

```javascript
// Unselected towns (default: light gray)
.attr('fill', '#e7e7e7')

// Selected district towns (default: Datawrapper purple)
.attr('fill', '#7a0177')

// Town borders
.attr('stroke', '#ffffff')
.attr('stroke-width', 0.5)
```

**Adjust Map Padding:**

```javascript
// More zoomed out (larger padding)
const projection = d3.geoIdentity()
  .fitSize([width - 40, height - 40], geojson);

// More zoomed in (smaller padding)
const projection = d3.geoIdentity()
  .fitSize([width - 5, height - 5], geojson);
```

**Change Map Height:**

Edit `DistrictBrowser.css`:

```css
.map-section {
  height: 750px;  /* Adjust this value */
}
```

### Why D3 Instead of Leaflet?

**D3.js Choropleth** was chosen over Leaflet for:
- **Better for regional data**: Shows all towns simultaneously vs individual markers
- **Cleaner aesthetics**: SVG polygons with custom styling (Datawrapper-style)
- **No external dependencies**: No map tiles needed, fully self-contained
- **District visualization**: Perfect for showing multi-town districts
- **Performance**: Single SVG render vs hundreds of map tiles

### Resources

- [D3.js Documentation](https://d3js.org/)
- [D3 Geographic Projections](https://github.com/d3/d3-geo)
- [TopoJSON Specification](https://github.com/topojson/topojson-specification)
- [Datawrapper](https://www.datawrapper.de/) - Inspiration for map style
