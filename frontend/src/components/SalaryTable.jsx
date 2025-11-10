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
          // Preserve salary value and whether it was calculated (some APIs use isCalculated or is_calculated)
          salariesByStep[step][eduCredKey] = {
            value: item.salary,
            // support both camelCase and snake_case flags
            isCalculated: !!(item.isCalculated || item.is_calculated)
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

        // Compute fallback highlight when the requested highlight cell is calculated
        let fallbackHighlight = null;
  let highlightMode = null; // 'exact' | 'fallback' | null
        if (highlight) {
          try {
            // Find the target column among all columns (sortedColumns) to preserve relative ordering
            const allColumns = sortedColumns;
            const targetColIndex = allColumns.findIndex(c =>
              String(c.education) === String(highlight.education) && Number(c.credits) === Number(highlight.credits)
            );

            const targetStepIndex = sortedSteps.findIndex(s => String(s) === String(highlight.step));

            if (targetColIndex !== -1 && targetStepIndex !== -1) {
              // Helper to check a cell at (colIndex, stepIndex) for non-calculated
              const findInColumnUpwards = (colIndex) => {
                const col = allColumns[colIndex];
                if (!col) return null;
                // Only consider columns that are visible (not fully-calculated)
                const visibleCol = visibleColumns.find(vc => vc.key === col.key);
                if (!visibleCol) return null;
                // Search upwards from targetStepIndex down to 0
                for (let si = targetStepIndex; si >= 0; si--) {
                  const stepKey = sortedSteps[si];
                  const entry = salariesByStep[stepKey] && salariesByStep[stepKey][visibleCol.key];
                  if (entry && !entry.isCalculated) {
                    return { education: visibleCol.education, credits: visibleCol.credits, step: stepKey };
                  }
                }
                return null;
              };

              // First check same column, then move leftwards
              for (let dc = 0; dc <= targetColIndex; dc++) {
                const colIndexToCheck = targetColIndex - dc;
                const found = findInColumnUpwards(colIndexToCheck);
                if (found) { fallbackHighlight = found; break; }
              }
            }
          } catch (e) {
            // defensive: don't break rendering on unexpected issues
            // leave fallbackHighlight as null
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
