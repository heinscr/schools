import { useEffect, useMemo, useState } from 'react';
import api from '../services/api';
import './SalaryUploadModal.css';

// Editor behavior:
// - All cells are editable, including previously calculated ones.
// - Include all non-calculated (is_calculated=false) cells that have a non-blank value.
// - For calculated cells (is_calculated=true), include ONLY if a new non-empty value is provided.
// - Exclude all others from payload. Frontend validation enforces > 0 and up to 2 decimals.
export default function EditSalaryModal({ district, onClose, onSuccess }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [schedules, setSchedules] = useState([]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getSalarySchedules(district.id);
        if (!mounted) return;
        setSchedules(data || []);
      } catch (e) {
        if (!mounted) return;
        setError(e.message || 'Failed to load salaries');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [district.id]);

  const [inputs, setInputs] = useState({});

  // Build an index for inputs: key `${idx}|${step}|${edu}|${credits}` -> string value
  useEffect(() => {
    const next = {};
    schedules.forEach((schedule, idx) => {
      (schedule.salaries || []).forEach(item => {
        const key = `${idx}|${item.step}|${item.education}|${item.credits}`;
        // seed all cells (including previously calculated) so they are editable
        next[key] = item.salary != null ? String(item.salary) : '';
      });
    });
    setInputs(next);
  }, [schedules]);

  const setCell = (idx, step, education, credits, value) => {
    const key = `${idx}|${step}|${education}|${credits}`;
    setInputs(prev => ({ ...prev, [key]: value }));
  };

  const validateAndBuildRecords = () => {
    const records = [];
    const errors = [];

    schedules.forEach((schedule, idx) => {
      // lookup of calc flags and original salaries for change detection
      const calcMap = new Map();
      const origMap = new Map();
      (schedule.salaries || []).forEach(item => {
        const key = `${item.step}|${item.education}|${item.credits}`;
        calcMap.set(key, Boolean(item.isCalculated || item.is_calculated));
        origMap.set(key, item.salary);
      });

      // Determine present steps and columns from existing data only
      const steps = Array.from(new Set((schedule.salaries || []).map(s => s.step))).sort((a,b)=>a-b);
      const cols = Array.from(new Set((schedule.salaries || []).map(s => `${s.education}|${s.credits}`)));

      for (const step of steps) {
        for (const col of cols) {
          const [education, creditsStr] = col.split('|');
          const credits = Number(creditsStr);
          const key = `${idx}|${step}|${education}|${credits}`;
          const raw = (inputs[key] ?? '').trim();
          const cellKey = `${step}|${education}|${credits}`;
          const isCalculated = calcMap.get(cellKey) === true;
          if (isCalculated) {
            // For calculated cells: include ONLY if user provided a new non-empty value
            if (raw === '') {
              continue; // exclude calculated cells without new value
            }
            // Skip if unchanged (numeric comparison, rounded to 2 decimals)
            const orig = origMap.get(cellKey);
            if (orig != null) {
              const newNum = Math.round(Number(raw) * 100) / 100;
              const origNum = Math.round(Number(orig) * 100) / 100;
              if (origNum === newNum) {
                continue; // unchanged calculated cell
              }
            }
            if (!/^\d+(?:\.\d{1,2})?$/.test(raw)) {
              errors.push(`Invalid amount at ${schedule.school_year} ${schedule.period || ''} step ${step} ${education}${credits>0?`+${credits}`:''}`);
              continue;
            }
            const amount = Number(raw);
            if (!(amount > 0)) {
              errors.push(`Salary must be > 0 at ${schedule.school_year} ${schedule.period || ''} step ${step} ${education}${credits>0?`+${credits}`:''}`);
              continue;
            }
            records.push({
              school_year: schedule.school_year,
              period: schedule.period || 'regular',
              education,
              credits,
              step: Number(step),
              salary: Math.round(amount * 100) / 100,
            });
          } else {
            // Non-calculated cells: include only if user provided a non-blank value.
            if (raw === '') {
              continue; // skip blanks
            }
            if (!/^\d+(?:\.\d{1,2})?$/.test(raw)) {
              errors.push(`Invalid amount at ${schedule.school_year} ${schedule.period || ''} step ${step} ${education}${credits>0?`+${credits}`:''}`);
              continue;
            }
            const amount = Number(raw);
            if (!(amount > 0)) {
              errors.push(`Salary must be > 0 at ${schedule.school_year} ${schedule.period || ''} step ${step} ${education}${credits>0?`+${credits}`:''}`);
              continue;
            }
            records.push({
              school_year: schedule.school_year,
              period: schedule.period || 'regular',
              education,
              credits,
              step: Number(step),
              salary: Math.round(amount * 100) / 100,
            });
          }
        }
      }
    });

    return { records, errors };
  };

  const handleApply = async () => {
    const { records, errors } = validateAndBuildRecords();
    if (errors.length) {
      setError(errors[0]);
      return;
    }
    if (records.length === 0) {
      setError('No editable values provided.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await api.manualApplySalaryRecords(district.id, records);
      onSuccess && onSuccess(result);
    } catch (e) {
      setError(e.message || 'Failed to apply edits');
    } finally {
      setSaving(false);
    }
  };

  // Helper: determine if a cell has been edited (value differs from original)
  const isCellEdited = (idx, step, education, credits, originalValue) => {
    const key = `${idx}|${step}|${education}|${credits}`;
    const currentValue = (inputs[key] ?? '').trim();
    const origValue = originalValue != null ? String(originalValue).trim() : '';

    if (currentValue === '' && origValue === '') return false;
    if (currentValue === '' || origValue === '') return currentValue !== origValue;

    // Numeric comparison rounded to 2 decimals
    const current = Math.round(Number(currentValue) * 100) / 100;
    const orig = Math.round(Number(origValue) * 100) / 100;
    return current !== orig;
  };

  // Count total calculated (not edited) and edited cells across all schedules
  const counts = useMemo(() => {
    let calculatedCount = 0;
    let editedCount = 0;

    schedules.forEach((schedule, idx) => {
      (schedule.salaries || []).forEach(item => {
        const isCalculated = Boolean(item.isCalculated || item.is_calculated);
        const edited = isCellEdited(idx, item.step, item.education, item.credits, item.salary);

        if (edited) {
          editedCount++;
        } else if (isCalculated) {
          calculatedCount++;
        }
      });
    });

    return { calculatedCount, editedCount };
  }, [schedules, inputs]);

  // Render
  return (
    <div className="modal-backdrop">
      <div className="modal-content edit-salary-modal">
        <div className="modal-header sticky-header">
          <div className="header-top">
            <h3>Edit Salary Table — {district.name}</h3>
            <button className="close-button" onClick={onClose} aria-label="Close">×</button>
          </div>
          <div className="color-key">
            <span className="key-item">
              <span className="color-box calculated"></span>
              Calculated ({counts.calculatedCount})
            </span>
            <span className="key-item">
              <span className="color-box edited"></span>
              Edited ({counts.editedCount})
            </span>
          </div>
        </div>
        <div className="modal-body scrollable-body">
          {loading ? (
            <div className="loading">Loading current salaries…</div>
          ) : error ? (
            <div className="error-message">{error}</div>
          ) : schedules.length === 0 ? (
            <div>No salary data available to edit.</div>
          ) : (
            <div className="salary-editor">
              {schedules.map((schedule, idx) => {
                // Build grid like SalaryTable, but inputs for non-calculated cells
                const salariesByStep = {};
                const colsSet = new Set();
                (schedule.salaries || []).forEach(item => {
                  const step = item.step;
                  const key = item.credits > 0 ? `${item.education}+${item.credits}` : item.education;
                  if (!salariesByStep[step]) salariesByStep[step] = {};
                  salariesByStep[step][key] = item;
                  colsSet.add(JSON.stringify({ education: item.education, credits: item.credits, key }));
                });
                const eduOrder = { 'B': 1, 'M': 2, 'D': 3 };
                const columns = Array.from(colsSet).map(s => JSON.parse(s)).sort((a,b)=>{
                  const ea = eduOrder[a.education] || 99;
                  const eb = eduOrder[b.education] || 99;
                  return ea === eb ? a.credits - b.credits : ea - eb;
                });
                const steps = Object.keys(salariesByStep).map(n=>Number(n)).sort((a,b)=>a-b);

                return (
                  <div key={idx} className="salary-schedule">
                    <h4>{schedule.school_year}{schedule.period ? ` (${schedule.period})` : ''}</h4>
                    <div className="salary-table-wrapper">
                      <table className="salary-table">
                        <thead>
                          <tr>
                            <th>Step</th>
                            {columns.map(c => (
                              <th key={c.key}>{c.key}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {steps.map(step => (
                            <tr key={step}>
                              <td className="step-cell">{step}</td>
                              {columns.map(c => {
                                const item = salariesByStep[step][c.key];
                                const valKey = `${idx}|${step}|${c.education}|${c.credits}`;
                                const isCalculated = Boolean(item?.isCalculated || item?.is_calculated);
                                const edited = item ? isCellEdited(idx, step, c.education, c.credits, item.salary) : false;

                                // Determine cell class: edited takes priority, then calculated
                                let cellClass = 'salary-input';
                                if (edited) {
                                  cellClass += ' edited';
                                } else if (isCalculated) {
                                  cellClass += ' calculated';
                                }

                                return (
                                  <td key={c.key}>
                                    <input
                                      type="text"
                                      inputMode="decimal"
                                      pattern="^\\d+(?:\\.\\d{1,2})?$"
                                      className={cellClass}
                                      value={inputs[valKey] ?? ''}
                                      placeholder={item && item.salary != null ? String(item.salary) : ''}
                                      onChange={(e) => {
                                        // strip $, commas, spaces as user types
                                        const cleaned = (e.target.value || '').replace(/[,$]/g, '').replace(/^\$/,'').trim();
                                        setCell(idx, step, c.education, c.credits, cleaned);
                                      }}
                                    />
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="modal-actions sticky-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn btn-primary" onClick={handleApply} disabled={saving || loading}>
            {saving ? 'Applying…' : 'Apply Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}