import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import * as topojson from 'topojson-client';
import './ChoroplethMap.css';

const ChoroplethMap = ({ selectedDistrict }) => {
  const containerRef = useRef(null);
  const tooltipRef = useRef(null);
  const [geojson, setGeojson] = useState(null);

  // Load GeoJSON/TopoJSON data
  useEffect(() => {
    fetch('/geojson.json')
      .then((res) => res.json())
      .then((data) => {
        // Check if data has a content wrapper
        const topoData = data.content || data;

        // Check if it's TopoJSON format
        if (topoData.type === 'Topology') {
          // Convert TopoJSON to GeoJSON
          const objectKey = Object.keys(topoData.objects)[0];
          console.log('Converting TopoJSON, object key:', objectKey);
          const geojson = topojson.feature(topoData, topoData.objects[objectKey]);
          console.log('Converted GeoJSON:', geojson);
          console.log('Number of features:', geojson.features?.length);
          setGeojson(geojson);
        } else if (data.type === 'FeatureCollection') {
          // Already GeoJSON
          console.log('Loading regular GeoJSON');
          setGeojson(data);
        } else {
          console.error('Unknown data format:', data);
        }
      })
      .catch((err) => console.error('Error loading GeoJSON:', err));
  }, []);

  // Render map
  useEffect(() => {
    if (!geojson || !containerRef.current) {
      console.log('Not rendering - geojson:', !!geojson, 'features:', geojson?.features?.length);
      return;
    }

    if (!geojson.features || geojson.features.length === 0) {
      console.error('GeoJSON has no features!', geojson);
      return;
    }

    // Get container dimensions
    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight || 500;

    // Clear previous render
    d3.select(container).select('svg').remove();

    // Create SVG
    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('class', 'choropleth-svg');

    // Use geoIdentity projection for proper display of local GeoJSON data
    // Minimal padding to zoom in more on the state
    const projection = d3.geoIdentity()
      .fitSize([width - 10, height - 10], geojson);

    // Adjust translate to center with minimal padding
    const [tx, ty] = projection.translate();
    projection.translate([tx + 5, ty + 5]);

    const path = d3.geoPath().projection(projection);

    // Get selected district towns
    const selectedTowns = new Set();
    if (selectedDistrict) {
      const towns = selectedDistrict.members || selectedDistrict.towns || [];
      towns.forEach(t => selectedTowns.add(t.trim().toLowerCase()));
    }

    // Create tooltip
    const tooltip = d3.select(tooltipRef.current);

    // Draw towns
    svg.selectAll('path.town')
      .data(geojson.features)
      .enter()
      .append('path')
      .attr('d', path)
      .attr('class', 'town')
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 0.5)
      .attr('fill', d => {
        const props = d.properties;
        const townName = (props.TOWN || props.NAME || props.TOWN_NAME || '').trim().toLowerCase();
        const isSelected = selectedTowns.has(townName);
        return isSelected ? '#7a0177' : '#e7e7e7';
      })
      .on('mouseover', function(event, d) {
        const props = d.properties;
        const townName = props.TOWN || props.NAME || props.TOWN_NAME || 'Unknown';

        // Highlight on hover
        d3.select(this)
          .attr('stroke-width', 2)
          .attr('stroke', '#333');

        // Show tooltip
        tooltip
          .style('opacity', 1)
          .style('left', `${event.pageX + 10}px`)
          .style('top', `${event.pageY - 10}px`)
          .html(`<strong>${townName}</strong>`);
      })
      .on('mousemove', function(event) {
        tooltip
          .style('left', `${event.pageX + 10}px`)
          .style('top', `${event.pageY - 10}px`);
      })
      .on('mouseout', function() {
        // Remove highlight
        d3.select(this)
          .attr('stroke-width', 0.5)
          .attr('stroke', '#ffffff');

        // Hide tooltip
        tooltip.style('opacity', 0);
      });

  }, [geojson, selectedDistrict]);

  return (
    <div ref={containerRef} className="choropleth-container">
      <div ref={tooltipRef} className="choropleth-tooltip"></div>
      {!selectedDistrict && (
        <div className="choropleth-overlay">
          <p>Select a district to view its towns on the map</p>
        </div>
      )}
    </div>
  );
};

export default ChoroplethMap;
