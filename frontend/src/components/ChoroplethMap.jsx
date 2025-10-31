import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import * as topojson from 'topojson-client';
import api from '../services/api';
import './ChoroplethMap.css';

const ChoroplethMap = ({ selectedDistrict, clickedTown, onTownClick, districtTypeOptions }) => {
  // Detect mobile devices
  const [isMobile, setIsMobile] = useState(false);

  // Zoom state: 1x to 4x, increments of 0.25
  const [zoom, setZoom] = useState(1);
  // Pan state: x/y offset in SVG coordinates
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panRef = useRef(pan);
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, origX: 0, origY: 0 });
  // Debounce timer for hover
  const hoverTimerRef = useRef(null);
  const containerRef = useRef(null);
  const tooltipRef = useRef(null);
  const [geojson, setGeojson] = useState(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoverDistricts, setHoverDistricts] = useState([]);
  const activeHoverTownRef = useRef(null);

  // Detect mobile on mount
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

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

  // Update panRef when pan changes
  useEffect(() => { panRef.current = pan; }, [pan]);

  // Remove initialPan/reset logic

  // Main render effect
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

    // Clear previous render - remove ALL svgs
    d3.select(container).selectAll('svg').remove();

  // Calculate zoomed size (zoom > 1 makes map larger by reducing viewBox size)
  const zoomedWidth = (width - 10) / zoom;
  const zoomedHeight = (height - 10) / zoom;

    // Calculate pan offset
    const panX = pan.x;
    const panY = pan.y;

    // Create SVG
    const svg = d3.select(container)
      .append('svg')
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', `${panX} ${panY} ${zoomedWidth} ${zoomedHeight}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .attr('class', 'choropleth-svg');
    // Add drag/pan handlers to SVG (disabled on mobile)
    if (!isMobile) {
      svg
        .style('cursor', 'grab')
        .on('mousedown', function(event) {
          dragRef.current.dragging = true;
          dragRef.current.startX = event.clientX;
          dragRef.current.startY = event.clientY;
          dragRef.current.origX = panRef.current.x;
          dragRef.current.origY = panRef.current.y;
          d3.select(this).style('cursor', 'grabbing');
        })
        .on('mousemove', function(event) {
          if (dragRef.current.dragging) {
            const dx = event.clientX - dragRef.current.startX;
            const dy = event.clientY - dragRef.current.startY;
            // Move by dx/dy scaled to SVG units
            setPan({
              x: dragRef.current.origX - dx * (zoom),
              y: dragRef.current.origY - dy * (zoom)
            });
          }
        })
        .on('mouseup', function() {
          dragRef.current.dragging = false;
          d3.select(this).style('cursor', 'grab');
        })
        .on('mouseleave', function() {
          dragRef.current.dragging = false;
          d3.select(this).style('cursor', 'grab');
        });
    }

    // Use geoIdentity projection for proper display of local GeoJSON data
    // Always fit to the base size (not zoomed size)
    const baseWidth = width - 10;
    const baseHeight = height - 10;
    const projection = d3.geoIdentity()
      .fitSize([baseWidth, baseHeight], geojson);

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
            districts = response.data.map(d => ({ name: d.name, type: d.district_type })).sort((a, b) => a.name.localeCompare(b.name));
          } catch (err) {
            districts = [];
          }
          // Only update UI if still hovering this town
          if (activeHoverTownRef.current === townName) {
            setHoverDistricts(districts.map(d => d.name));
            // Determine which item to bold
            let boldTown = false;
            let boldDistrict = null;
            if (clickedTown && townName === clickedTown) {
              boldTown = true;
            } else if (selectedDistrict && districts.some(d => d.name === selectedDistrict.name)) {
              boldDistrict = selectedDistrict.name;
            }
            // Show tooltip as bullet list with icons
            tooltip
              .style('opacity', 1)
              .html(
                (boldTown
                  ? `<span class="town-highlight">${townName}</span>`
                  : `${townName}`
                ) + '<br/>' +
                (districts.length > 0
                  ? `<ul style='margin: 4px 0 0 12px; padding: 0; list-style: none;'>${districts.map(d => {
                      const typeOpt = districtTypeOptions?.find(opt => opt.value === d.type);
                      const icon = typeOpt?.icon || '';
                      const label = boldDistrict === d.name ? `<strong>${d.name}</strong>` : d.name;
                      return `<li>${icon ? `<span style='font-size:1.1em;vertical-align:middle;margin-right:4px;'>${icon}</span>` : ''}${label}</li>`;
                    }).join('')}</ul>`
                  : `<span>No districts found</span>`)
              );
            // Position tooltip inside map window
            setTimeout(() => {
              const tooltipNode = tooltipRef.current;
              const containerNode = containerRef.current;
              if (!tooltipNode || !containerNode) return;
              const tooltipRect = tooltipNode.getBoundingClientRect();
              const containerRect = containerNode.getBoundingClientRect();
              let left = event.pageX + 10;
              let top = event.pageY - 10;
              // Right edge
              if (left + tooltipRect.width > containerRect.right) {
                left = event.pageX - tooltipRect.width - 10;
              }
              // Bottom edge
              if (top + tooltipRect.height > containerRect.bottom) {
                top = event.pageY - tooltipRect.height - 10;
              }
              // Left edge
              if (left < containerRect.left) {
                left = containerRect.left + 10;
              }
              // Top edge
              if (top < containerRect.top) {
                top = containerRect.top + 10;
              }
              tooltip.style('left', `${left}px`).style('top', `${top}px`);
            }, 0);
          }
        }, 50); // 50ms debounce
      })
      .on('mousemove', function(event) {
        // Position tooltip inside map window
        const tooltipNode = tooltipRef.current;
        const containerNode = containerRef.current;
        if (!tooltipNode || !containerNode) return;
        const tooltipRect = tooltipNode.getBoundingClientRect();
        const containerRect = containerNode.getBoundingClientRect();
        let left = event.pageX + 10;
        let top = event.pageY - 10;
        // Right edge
        if (left + tooltipRect.width > containerRect.right) {
          left = event.pageX - tooltipRect.width - 10;
        }
        // Bottom edge
        if (top + tooltipRect.height > containerRect.bottom) {
          top = event.pageY - tooltipRect.height - 10;
        }
        // Left edge
        if (left < containerRect.left) {
          left = containerRect.left + 10;
        }
        // Top edge
        if (top < containerRect.top) {
          top = containerRect.top + 10;
        }
        tooltip.style('left', `${left}px`).style('top', `${top}px`);
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
        // Disable clicks on mobile
        if (onTownClick && !isMobile) {
          event.stopPropagation();
          const props = d.properties;
          const townName = props.TOWN || props.NAME || props.TOWN_NAME || 'Unknown';
          onTownClick(townName);
        }
      });

  }, [geojson, selectedDistrict, clickedTown, onTownClick, zoom, dimensions, pan, isMobile]);

  // Zoom controls
  const handleZoomIn = () => {
    setZoom(z => Math.min(4, Math.round((z + 0.25) * 100) / 100));
  };
  const handleZoomOut = () => {
    setZoom(z => {
      const newZoom = Math.max(1, Math.round((z - 0.25) * 100) / 100);
      // Reset pan when zooming back to 1x
      if (newZoom === 1) {
        setPan({ x: 0, y: 0 });
      }
      return newZoom;
    });
  };
  const handleReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  return (
    <div ref={containerRef} className="choropleth-container" style={{ position: 'relative' }}>
      {!isMobile && (
        <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          <button
            onClick={handleZoomIn}
            disabled={zoom >= 4}
            style={{
              fontSize: '1.5em',
              fontWeight: 'bold',
              width: 40,
              height: 40,
              borderRadius: 8,
              border: '2px solid #000',
              background: zoom < 4 ? '#fffbe6' : '#f3f3f3',
              color: '#000',
              cursor: zoom < 4 ? 'pointer' : 'not-allowed',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              transition: 'background 0.2s, color 0.2s',
              outline: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
            }}
            aria-label="Zoom in"
            title="Zoom in"
          >
            <span style={{ pointerEvents: 'none', display: 'block', width: '100%', textAlign: 'center', lineHeight: '1' }}>+</span>
          </button>
          <button
            onClick={handleZoomOut}
            disabled={zoom <= 1}
            style={{
              fontSize: '1.5em',
              fontWeight: 'bold',
              width: 40,
              height: 40,
              borderRadius: 8,
              border: '2px solid #000',
              background: zoom > 1 ? '#fffbe6' : '#f3f3f3',
              color: '#000',
              cursor: zoom > 1 ? 'pointer' : 'not-allowed',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              transition: 'background 0.2s, color 0.2s',
              outline: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
            }}
            aria-label="Zoom out"
            title="Zoom out"
          >
            <span style={{ pointerEvents: 'none', display: 'block', width: '100%', textAlign: 'center', lineHeight: '1' }}>−</span>
          </button>
          <button
            onClick={handleReset}
            disabled={zoom === 1 && pan.x === 0 && pan.y === 0}
            style={{
              fontSize: '1.2em',
              fontWeight: 'bold',
              width: 40,
              height: 40,
              borderRadius: 8,
              border: '2px solid #000',
              background: (zoom !== 1 || pan.x !== 0 || pan.y !== 0) ? '#fffbe6' : '#f3f3f3',
              color: '#000',
              cursor: (zoom !== 1 || pan.x !== 0 || pan.y !== 0) ? 'pointer' : 'not-allowed',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
              transition: 'background 0.2s, color 0.2s',
              outline: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
            }}
            aria-label="Reset zoom and pan"
            title="Reset zoom and pan"
          >
            <span style={{ pointerEvents: 'none', display: 'block', width: '100%', textAlign: 'center' }}>⟲</span>
          </button>
        </div>
        <span style={{ fontSize: '0.9em', textAlign: 'center', color: '#333', fontWeight: 500 }}>
          Zoom: {zoom.toFixed(2)}x
        </span>
      </div>
      )}
      <div ref={tooltipRef} className="choropleth-tooltip"></div>
    </div>
  );
};

export default ChoroplethMap;
