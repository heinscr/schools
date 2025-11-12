import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as d3 from 'd3';
import api from '../services/api';
import { normalizeTownName } from '../utils/formatters';
import { sortDistrictInfosByType } from '../utils/sortDistricts';
import { logger } from '../utils/logger';
import { useDataCache } from '../hooks/useDataCache';
import './ChoroplethMap.css';

const ChoroplethMap = ({ selectedDistrict, clickedTown, onTownClick, districtTypeOptions }) => {
  // Data cache for districts
  const cache = useDataCache();
  const isDistrictsLoading = cache.status === 'loading' || cache.status === 'idle';

  // Detect mobile devices
  const [isMobile, setIsMobile] = useState(false);

  // Zoom state: 1x to 4x, increments of 0.25
  const [zoom, setZoom] = useState(1);
  // Pan state: x/y offset in SVG coordinates
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panRef = useRef(pan);
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, origX: 0, origY: 0, hasMoved: false });
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

  // Re-render when loading status changes
  useEffect(() => {
    // Force re-render by triggering dimensions update
    if (containerRef.current) {
      setDimensions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight
      });
    }
  }, [isDistrictsLoading]);

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

  // Load GeoJSON data from cache
  useEffect(() => {
    const loadGeoData = async () => {
      try {
        // Try to get from cache first
        let geojsonData = cache.getMunicipalitiesGeojson();

        // If not in cache, load it
        if (!geojsonData) {
          await cache.loadMunicipalitiesGeojson();
          geojsonData = cache.getMunicipalitiesGeojson();
        }

        logger.log('Loaded GeoJSON:', geojsonData);
        logger.log('Number of features:', geojsonData?.features?.length);
        setGeojson(geojsonData);
      } catch (err) {
        logger.error('Error loading GeoJSON:', err);
      }
    };

    loadGeoData();
  }, [cache]);

  // Update panRef when pan changes
  useEffect(() => { panRef.current = pan; }, [pan]);

  // Memoize selected towns set to avoid recalculation on every render
  const selectedTowns = useMemo(() => {
    const towns = new Set();
    if (selectedDistrict) {
      const districtTowns = selectedDistrict.members || selectedDistrict.towns || [];
      districtTowns.forEach(t => towns.add(normalizeTownName(t)));
    }
    return towns;
  }, [selectedDistrict]);

  // Memoize normalized clicked town
  const normalizedClickedTown = useMemo(() => {
    return normalizeTownName(clickedTown);
  }, [clickedTown]);

  // Memoize town click handler
  const handleTownClickCallback = useCallback((townName) => {
    if (onTownClick) {
      onTownClick(townName);
    }
  }, [onTownClick]);

  // Remove initialPan/reset logic

  // Main render effect
  useEffect(() => {
    if (!geojson || !containerRef.current) {
      logger.log('Not rendering - geojson:', !!geojson, 'features:', geojson?.features?.length);
      return;
    }

    if (!geojson.features || geojson.features.length === 0) {
      logger.error('GeoJSON has no features!', geojson);
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
          dragRef.current.hasMoved = false;
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
            // Track if we've moved more than a small threshold (5px)
            if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
              dragRef.current.hasMoved = true;
            }
            // Move by dx/dy scaled to SVG units
            setPan({
              x: dragRef.current.origX - dx * (zoom),
              y: dragRef.current.origY - dy * (zoom)
            });
          }
        })
        .on('mouseup', function() {
          dragRef.current.dragging = false;
          // Reset hasMoved after a short delay to allow click event to check it
          setTimeout(() => {
            dragRef.current.hasMoved = false;
          }, 10);
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
        const townName = normalizeTownName(props.TOWN || props.NAME || props.TOWN_NAME);

        // If districts are still loading, show dimmed colors
        if (isDistrictsLoading) {
          return '#d0d0d0'; // Light gray for all towns when loading
        }

        // Clicked town takes precedence with orange/amber color
        if (normalizedClickedTown && townName === normalizedClickedTown) {
          return '#ff7f00'; // Orange color for clicked town
        }

        // Then check if part of selected district (purple)
        const isSelected = selectedTowns.has(townName);
        return isSelected ? '#7a0177' : '#e7e7e7';
      })
      .on('mouseover', function(event, d) {
        // Skip hover interactions if districts are still loading
        if (isDistrictsLoading) return;
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
        hoverTimerRef.current = setTimeout(() => {
          // Fetch districts for this town from cache
          let districts = [];
          try {
            const cachedDistricts = cache.getDistrictsByTown(townName);
            const districtInfos = cachedDistricts.map(d => ({ name: d.name, type: d.district_type }));
            // Sort by custom type order, then name
            districts = sortDistrictInfosByType(districtInfos);
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
            // Build DOM safely to prevent XSS
            tooltip.style('opacity', 1);
            tooltip.selectAll('*').remove(); // Clear previous content

            // Add town name
            const townSpan = tooltip.append('span');
            if (boldTown) {
              townSpan.attr('class', 'town-highlight');
            }
            townSpan.text(townName);

            tooltip.append('br');

            // Add districts list
            if (districts.length > 0) {
              const ul = tooltip.append('ul')
                .style('margin', '4px 0 0 12px')
                .style('padding', '0')
                .style('list-style', 'none');

              districts.forEach(d => {
                const li = ul.append('li');
                const typeOpt = districtTypeOptions?.find(opt => opt.value === d.type);
                const icon = typeOpt?.icon || '';

                if (icon) {
                  li.append('span')
                    .style('font-size', '1.1em')
                    .style('vertical-align', 'middle')
                    .style('margin-right', '4px')
                    .text(icon);
                }

                const labelSpan = li.append('span');
                if (boldDistrict === d.name) {
                  labelSpan.style('font-weight', 'bold');
                }
                labelSpan.text(d.name);
              });
            } else {
              tooltip.append('span').text('No districts found');
            }
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
        // Skip if districts are loading
        if (isDistrictsLoading) return;
        
        // Remove highlight
        d3.select(this)
          .attr('stroke-width', 0.5)
          .attr('stroke', '#ffffff');

        // Hide tooltip
        tooltip.style('opacity', 0);
      })
      .on('click', function(event, d) {
        // Skip if districts are loading
        if (isDistrictsLoading) return;
        
        // Only handle click if not dragging (prevents clicks during pan)
        if (dragRef.current.hasMoved) {
          return;
        }
        if (!isMobile && onTownClick) {
          event.stopPropagation();
          const props = d.properties;
          const townName = props.TOWN || props.NAME || props.TOWN_NAME || 'Unknown';
          handleTownClickCallback(townName);
        }
      });

    }, [geojson, selectedTowns, normalizedClickedTown, handleTownClickCallback, zoom, dimensions, pan, isMobile, cache, districtTypeOptions, onTownClick, isDistrictsLoading]);

  // Zoom controls - memoize to prevent recreation on every render
  const handleZoomIn = useCallback(() => {
    setZoom(z => Math.min(4, Math.round((z + 0.25) * 100) / 100));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom(z => {
      const newZoom = Math.max(1, Math.round((z - 0.25) * 100) / 100);
      // Reset pan when zooming back to 1x
      if (newZoom === 1) {
        setPan({ x: 0, y: 0 });
      }
      return newZoom;
    });
  }, []);

  const handleReset = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  return (
    <div ref={containerRef} className="choropleth-container" style={{ position: 'relative' }}>
      {isDistrictsLoading && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'rgba(255, 255, 255, 0.95)',
          padding: '20px 30px',
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          zIndex: 1000,
          fontSize: '1.1em',
          fontWeight: 500,
          color: '#333',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          pointerEvents: 'none'
        }}>
          <div style={{
            width: '20px',
            height: '20px',
            border: '3px solid #e0e0e0',
            borderTop: '3px solid #7a0177',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite'
          }}></div>
          Loading districts...
        </div>
      )}
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