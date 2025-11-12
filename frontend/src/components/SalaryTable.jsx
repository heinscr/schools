import { useState, useEffect, useContext } from 'react';
import api from '../services/api';
import { formatCurrency } from '../utils/formatters';
import { logger } from '../utils/logger';
import './SalaryTable.css';
import { DataCacheContext } from '../contexts/DataCacheContext';

function SalaryTable({ districtId, highlight = null }) {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [globalMaxStep, setGlobalMaxStep] = useState(15);

  // Compute reserved height for the table area (header + rows)
  const reservedHeight = 56 + (globalMaxStep * 44);

  useEffect(() => {
    if (!districtId) {
      setSchedules([]);
      return;
    }

    const fetchSalaries = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getSalarySchedules(districtId);
        logger.log('Salary data received:', data);
        logger.log('First schedule:', data[0]);
        setSchedules(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchSalaries();
  }, [districtId]);

  // Fetch global salary metadata (max_step) to calculate reserved table height
  useEffect(() => {
    let mounted = true;
    const loadMeta = async () => {
      try {
        const meta = await api.getGlobalSalaryMetadata();
        if (!mounted) return;
        if (meta && Number.isFinite(Number(meta.max_step))) {
          setGlobalMaxStep(Number(meta.max_step));
        }
      } catch (e) {
        // ignore — keep default
      }
    };
    loadMeta();
    return () => { mounted = false; };
  }, []);

  if (!districtId) {
    return null;
  }

  const { getDistrictById } = useContext(DataCacheContext);

  if (loading) {
    // Show the same header as the final table (prefer cached district name) to avoid layout jump
    const d = getDistrictById ? getDistrictById(districtId) : null;
    const headerName = (d && (d.name || d.district_name)) || districtId;
      return (
        <div className="salary-tables">
          <div className="salary-schedule">
            <h3>{headerName}</h3>
            <div className="salary-table-wrapper" style={{ minHeight: `${reservedHeight}px` }}>
              <table className="salary-table">
                <thead>
                  <tr>
                    <th>Step</th>
                    {[...Array(5)].map((_, i) => <th key={i}>—</th>)}
                  </tr>
                </thead>
                <tbody>
                  {[...Array(globalMaxStep)].map((_, r) => (
                    <tr key={r}>
                      <td className="step-cell skeleton-cell">&nbsp;</td>
                      {[...Array(5)].map((__, c) => <td key={c} className="skeleton-cell">&nbsp;</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
    );
  }

  if (error) {
    return <div className="salary-error">Error: {error}</div>;
  }

  if (schedules.length === 0) {
    const d = getDistrictById ? getDistrictById(districtId) : null;
    const headerName = (d && (d.name || d.district_name)) || districtId;
    return (
      <div className="salary-tables">
        <div className="salary-schedule">
          <h3>{headerName}</h3>
          <div className="salary-table-wrapper" style={{ minHeight: `${reservedHeight}px` }}>
            <table className="salary-table">
              <thead>
                <tr>
                  <th>Step</th>
                  {[...Array(5)].map((_, i) => <th key={i}>—</th>)}
                </tr>
              </thead>
              <tbody>
                {[...Array(globalMaxStep)].map((_, r) => (
                  <tr key={r}>
                    <td className="step-cell skeleton-cell">&nbsp;</td>
                    {[...Array(5)].map((__, c) => <td key={c} className="skeleton-cell">&nbsp;</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // Sort schedules: newest school_year first, then period in inverse ASCII order
  const extractYear = (s) => {
    if (!s) return Number.NEGATIVE_INFINITY;
    const m = String(s).match(/(\d{4})/);
    return m ? parseInt(m[1], 10) : Number.NEGATIVE_INFINITY;
  };

  const sortedSchedules = [...schedules].sort((a, b) => {
    const ya = extractYear(a?.school_year);
    const yb = extractYear(b?.school_year);
    if (ya !== yb) return yb - ya; // descending year
    const pa = a?.period || '';
    const pb = b?.period || '';
    if (pa === pb) return 0;
    // inverse ASCII sort (reverse lexicographic)
    return pa < pb ? 1 : -1;
  });

  return (
    <div className="salary-tables">
  {sortedSchedules.map((schedule, idx) => {
        logger.log(`Schedule ${idx}:`, schedule);
        
  // Group salaries by step for table display
        const salariesByStep = {};
        const educationCreditsSet = new Set();
        
        (schedule.salaries || []).forEach(item => {
          const step = item.step;
          const eduCredKey = item.credits > 0 ? `${item.education}+${item.credits}` : item.education;
          
          if (!salariesByStep[step]) {
            salariesByStep[step] = {};
          }
          // Preserve salary value, whether it was calculated, and where it was calculated from
          salariesByStep[step][eduCredKey] = {
            value: item.salary,
            // support both camelCase and snake_case flags
            isCalculated: !!(item.isCalculated || item.is_calculated),
            isCalculatedFrom: item.is_calculated_from || item.isCalculatedFrom
          };
          educationCreditsSet.add(JSON.stringify({ 
            education: item.education, 
            credits: item.credits,
            key: eduCredKey
          }));
        });
        
        // Sort education/credits columns: B->M->D, then by credits
        const eduOrder = { 'B': 1, 'M': 2, 'D': 3 };
        const sortedColumns = Array.from(educationCreditsSet)
          .map(str => JSON.parse(str))
          .sort((a, b) => {
            const eduA = eduOrder[a.education] || 99;
            const eduB = eduOrder[b.education] || 99;
            if (eduA !== eduB) return eduA - eduB;
            return a.credits - b.credits;
          });
        
        // Get sorted steps
        const sortedSteps = Object.keys(salariesByStep).sort((a, b) => Number(a) - Number(b));
        
        // Filter out columns where every step is calculated (suppress fully-calculated columns)
        const visibleColumns = sortedColumns.filter(col => {
          if (sortedSteps.length === 0) return true;
          const allCalculated = sortedSteps.every(step => {
            const cellEntry = salariesByStep[step] && salariesByStep[step][col.key];
            // Only count as calculated if entry exists and is marked calculated
            return cellEntry && cellEntry.isCalculated;
          });
          return !allCalculated;
        });

        // Compute fallback highlight using is_calculated_from field
        let fallbackHighlight = null;
        let highlightMode = null; // 'exact' | 'fallback' | null
        if (highlight) {
          try {
            const targetEdKey = highlight.credits > 0 ? `${highlight.education}+${highlight.credits}` : highlight.education;
            const targetStepKey = String(highlight.step);
            const targetEntry = salariesByStep[targetStepKey] && salariesByStep[targetStepKey][targetEdKey];

            // If target cell exists and is calculated, use is_calculated_from to find the source
            if (targetEntry && targetEntry.isCalculated && targetEntry.isCalculatedFrom) {
              // is_calculated_from is an object: {education, credits, step}
              fallbackHighlight = {
                education: targetEntry.isCalculatedFrom.education,
                credits: targetEntry.isCalculatedFrom.credits,
                step: targetEntry.isCalculatedFrom.step
              };
              logger.log('highlight-fallback', { target: highlight, calculated_from: targetEntry.isCalculatedFrom, fallback: fallbackHighlight });
            }
          } catch (e) {
            // defensive: don't break rendering on unexpected issues
            console.error('Error computing fallback highlight', e);
          }
        }

        // Decide whether this schedule will use exact highlight or fallback
        if (highlight) {
          const targetVisibleCol = visibleColumns.find(c => String(c.education) === String(highlight.education) && Number(c.credits) === Number(highlight.credits));
          const targetStepKey = String(highlight.step);
          const targetEntry = targetVisibleCol ? (salariesByStep[targetStepKey] && salariesByStep[targetStepKey][targetVisibleCol.key]) : null;
          if (targetEntry && !targetEntry.isCalculated) {
            highlightMode = 'exact';
          } else if (fallbackHighlight) {
            highlightMode = 'fallback';
          } else {
            highlightMode = null;
          }
        }
        // DEBUG: surface the decision for troubleshooting
        try {
          logger.log('highlight-debug', {
            highlight,
            visibleColumns: visibleColumns.map(c => c.key),
            fallbackHighlight,
            highlightMode
          });
        } catch (e) {
          // ignore logging errors
        }
        
        return (
        <div key={idx} className="salary-schedule">
          <h3>
            {(() => {
              // Prefer the cached district name when available
              const d = getDistrictById ? getDistrictById(schedule.district_id) : null;
              return (d && (d.name || d.district_name)) || schedule.district_name || schedule.district_id;
            })()} - {schedule.school_year}
            {schedule.period && <span className="salary-period"> ({schedule.period})</span>}
            {highlightMode === 'fallback' && (
              <span className="salary-interpret-badge" role="status" aria-live="polite">
                Interpreted
              </span>
            )}
          </h3>

          {/* Reserve vertical space based on globalMaxStep so the modal doesn't jump when rows render */}
          <div className="salary-table-wrapper" style={{ minHeight: `${reservedHeight}px` }}>
            <table className="salary-table">
              <thead>
                <tr>
                  <th>Step</th>
                  {visibleColumns.map(col => (
                    <th key={col.key} title={
                      col.education === 'B' ? "Bachelor's" :
                      col.education === 'M' ? "Master's" :
                      col.education === 'D' ? "Doctorate" : col.education
                    }>
                      {col.key}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedSteps.map(step => (
                  <tr key={step}>
                    <td className="step-cell">{step}</td>
                        {visibleColumns.map(col => {
                          const cellEntry = salariesByStep[step][col.key];
                          const cellValue = cellEntry ? cellEntry.value : undefined;
                          const cellIsCalculated = cellEntry ? cellEntry.isCalculated : false;
                          // Exact match only when the target cell exists and is NOT calculated
                          const isMatch = Boolean(highlight && (
                            String(col.education) === String(highlight.education) &&
                            Number(col.credits) === Number(highlight.credits) &&
                            String(step) === String(highlight.step) &&
                            !cellIsCalculated
                          ));

                          // Fallback exact match (when exact is calculated) — compare against computed fallbackHighlight
                          const isFallbackExact = Boolean(fallbackHighlight && (
                            String(col.education) === String(fallbackHighlight.education) &&
                            Number(col.credits) === Number(fallbackHighlight.credits) &&
                            String(step) === String(fallbackHighlight.step)
                          ));

                          const finalIsMatch = isMatch || isFallbackExact;
                          const isFallback = Boolean(isFallbackExact && highlightMode === 'fallback');
                          const cellClass = `salary-cell${finalIsMatch ? ' highlight' : ''}${isFallback ? ' fallback-highlight' : ''}`;
                          return (
                            <td key={col.key} className={cellClass}>
                              {cellIsCalculated ? 'NA' : formatCurrency(cellValue)}
                            </td>
                          );
                        })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )})}
    </div>
  );
}

export default SalaryTable;