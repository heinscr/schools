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

  // State for adding new items
  const [newYearInput, setNewYearInput] = useState('');
  const [newPeriodInput, setNewPeriodInput] = useState('regular');
  const [showAddYear, setShowAddYear] = useState(false);

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

  // Add a new year/period schedule
  const handleAddYear = () => {
    const yearPattern = /^\d{4}-\d{4}$/;
    if (!yearPattern.test(newYearInput.trim())) {
      setError('Year must be in YYYY-YYYY format (e.g., 2024-2025)');
      return;
    }

    // Check if this year/period combination already exists
    const exists = schedules.some(s =>
      s.school_year === newYearInput.trim() &&
      (s.period || 'regular') === newPeriodInput
    );

    if (exists) {
      setError(`Schedule for ${newYearInput.trim()} (${newPeriodInput}) already exists`);
      return;
    }

    // Add new empty schedule
    setSchedules(prev => [...prev, {
      school_year: newYearInput.trim(),
      period: newPeriodInput,
      salaries: []
    }]);

    setNewYearInput('');
    setNewPeriodInput('regular');
    setShowAddYear(false);
    setError(null);
  };

  // Add a new column to a specific schedule
  const handleAddColumn = (scheduleIdx, education, credits) => {
    setSchedules(prev => {
      const updated = [...prev];
      const schedule = { ...updated[scheduleIdx] };
      const salaries = [...(schedule.salaries || [])];

      // Get all existing steps for this schedule
      const existingSteps = Array.from(new Set(salaries.map(s => s.step))).sort((a,b)=>a-b);

      // If no steps exist, add step 1
      const steps = existingSteps.length > 0 ? existingSteps : [1];

      // Add new column cells for all steps
      steps.forEach(step => {
        // Check if this combination already exists
        const exists = salaries.some(s =>
          s.step === step &&
          s.education === education &&
          s.credits === credits
        );

        if (!exists) {
          salaries.push({
            step,
            education,
            credits,
            salary: null,
            isCalculated: false
          });
        }
      });

      schedule.salaries = salaries;
      updated[scheduleIdx] = schedule;
      return updated;
    });
  };

  // Delete a column from a specific schedule
  const handleDeleteColumn = (scheduleIdx, education, credits) => {
    setSchedules(prev => {
      const updated = [...prev];
      const schedule = { ...updated[scheduleIdx] };
      const salaries = (schedule.salaries || []).filter(s =>
        !(s.education === education && s.credits === credits)
      );
      schedule.salaries = salaries;
      updated[scheduleIdx] = schedule;
      return updated;
    });
  };

  // Delete a step (row) from a specific schedule
  const handleDeleteStep = (scheduleIdx, stepNumber) => {
    setSchedules(prev => {
      const updated = [...prev];
      const schedule = { ...updated[scheduleIdx] };
      const salaries = (schedule.salaries || []).filter(s => s.step !== stepNumber);
      schedule.salaries = salaries;
      updated[scheduleIdx] = schedule;
      return updated;
    });
  };

  // Add a new step row to a specific schedule
  const handleAddStep = (scheduleIdx, stepNumber) => {
    setSchedules(prev => {
      const updated = [...prev];
      const schedule = { ...updated[scheduleIdx] };
      const salaries = [...(schedule.salaries || [])];

      // Get all existing education/credit combinations for this schedule
      const existingCols = Array.from(new Set(
        salaries.map(s => `${s.education}|${s.credits}`)
      ));

      // If no columns exist, add a default B column
      const cols = existingCols.length > 0 ? existingCols : ['B|0'];

      // Add new row cells for all columns
      cols.forEach(col => {
        const [education, creditsStr] = col.split('|');
        const credits = Number(creditsStr);

        // Check if this combination already exists
        const exists = salaries.some(s =>
          s.step === stepNumber &&
          s.education === education &&
          s.credits === credits
        );

        if (!exists) {
          salaries.push({
            step: stepNumber,
            education,
            credits,
            salary: null,
            isCalculated: false
          });
        }
      });

      schedule.salaries = salaries;
      updated[scheduleIdx] = schedule;
      return updated;
    });
  };

  // Remove a schedule
  const handleRemoveSchedule = (scheduleIdx) => {
    setSchedules(prev => prev.filter((_, idx) => idx !== scheduleIdx));
    // Clean up inputs for this schedule
    setInputs(prev => {
      const updated = { ...prev };
      Object.keys(updated).forEach(key => {
        if (key.startsWith(`${scheduleIdx}|`)) {
          delete updated[key];
        }
      });
      return updated;
    });
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
          ) : (
            <div className="salary-editor">
              {/* Add Year Button */}
              <div style={{ marginBottom: '20px', display: 'flex', gap: '12px', alignItems: 'center' }}>
                {!showAddYear ? (
                  <button
                    className="btn btn-primary"
                    onClick={() => setShowAddYear(true)}
                    style={{ fontSize: '14px', padding: '8px 16px' }}
                  >
                    + Add New Year
                  </button>
                ) : (
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '4px', flex: 1 }}>
                    <input
                      type="text"
                      placeholder="YYYY-YYYY (e.g., 2024-2025)"
                      value={newYearInput}
                      onChange={(e) => setNewYearInput(e.target.value)}
                      style={{
                        padding: '8px 12px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '4px',
                        fontSize: '14px',
                        width: '200px',
                        backgroundColor: '#ffffff',
                        color: '#000'
                      }}
                    />
                    <select
                      value={newPeriodInput}
                      onChange={(e) => setNewPeriodInput(e.target.value)}
                      style={{
                        padding: '8px 12px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '4px',
                        fontSize: '14px',
                        backgroundColor: '#ffffff',
                        color: '#000'
                      }}
                    >
                      <option value="regular">Regular</option>
                      <option value="summer">Summer</option>
                      <option value="extended">Extended</option>
                      <option value="other">Other</option>
                    </select>
                    <button
                      className="btn btn-primary"
                      onClick={handleAddYear}
                      style={{ fontSize: '14px', padding: '8px 16px' }}
                    >
                      Add
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowAddYear(false);
                        setNewYearInput('');
                        setNewPeriodInput('regular');
                        setError(null);
                      }}
                      style={{ fontSize: '14px', padding: '8px 16px' }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>

              {schedules.length === 0 ? (
                <div>No salary data available. Add a new year to get started.</div>
              ) : (
                schedules.map((schedule, idx) => {
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
                    <div key={idx} className="salary-schedule" style={{ marginBottom: '32px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <h4>{schedule.school_year}{schedule.period ? ` (${schedule.period})` : ''}</h4>
                        <button
                          className="remove-btn"
                          onClick={() => handleRemoveSchedule(idx)}
                          title="Remove this schedule"
                          style={{ width: '24px', height: '24px', fontSize: '18px' }}
                        >
                          ×
                        </button>
                      </div>

                      {/* Add Column and Add Step Controls */}
                      <div style={{ marginBottom: '12px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <AddColumnControl scheduleIdx={idx} onAddColumn={handleAddColumn} />
                        <AddStepControl scheduleIdx={idx} existingSteps={steps} onAddStep={handleAddStep} />
                      </div>

                      <div className="salary-table-wrapper">
                        <table className="salary-table">
                          <thead>
                            <tr>
                              <th>Step</th>
                              {columns.map(c => (
                                <th key={c.key}>
                                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                                    <span>{c.key}</span>
                                    <button
                                      className="remove-btn"
                                      onClick={() => handleDeleteColumn(idx, c.education, c.credits)}
                                      title={`Delete column ${c.key}`}
                                      style={{ width: '18px', height: '18px', fontSize: '14px' }}
                                    >
                                      ×
                                    </button>
                                  </div>
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {steps.map(step => (
                              <tr key={step}>
                                <td className="step-cell">
                                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                                    <span>{step}</span>
                                    <button
                                      className="remove-btn"
                                      onClick={() => handleDeleteStep(idx, step)}
                                      title={`Delete step ${step}`}
                                      style={{ width: '18px', height: '18px', fontSize: '14px' }}
                                    >
                                      ×
                                    </button>
                                  </div>
                                </td>
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
                })
              )}
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

// Component for adding a new column
function AddColumnControl({ scheduleIdx, onAddColumn }) {
  const [showForm, setShowForm] = useState(false);
  const [education, setEducation] = useState('B');
  const [credits, setCredits] = useState(0);

  const handleAdd = () => {
    onAddColumn(scheduleIdx, education, Number(credits));
    setShowForm(false);
    setEducation('B');
    setCredits(0);
  };

  if (!showForm) {
    return (
      <button
        className="btn btn-secondary"
        onClick={() => setShowForm(true)}
        style={{ fontSize: '13px', padding: '6px 12px' }}
      >
        + Add Column
      </button>
    );
  }

  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '8px', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
      <span style={{ fontSize: '13px', fontWeight: '500', color: '#000' }}>Education:</span>
      <select
        value={education}
        onChange={(e) => setEducation(e.target.value)}
        style={{
          padding: '6px 8px',
          border: '1px solid #cbd5e1',
          borderRadius: '4px',
          fontSize: '13px',
          backgroundColor: '#ffffff',
          color: '#000'
        }}
      >
        <option value="B">Bachelor's (B)</option>
        <option value="M">Master's (M)</option>
        <option value="D">Doctorate (D)</option>
      </select>
      <span style={{ fontSize: '13px', fontWeight: '500', color: '#000' }}>Credits:</span>
      <select
        value={credits}
        onChange={(e) => setCredits(e.target.value)}
        style={{
          padding: '6px 8px',
          border: '1px solid #cbd5e1',
          borderRadius: '4px',
          fontSize: '13px',
          backgroundColor: '#ffffff',
          color: '#000',
          width: '80px'
        }}
      >
        <option value="0">0</option>
        <option value="15">15</option>
        <option value="30">30</option>
        <option value="45">45</option>
        <option value="60">60</option>
        <option value="75">75</option>
      </select>
      <button
        className="btn btn-primary"
        onClick={handleAdd}
        style={{ fontSize: '13px', padding: '6px 12px' }}
      >
        Add
      </button>
      <button
        className="btn btn-secondary"
        onClick={() => {
          setShowForm(false);
          setEducation('B');
          setCredits(0);
        }}
        style={{ fontSize: '13px', padding: '6px 12px' }}
      >
        Cancel
      </button>
    </div>
  );
}

// Component for adding a new step
function AddStepControl({ scheduleIdx, existingSteps, onAddStep }) {
  const [showForm, setShowForm] = useState(false);
  const [stepNumber, setStepNumber] = useState('');

  const nextStep = existingSteps.length > 0 ? Math.max(...existingSteps) + 1 : 1;

  const handleAdd = () => {
    const step = Number(stepNumber);
    if (isNaN(step) || step < 1) {
      alert('Please enter a valid step number (1 or greater)');
      return;
    }
    if (existingSteps.includes(step)) {
      alert(`Step ${step} already exists`);
      return;
    }
    onAddStep(scheduleIdx, step);
    setShowForm(false);
    setStepNumber('');
  };

  if (!showForm) {
    return (
      <button
        className="btn btn-secondary"
        onClick={() => {
          setShowForm(true);
          setStepNumber(String(nextStep));
        }}
        style={{ fontSize: '13px', padding: '6px 12px' }}
      >
        + Add Step
      </button>
    );
  }

  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', padding: '8px', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
      <span style={{ fontSize: '13px', fontWeight: '500', color: '#000' }}>Step:</span>
      <input
        type="number"
        min="1"
        value={stepNumber}
        onChange={(e) => setStepNumber(e.target.value)}
        placeholder={`e.g., ${nextStep}`}
        style={{
          padding: '6px 8px',
          border: '1px solid #cbd5e1',
          borderRadius: '4px',
          fontSize: '13px',
          width: '80px',
          backgroundColor: '#ffffff',
          color: '#000'
        }}
      />
      <button
        className="btn btn-primary"
        onClick={handleAdd}
        style={{ fontSize: '13px', padding: '6px 12px' }}
      >
        Add
      </button>
      <button
        className="btn btn-secondary"
        onClick={() => {
          setShowForm(false);
          setStepNumber('');
        }}
        style={{ fontSize: '13px', padding: '6px 12px' }}
      >
        Cancel
      </button>
    </div>
  );
}