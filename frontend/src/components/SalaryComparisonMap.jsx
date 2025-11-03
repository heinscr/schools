import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import * as topojson from 'topojson-client';
import './ChoroplethMap.css';

const SalaryComparisonMap = ({ results }) => {
  const containerRef = useRef(null);
  const [geojson, setGeojson] = useState(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Load GeoJSON on mount
  useEffect(() => {
    fetch('/geojson.json')
      .then(res => res.json())
      .then(data => {
        // Check if data has a content wrapper
        const topoData = data.content || data;

        // Check if it's TopoJSON format
        if (topoData.type === 'Topology') {
          // Convert TopoJSON to GeoJSON
          const objectKey = Object.keys(topoData.objects)[0];
          const geojsonData = topojson.feature(topoData, topoData.objects[objectKey]);
          setGeojson(geojsonData);
        } else if (data.type === 'FeatureCollection') {
          // Already GeoJSON
          setGeojson(data);
        } else {
          console.error('Unknown data format:', data);
        }
      })
      .catch(err => console.error('Error loading geojson:', err));
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

  // Render map
  useEffect(() => {
    // Early return if required data is missing or invalid
    if (!geojson || !geojson.features || !Array.isArray(results) || results.length === 0) {
      return;
    }

    // Ensure we have valid dimensions before creating projection
    if (!dimensions.width || !dimensions.height || dimensions.width < 10 || dimensions.height < 10) {
      return;
    }

    // Clear existing SVG
    d3.select(containerRef.current).select('svg').remove();

    // Create SVG
    const svg = d3.select(containerRef.current)
      .append('svg')
      .attr('width', dimensions.width)
      .attr('height', dimensions.height)
      .style('background-color', '#ffffff')
      .style('border', '1px solid #ccc');

    // Use geoIdentity projection for proper display of local GeoJSON data
    const baseWidth = dimensions.width - 10;
    const baseHeight = dimensions.height - 10;
    const projection = d3.geoIdentity()
      .fitSize([baseWidth, baseHeight], geojson);

    // Adjust translate to center with minimal padding
    const [tx, ty] = projection.translate();
    projection.translate([tx + 5, ty + 5]);

    const path = d3.geoPath().projection(projection);

    // Build district to towns mapping from results
    const districtToTowns = {};
    results.forEach(result => {
      if (result && result.district_id) {
        districtToTowns[result.district_id] = result.towns || [];
      }
    });

    // Build town to salary rank mapping (for coloring)
    const townToRank = {};
    results.forEach((result, index) => {
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
                total: results.length,
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
      .data(geojson.features || [])
      .enter()
      .append('path')
      .attr('d', path)
      .attr('class', 'town')
      .attr('fill', d => {
        const townName = d.properties?.TOWN?.toLowerCase().trim();
        if (townName && townToRank[townName]) {
          const { rank, total } = townToRank[townName];
          return getColorForRank(rank, total);
        }
        return '#e7e7e7'; // Default light gray for towns not in results
      })
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 0.5)
      .style('cursor', 'pointer')
      .on('mouseover', function(event, d) {
        const townName = d.properties?.TOWN?.toLowerCase().trim();
        if (townName && townToRank[townName]) {
          d3.select(this)
            .attr('stroke', '#333')
            .attr('stroke-width', 2);
          
          // Show tooltip
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
              <strong>${d.properties?.TOWN || 'Unknown'}</strong><br/>
              ${info.districtName}<br/>
              Rank: #${info.rank} of ${info.total}<br/>
              Salary: $${Number(info.salary).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
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

  }, [geojson, dimensions, results]);

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
      {(!results || !Array.isArray(results) || results.length === 0) && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          color: '#999',
          fontSize: '16px',
          textAlign: 'center'
        }}>
          Search for salaries to see districts on the map
        </div>
      )}
      
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
          <div style={{ fontSize: '12px', fontWeight: '600', marginBottom: '8px', color: '#4a5568' }}>
            Salary Ranking
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{
              width: '120px',
              height: '20px',
              background: 'linear-gradient(to right, #ef4444, #fbbf24, #10b981)',
              borderRadius: '4px',
              border: '1px solid #e0e0e0'
            }}></div>
            <div style={{ fontSize: '11px', color: '#666', display: 'flex', justifyContent: 'space-between', width: '120px' }}>
              <span>Lowest</span>
              <span>Highest</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SalaryComparisonMap;
