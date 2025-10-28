import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './DistrictMap.css';

// Fix for default marker icons in Leaflet with Vite
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});

const DistrictMap = ({ address, districtName, selectedDistrict }) => {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markerRef = useRef(null);
  const geoJsonLayerRef = useRef(null);
  const [geojson, setGeojson] = useState(null);
  const [geojsonLoaded, setGeojsonLoaded] = useState(false);
  // Load GeoJSON once and cache
  useEffect(() => {
    if (geojsonLoaded || geojson) return;
    fetch('/geojson.json')
      .then((res) => res.json())
      .then((data) => {
        setGeojson(data);
        setGeojsonLoaded(true);
      })
      .catch(() => setGeojsonLoaded(false));
  }, [geojsonLoaded, geojson]);
  // Highlight towns for selected district and clear pin if needed
  useEffect(() => {
    if (!mapInstanceRef.current || !geojson || !selectedDistrict) {
      // Remove previous geojson layer if present
      if (geoJsonLayerRef.current) {
        geoJsonLayerRef.current.remove();
        geoJsonLayerRef.current = null;
      }
      // Remove marker if present (clear pin)
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
      return;
    }

    // Remove previous geojson layer
    if (geoJsonLayerRef.current) {
      geoJsonLayerRef.current.remove();
      geoJsonLayerRef.current = null;
    }

    // Get towns for selected district
    const towns = selectedDistrict.members || selectedDistrict.towns || [];
    // Normalize for matching
    const townSet = new Set(towns.map(t => t.trim().toLowerCase()));

    // Filter geojson features for these towns
    const matchedFeatures = geojson.features.filter(f => {
      const props = f.properties;
      // Try multiple possible property keys
      const keys = ['NAME', 'TOWN', 'TOWN_NAME'];
      let name = '';
      for (const k of keys) {
        if (props[k]) {
          name = props[k];
          break;
        }
      }
      return townSet.has(name.trim().toLowerCase());
    });

    if (matchedFeatures.length === 0) return;

    // Create a new geojson layer for these towns
    const layer = L.geoJSON({ type: 'FeatureCollection', features: matchedFeatures }, {
      style: {
        color: '#1976d2',
        weight: 2,
        fillColor: '#1976d2',
        fillOpacity: 0.5,
      },
      onEachFeature: (feature, layer) => {
        layer.bindPopup(feature.properties.NAME || feature.properties.TOWN || feature.properties.TOWN_NAME || '');
      }
    });
    layer.addTo(mapInstanceRef.current);
    geoJsonLayerRef.current = layer;

    // Optionally zoom to bounds
    try {
      mapInstanceRef.current.fitBounds(layer.getBounds(), { animate: true, duration: 0.5 });
    } catch {}

    // Cleanup on district change
    return () => {
      if (geoJsonLayerRef.current) {
        geoJsonLayerRef.current.remove();
        geoJsonLayerRef.current = null;
      }
      // Remove marker if present (clear pin)
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
    };
  }, [selectedDistrict, geojson]);

  // Massachusetts center coordinates
  const MA_CENTER = [42.4072, -71.3824];

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // Create map instance
    const map = L.map(mapRef.current).setView(MA_CENTER, 8);

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    mapInstanceRef.current = map;

    // Cleanup on unmount
    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // Update marker when address changes
  useEffect(() => {
    if (!mapInstanceRef.current || !address) {
      // Remove marker if no address
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
      return;
    }

    // Remove existing marker
    if (markerRef.current) {
      markerRef.current.remove();
    }

    // Geocode the address using Nominatim (OpenStreetMap's geocoding service)
    const geocodeAddress = async () => {
      try {
        // Try full address first
        let query = encodeURIComponent(`${address}, Massachusetts, USA`);
        let response = await fetch(
          `https://nominatim.openstreetmap.org/search?format=json&q=${query}&limit=1`
        );
        let data = await response.json();

        // If no results, try fallback: extract city from address
        if (!data || data.length === 0) {
          console.log('Full address not found, trying city fallback for:', address);

          // Extract city from address (assuming format: "street, city, state zip")
          const addressParts = address.split(',');
          if (addressParts.length >= 2) {
            // Try with just city name
            const cityPart = addressParts[1].trim().split(' ')[0]; // Get just the city name
            query = encodeURIComponent(`${cityPart}, Massachusetts, USA`);
            response = await fetch(
              `https://nominatim.openstreetmap.org/search?format=json&q=${query}&limit=1`
            );
            data = await response.json();
          }
        }

        if (data && data.length > 0) {
          const { lat, lon } = data[0];
          const latLng = [parseFloat(lat), parseFloat(lon)];

          // Create new marker
          const marker = L.marker(latLng).addTo(mapInstanceRef.current);

          // Add popup with district info
          marker.bindPopup(`
            <div style="padding: 8px;">
              <h3 style="margin: 0 0 8px 0; font-size: 16px;">${districtName}</h3>
              <p style="margin: 0; font-size: 14px; color: #666;">${address}</p>
            </div>
          `).openPopup();

          // Only pan/zoom to marker if no boundary is highlighted
          if (!geoJsonLayerRef.current) {
            mapInstanceRef.current.setView(latLng, 12, {
              animate: true,
              duration: 0.5,
            });
          }
          markerRef.current = marker;
        } else {
          console.warn('Geocoding failed: No results found for', address);
        }
      } catch (error) {
        console.error('Geocoding error:', error);
      }
    };

    geocodeAddress();
  }, [address, districtName]);

  return (
    <div className="map-container">
      <div ref={mapRef} className="map-view" />
      {!address && (
        <div className="map-overlay">
          <p>Select a district to view its location on the map</p>
        </div>
      )}
    </div>
  );
};

export default DistrictMap;
