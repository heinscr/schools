import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import * as topojson from 'topojson-client';
import api from '../services/api';
import './ChoroplethMap.css';

const ChoroplethMap = ({ selectedDistrict, clickedTown, onTownClick }) => {
  // Debounce timer for hover
  const hoverTimerRef = useRef(null);
  const containerRef = useRef(null);
  const tooltipRef = useRef(null);
  const [geojson, setGeojson] = useState(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoverDistricts, setHoverDistricts] = useState([]);
  const activeHoverTownRef = useRef(null);

  // Handle window resize
  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Hide tooltip when mouse leaves the map container
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const handleMouseLeave = () => {
      d3.select(tooltipRef.current).style('opacity', 0);
      activeHoverTownRef.current = null;
    };
    container.addEventListener('mouseleave', handleMouseLeave);
    return () => container.removeEventListener('mouseleave', handleMouseLeave);
  }, []);

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
    const width = dimensions.width || container.clientWidth;
    const height = dimensions.height || container.clientHeight;

    // Clear previous render
    d3.select(container).select('svg').remove();

    // Create SVG
    const svg = d3.select(container)
      .append('svg')
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
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

    // Normalize clicked town name
    const normalizedClickedTown = clickedTown ? clickedTown.trim().toLowerCase() : null;

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

        // Clicked town takes precedence with orange/amber color
        if (normalizedClickedTown && townName === normalizedClickedTown) {
          return '#ff7f00'; // Orange color for clicked town
        }

        // Then check if part of selected district (purple)
        const isSelected = selectedTowns.has(townName);
        return isSelected ? '#7a0177' : '#e7e7e7';
      })
      .on('mouseover', function(event, d) {
        const props = d.properties;
        const townName = props.TOWN || props.NAME || props.TOWN_NAME || 'Unknown';

        // Track the currently hovered town
        activeHoverTownRef.current = townName;

        // Highlight on hover
        d3.select(this)
          .attr('stroke-width', 2)
          .attr('stroke', '#333');

        // Debounce: clear previous timer
        if (hoverTimerRef.current) {
          clearTimeout(hoverTimerRef.current);
        }
        // Start new timer
        hoverTimerRef.current = setTimeout(async () => {
          // Fetch districts for this town (cached)
          let districts = [];
          try {
            const response = await api.getDistricts({ town: townName });
            districts = response.data.map(d => d.name).sort((a, b) => a.localeCompare(b));
          } catch (err) {
            districts = [];
          }
          // Only update UI if still hovering this town
          if (activeHoverTownRef.current === townName) {
            setHoverDistricts(districts);
            // Determine which item to bold
            let boldTown = false;
            let boldDistrict = null;
            if (clickedTown && townName === clickedTown) {
              boldTown = true;
            } else if (selectedDistrict && districts.includes(selectedDistrict.name)) {
              boldDistrict = selectedDistrict.name;
            }
            // Show tooltip as bullet list
            tooltip
              .style('opacity', 1)
              .style('left', `${event.pageX + 10}px`)
              .style('top', `${event.pageY - 10}px`)
              .html(
                (boldTown
                  ? `<span class="town-highlight">${townName}</span>`
                  : `${townName}`
                ) + '<br/>' +
                (districts.length > 0
                  ? `<ul style='margin: 4px 0 0 12px; padding: 0;'>${districts.map(d => boldDistrict === d ? `<li><strong>${d}</strong></li>` : `<li>${d}</li>`).join('')}</ul>`
                  : `<span>No districts found</span>`)
              );
          }
        }, 50); // 50ms debounce
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
      })
      .on('click', function(event, d) {
        if (onTownClick) {
          event.stopPropagation();
          const props = d.properties;
          const townName = props.TOWN || props.NAME || props.TOWN_NAME || 'Unknown';
          onTownClick(townName);
        }
      });

  }, [geojson, selectedDistrict, clickedTown, onTownClick]);

  return (
    <div ref={containerRef} className="choropleth-container">
      <div ref={tooltipRef} className="choropleth-tooltip"></div>
    </div>
  );
};

export default ChoroplethMap;
