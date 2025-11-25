import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { formatCurrency } from '../utils/formatters';
import { logger } from '../utils/logger';
import { useDataCache } from '../hooks/useDataCache';

const SalaryComparisonMap = ({
  results = [],
  onTownSelectionChange = null,
  selectedTowns = new Set(),
  hasResults = false,
  lastSearchTime = null
}) => {
  const containerRef = useRef(null);
  const cache = useDataCache();
  const [geoData, setGeoData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [selectionMode, setSelectionMode] = useState(true);
  const [isDragging, setIsDragging] = useState(false);

  // Load geo data from cache
  useEffect(() => {
    const loadGeoData = async () => {
      try {
        // Try to get from cache first
        let geoJsonData = cache.getMunicipalitiesGeojson();

        // If not in cache, load it
        if (!geoJsonData) {
          await cache.loadMunicipalitiesGeojson();
          geoJsonData = cache.getMunicipalitiesGeojson();
        }

        setGeoData(geoJsonData);
        setLoading(false);
      } catch (error) {
        logger.error('Error loading geo data:', error);
        setLoading(false);
      }
    };

    loadGeoData();
  }, [cache]);

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

  // Helper functions for town selection
  const toggleTownSelection = (townName) => {
    if (!onTownSelectionChange) return;

    const normalizedTown = townName.toLowerCase().trim();
    const newSelection = new Set(selectedTowns);

    if (newSelection.has(normalizedTown)) {
      newSelection.delete(normalizedTown);
    } else {
      newSelection.add(normalizedTown);
    }

    onTownSelectionChange(newSelection);
  };

  const addTownToSelection = (townName) => {
    if (!onTownSelectionChange) return;

    const normalizedTown = townName.toLowerCase().trim();
    if (!selectedTowns.has(normalizedTown)) {
      const newSelection = new Set(selectedTowns);
      newSelection.add(normalizedTown);
      onTownSelectionChange(newSelection);
    }
  };

  const clearAllSelections = () => {
    if (onTownSelectionChange) {
      onTownSelectionChange(new Set());
    }
  };

  const toggleSelectionMode = () => {
    setSelectionMode(prev => !prev);
  };

  // Handle global mouseup to stop dragging
  useEffect(() => {
    const handleMouseUp = () => {
      if (isDragging) {
        setIsDragging(false);
      }
    };

    window.addEventListener('mouseup', handleMouseUp);
    return () => window.removeEventListener('mouseup', handleMouseUp);
  }, [isDragging]);

  // Auto-exit selection mode when a new search is executed
  useEffect(() => {
    if (lastSearchTime !== null) {
      setSelectionMode(false);
    }
  }, [lastSearchTime]);

  // Render map
  useEffect(() => {
    // Ensure container exists
    if (!containerRef.current) return;

    // Always clear any existing SVG and tooltip before re-rendering
    d3.select(containerRef.current).select('svg').remove();
    d3.select('.map-tooltip').remove();

    // Early return if required data is missing or invalid
    if (!geoData || !geoData.features) {
      return;
    }

    // Ensure we have valid dimensions before creating projection
    if (!dimensions.width || !dimensions.height || dimensions.width < 10 || dimensions.height < 10) {
      return;
    }

    // Use zoom level to match DistrictBrowser - higher zoom = more zoomed in
    const zoom = 1.0;
    const zoomedWidth = (dimensions.width - 10) / zoom;
    const zoomedHeight = (dimensions.height - 10) / zoom;

    // Create SVG with viewBox for consistent zoom behavior
    const svg = d3.select(containerRef.current)
      .append('svg')
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('viewBox', `0 0 ${zoomedWidth} ${zoomedHeight}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .style('background-color', '#ffffff')
      .style('border', '1px solid #ccc');

    // Use geoIdentity projection for proper display of local GeoJSON data
    const baseWidth = dimensions.width - 10;
    const baseHeight = dimensions.height - 10;
    const projection = d3.geoIdentity()
      .fitSize([baseWidth, baseHeight], geoData);

    // Adjust translate to center with minimal padding
    const [tx, ty] = projection.translate();
    projection.translate([tx + 5, ty + 5]);

    const path = d3.geoPath().projection(projection);

    // Build district to towns mapping from results (safe if results is not an array)
    const safeResults = Array.isArray(results) ? results : [];
    const districtToTowns = {};
    safeResults.forEach(result => {
      if (result && result.district_id) {
        districtToTowns[result.district_id] = result.towns || [];
      }
    });

    // Build town to salary rank mapping (for coloring)
    const townToRank = {};
    safeResults.forEach((result, index) => {
      if (!result) return;
      const towns = result.towns || [];
      if (Array.isArray(towns)) {
        towns.forEach(town => {
          if (town && typeof town === 'string') {
            const townKey = town.toLowerCase().trim();
            // Store the rank (1-based) and total count for gradient calculation
            if (!townToRank[townKey]) {
              townToRank[townKey] = {
                rank: index + 1,
                total: safeResults.length,
                salary: result.salary,
                districtName: result.district_name
              };
            }
          }
        });
      }
    });

    // Color scale: red (low salary) to green (high salary)
    const getColorForRank = (rank, total) => {
      if (total === 1) {
        return '#10b981'; // Green for single result
      }
      
      // Normalize rank to 0-1 (1 = best/highest salary, total = worst/lowest salary)
      // Invert so best is 1 and worst is 0
      const normalized = 1 - ((rank - 1) / (total - 1));
      
      // Red to Yellow to Green gradient
      if (normalized >= 0.5) {
        // Green to Yellow (top half)
        const t = (normalized - 0.5) * 2; // 0 to 1
        return d3.interpolateRgb('#fbbf24', '#10b981')(t);
      } else {
        // Red to Yellow (bottom half)
        const t = normalized * 2; // 0 to 1
        return d3.interpolateRgb('#ef4444', '#fbbf24')(t);
      }
    };

    // Draw towns
    svg.append('g')
      .selectAll('path')
      .data(geoData.features || [])
      .enter()
      .append('path')
      .attr('d', path)
      .attr('class', 'town')
      .attr('fill', d => {
        const townName = d.properties?.TOWN?.toLowerCase().trim();

        // In selection mode, show purple for selected towns
        if (selectionMode && townName) {
          return selectedTowns.has(townName) ? '#a855f7' : '#e7e7e7';
        }

        // Otherwise, show ranking colors for towns with results
        if (townName && townToRank[townName]) {
          const { rank, total } = townToRank[townName];
          return getColorForRank(rank, total);
        }

        return '#e7e7e7'; // Default light gray for towns not in results
      })
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 0.5)
      .style('cursor', selectionMode ? 'crosshair' : 'pointer')
      .on('click', function(event, d) {
        // Only handle clicks in selection mode
        if (selectionMode) {
          const townName = d.properties?.TOWN;
          if (townName) {
            toggleTownSelection(townName);
          }
        }
      })
      .on('mousedown', function(event, d) {
        // Start drag selection in selection mode
        if (selectionMode) {
          setIsDragging(true);
          const townName = d.properties?.TOWN;
          if (townName) {
            addTownToSelection(townName);
          }
        }
      })
      .on('mouseover', function(event, d) {
        const townName = d.properties?.TOWN?.toLowerCase().trim();
        const displayTownName = d.properties?.TOWN;

        // Handle paint brush selection during drag
        if (isDragging && selectionMode && townName) {
          addTownToSelection(displayTownName);
        }

        // Highlight town border
        d3.select(this)
          .attr('stroke', '#333')
          .attr('stroke-width', 2);

        // Show tooltip based on mode
        if (selectionMode && displayTownName) {
          // Show tooltip in selection mode
          // Get districts for this town from cache
          const allDistricts = cache?.getAllDistricts() || [];
          const districtsInTown = allDistricts.filter(district =>
            district.towns && Array.isArray(district.towns) &&
            district.towns.some(t => t.toLowerCase().trim() === townName)
          );

          let tooltipContent = `<strong>${displayTownName}</strong>`;

          if (districtsInTown.length > 0) {
            tooltipContent += '<br/><br/><span style="font-size: 12px; color: #ccc;">Districts:</span><br/>';
            tooltipContent += districtsInTown
              .slice(0, 5)  // Limit to first 5 districts
              .map(d => `<span style="font-size: 12px;">${d.name}</span>`)
              .join('<br/>');
            if (districtsInTown.length > 5) {
              tooltipContent += `<br/><span style="font-size: 12px; color: #ccc;">+${districtsInTown.length - 5} more</span>`;
            }
          }

          const tooltip = d3.select('body')
            .append('div')
            .attr('class', 'map-tooltip')
            .style('position', 'absolute')
            .style('background', 'rgba(0, 0, 0, 0.8)')
            .style('color', 'white')
            .style('padding', '8px 12px')
            .style('border-radius', '4px')
            .style('font-size', '14px')
            .style('pointer-events', 'none')
            .style('z-index', '1000')
            .html(tooltipContent);

          tooltip
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 10) + 'px');
        } else if (!selectionMode && townName && townToRank[townName]) {
          // Show ranking tooltip when not in selection mode
          const info = townToRank[townName];
          const tooltip = d3.select('body')
            .append('div')
            .attr('class', 'map-tooltip')
            .style('position', 'absolute')
            .style('background', 'rgba(0, 0, 0, 0.8)')
            .style('color', 'white')
            .style('padding', '8px 12px')
            .style('border-radius', '4px')
            .style('font-size', '14px')
            .style('pointer-events', 'none')
            .style('z-index', '1000')
            .html(`
              <strong>${displayTownName || 'Unknown'}</strong><br/>
              ${info.districtName}<br/>
              Rank: #${info.rank} of ${info.total}<br/>
              Salary: ${formatCurrency(info.salary)}
            `);

          tooltip
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 10) + 'px');
        }
      })
      .on('mouseout', function() {
        d3.select(this)
          .attr('stroke', '#ffffff')
          .attr('stroke-width', 0.5);

        // Remove tooltip
        d3.select('.map-tooltip').remove();
      })
      .on('mousemove', function(event) {
        d3.select('.map-tooltip')
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 10) + 'px');
      });

  }, [geoData, dimensions, results, selectionMode, selectedTowns, hasResults, isDragging, cache]);

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        background: '#f8f9fa'
      }}
    >
      {/* Selection Mode Controls */}
      <div style={{
        position: 'absolute',
        top: '20px',
        right: '20px',
        display: 'flex',
        gap: '8px',
        zIndex: 10
      }}>
        <button
          onClick={toggleSelectionMode}
          style={{
            background: selectionMode ? '#a855f7' : '#ffffff',
            color: selectionMode ? '#ffffff' : '#333333',
            border: '1px solid #d1d5db',
            padding: '8px 16px',
            borderRadius: '6px',
            fontSize: '13px',
            fontWeight: '500',
            cursor: 'pointer',
            boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
            transition: 'all 0.2s'
          }}
          title={selectionMode ? 'Exit Selection Mode' : 'Enter Selection Mode'}
        >
          {selectionMode ? '✓ Selection Mode' : 'Selection Mode'}
        </button>
        {selectedTowns.size > 0 && (
          <button
            onClick={clearAllSelections}
            style={{
              background: '#ffffff',
              color: '#dc2626',
              border: '1px solid #d1d5db',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: '500',
              cursor: 'pointer',
              boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
              transition: 'all 0.2s'
            }}
            title="Clear all selected towns"
          >
            Clear All ({selectedTowns.size})
          </button>
        )}
      </div>

      {/* Legend only when results present */}
      {results && Array.isArray(results) && results.length > 0 && (
        <div style={{
          position: 'absolute',
          bottom: '20px',
          left: '20px',
          background: 'rgba(255, 255, 255, 0.95)',
          padding: '12px 16px',
          borderRadius: '8px',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
          zIndex: 10
        }}>
          <div style={{ fontSize: '12px', fontWeight: '600', marginBottom: '8px', color: '#4a5568', textAlign: 'center' }}>
            Salary Ranking
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ fontSize: '11px', color: '#666', display: 'flex'}}>
              <span>Lowest</span>
            </div>
            <div style={{
              width: '120px',
              height: '20px',
              background: 'linear-gradient(to right, #ef4444, #fbbf24, #10b981)',
              borderRadius: '4px',
              border: '1px solid #e0e0e0'
            }}></div>
            <div style={{ fontSize: '11px', color: '#666', display: 'flex'}}>
              <span>Highest</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SalaryComparisonMap;