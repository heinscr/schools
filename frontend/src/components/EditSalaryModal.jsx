
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
  const [newYearInput, setNewYearInput] = useState('2025-2026');
  const [showAddYear, setShowAddYear] = useState(false);

  // Generate year options from 2025-2026 to 2030-2031
  const yearOptions = [];
  for (let startYear = 2025; startYear <= 2030; startYear++) {
    yearOptions.push(`${startYear}-${startYear + 1}`);
  }

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

  // State for raw clipboard input per schedule
  const [rawInputs, setRawInputs] = useState({});
  const [showRawInputs, setShowRawInputs] = useState({});

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
    // Check if this year already exists (with Full Year period)
    const exists = schedules.some(s =>
      s.school_year === newYearInput &&
      (s.period || 'Full Year') === 'Full Year'
    );

    if (exists) {
      setError(`Schedule for ${newYearInput} already exists`);
      return;
    }

    // Add new empty schedule with "Full Year" period
    setSchedules(prev => [...prev, {
      school_year: newYearInput,
      period: 'Full Year',
      salaries: []
    }]);

    setNewYearInput('2025-2026');
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

  // Re-label a column (change education level and/or credits)
  const handleRelabelColumn = (scheduleIdx, oldEducation, oldCredits, newEducation, newCredits) => {
    setSchedules(prev => {
      const updated = [...prev];
      const schedule = { ...updated[scheduleIdx] };
      const salaries = (schedule.salaries || []).map(s => {
        if (s.education === oldEducation && s.credits === oldCredits) {
          return { ...s, education: newEducation, credits: newCredits };
        }
        return s;
      });
      schedule.salaries = salaries;
      updated[scheduleIdx] = schedule;
      return updated;
    });

    // Update inputs map with new keys
    setInputs(prev => {
      const updated = { ...prev };
      const steps = Array.from(new Set(
        (schedules[scheduleIdx]?.salaries || []).map(s => s.step)
      ));

      steps.forEach(step => {
        const oldKey = `${scheduleIdx}|${step}|${oldEducation}|${oldCredits}`;
        const newKey = `${scheduleIdx}|${step}|${newEducation}|${newCredits}`;
        if (updated[oldKey] !== undefined) {
          updated[newKey] = updated[oldKey];
          delete updated[oldKey];
        }
      });

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

  // Parse clipboard data and populate the schedule
  const handlePasteData = async (scheduleIdx) => {
    try {
      const text = await navigator.clipboard.readText();

      // Store the raw text and show the raw input area
      setRawInputs(prev => ({ ...prev, [scheduleIdx]: text }));
      setShowRawInputs(prev => ({ ...prev, [scheduleIdx]: true }));

      // Parse and populate the table
      parseAndPopulateSchedule(scheduleIdx, text);

      setError(null);
    } catch (e) {
      setError('Failed to read clipboard. Please ensure you have granted clipboard permissions.');
    }
  };

  // Parse raw text and populate the schedule (used by paste and when editing raw input)
  const parseAndPopulateSchedule = (scheduleIdx, text) => {
    const parsed = parseClipboardData(text);

    if (!parsed.success) {
      setError(parsed.error || 'Failed to parse clipboard data');
      return;
    }

    // Update the schedule with parsed data
    setSchedules(prev => {
      const updated = [...prev];
      const schedule = { ...updated[scheduleIdx] };
      const salaries = [];

      // Create all cells from parsed data
      parsed.steps.forEach(step => {
        parsed.columns.forEach(col => {
          const salary = parsed.data[step]?.[col.key];
          if (salary != null) {
            salaries.push({
              step,
              education: col.education,
              credits: col.credits,
              salary,
              isCalculated: false
            });
          }
        });
      });

      schedule.salaries = salaries;
      updated[scheduleIdx] = schedule;
      return updated;
    });

    setError(null);
  };

  // Handle raw input changes and re-parse
  const handleRawInputChange = (scheduleIdx, newText) => {
    // Update the raw input state
    setRawInputs(prev => ({ ...prev, [scheduleIdx]: newText }));

    // Try to parse and update the table
    if (newText.trim()) {
      parseAndPopulateSchedule(scheduleIdx, newText);
    }
  };

  // Toggle raw input visibility
  const toggleRawInput = (scheduleIdx) => {
    setShowRawInputs(prev => ({ ...prev, [scheduleIdx]: !prev[scheduleIdx] }));
  };

  // Intelligent parser for clipboard data
  const parseClipboardData = (text) => {
    const lines = text.trim().split('\n').filter(line => line.trim());
    if (lines.length < 2) {
      return { success: false, error: 'Clipboard data must have at least a header row and one data row' };
    }

    // Enhanced education mapping (matches backend's EDU_MAP)
    const eduMap = {
      'B': 'B', 'BA': 'B', 'BACHELOR': 'B', "BACHELOR'S": 'B', 'BACCALAUREATE': 'B',
      'M': 'M', 'MA': 'M', 'MASTER': 'M', "MASTER'S": 'M', 'MASTERS': 'M', '2M': 'M',
      'CAGS': 'M',  // CAGS typically maps to M+60 but we'll handle that separately
      'D': 'D', 'DOC': 'D', 'DOCTOR': 'D', "DOCTOR'S": 'D', 'DOCTORATE': 'D',
      'PHD': 'D', 'EDD': 'D', 'PROV': 'D'
    };

    const headerTokens = [];
    let dataStartIdx = 0;

    // Collect all header tokens until we hit a line starting with a number
    for (let i = 0; i < lines.length; i++) {
      const parts = lines[i].split(/\s+/).filter(p => p.trim());
      const firstPart = parts[0];

      // If first part is a number, this is where data starts
      if (/^\d+$/.test(firstPart)) {
        dataStartIdx = i;
        break;
      }

      // Collect all non-"Step" tokens from header lines
      for (const part of parts) {
        const normalized = part.replace(/['']/g, "'").toUpperCase();
        if (!normalized.match(/^(STEP|TEP)$/i)) {
          headerTokens.push(part);
        }
      }
    }

    if (dataStartIdx === 0 || headerTokens.length === 0) {
      return { success: false, error: 'Could not find header and data rows' };
    }

    // Find the first data row with actual values to determine column count
    let numDataCols = 0;
    for (let i = dataStartIdx; i < Math.min(dataStartIdx + 10, lines.length); i++) {
      const parts = lines[i].split(/\s+/);
      if (parts.length > 1 && /^\d+$/.test(parts[0])) {
        // This line starts with a step number and has values
        const valueCols = parts.slice(1).filter(p => {
          const cleaned = p.replace(/[$,]/g, '').trim();
          return !isNaN(parseFloat(cleaned));
        }).length;
        if (valueCols > numDataCols) {
          numDataCols = valueCols;
        }
      }
    }

    if (numDataCols === 0) {
      // Fallback to header token count
      numDataCols = headerTokens.length;
    }

    // Helper function to parse a column header token or phrase
    const parseColumnHeader = (tokens) => {
      let combined = tokens.join(' ').replace(/['']/g, "'").toUpperCase();

      // Normalize patterns like backend does
      combined = combined.replace(/\b(BA|MA|B|M)(\d{1,2})\b/g, '$1+$2');
      combined = combined.replace(/[–—\-:]/g, '+');
      combined = combined.replace(/\s*\+\s*/g, '+');

      // Special case: CAGS alone maps to M+60
      if (combined === 'CAGS' || combined.includes('CAGS') && !combined.includes('DOC')) {
        // Check if there's a credit amount mentioned
        const creditMatch = combined.match(/\+\s*(\d+)/);
        if (creditMatch) {
          return { education: 'M', credits: parseInt(creditMatch[1]), key: `M+${creditMatch[1]}` };
        }
        return { education: 'M', credits: 60, key: 'M+60' };
      }

      // Special case: CAGS+DOC or CAGS/DOC -> D
      if (combined.includes('CAGS') && (combined.includes('DOC') || combined.includes('/'))) {
        return { education: 'D', credits: 0, key: 'D' };
      }

      // Try patterns like "BACHELOR'S DEGREE", "MASTER'S DEGREE +30", etc.
      let eduLevel = null;
      let credits = 0;

      // Look for education level keywords (longest match first)
      const sortedKeys = Object.keys(eduMap).sort((a, b) => b.length - a.length);
      for (const key of sortedKeys) {
        if (combined.includes(key)) {
          eduLevel = eduMap[key];
          break;
        }
      }

      // Look for credit amounts like "+30", "+45", "DEGREE +30"
      const creditMatch = combined.match(/\+\s*(\d+)/);
      if (creditMatch) {
        credits = parseInt(creditMatch[1]);
      }

      if (eduLevel) {
        const key = credits > 0 ? `${eduLevel}+${credits}` : eduLevel;
        return { education: eduLevel, credits, key };
      }

      return null;
    };

    // Try to match header tokens to columns
    const columns = [];

    // First, try to parse all tokens as simple single-token headers
    // This parser now mirrors the backend's extraction_utils.py normalize_lane_key logic
    const parsedTokens = headerTokens.map(token => {
      let normalized = token.replace(/['']/g, "'").toUpperCase();

      // Normalize common patterns like backend does:
      // BA15 -> BA+15, M30 -> M+30, MA15 -> MA+15
      normalized = normalized.replace(/\b(BA|MA|B|M)(\d{1,2})\b/g, '$1+$2');

      // Normalize separators: dashes/colons to plus
      normalized = normalized.replace(/[–—\-:]/g, '+');

      // Normalize plus signs (remove spaces around them)
      normalized = normalized.replace(/\s*\+\s*/g, '+');

      // Special case: CAGS maps to M+60
      if (normalized === 'CAGS') {
        return { education: 'M', credits: 60, key: 'M+60', original: token, parsed: true };
      }

      // Special case: Handle CAGS+DOC or CAGS/DOC -> D
      if (normalized.includes('CAGS') && (normalized.includes('DOC') || normalized.includes('/'))) {
        return { education: 'D', credits: 0, key: 'D', original: token, parsed: true };
      }

      // Special case: B30/MA or B+30/MA -> M (equivalent to MA)
      if (normalized.match(/B\+?30\/MA/)) {
        return { education: 'M', credits: 0, key: 'M', original: token, parsed: true };
      }

      // Special case: MA+45/CAGS or M+60/CAGS -> M with the credit amount
      const cagsWithCredits = normalized.match(/M[A]?\+(\d+)\/CAGS/);
      if (cagsWithCredits) {
        const credits = parseInt(cagsWithCredits[1]);
        return { education: 'M', credits, key: `M+${credits}`, original: token, parsed: true };
      }

      // Try simple patterns (e.g., "BA+15", "MA", "DOC", "B", "M+30")
      const simpleMatch = normalized.match(/^([A-Z]+)(\+(\d+))?$/);
      if (simpleMatch) {
        const eduRaw = simpleMatch[1];
        const education = eduMap[eduRaw] || eduRaw.charAt(0);
        const credits = simpleMatch[3] ? parseInt(simpleMatch[3]) : 0;
        const key = credits > 0 ? `${education}+${credits}` : education;
        return { education, credits, key, original: token, parsed: true };
      }
      return { original: token, parsed: false };
    });

    // Count how many tokens successfully parsed as simple headers
    const simpleParsedCount = parsedTokens.filter(t => t.parsed).length;

    if (simpleParsedCount === numDataCols || simpleParsedCount >= numDataCols) {
      // Use parsed tokens, handling potential duplicates by adding suffixes
      const seenKeys = new Map(); // maps key -> count
      for (const token of parsedTokens) {
        if (token.parsed && columns.length < numDataCols) {
          let finalKey = token.key;
          const count = seenKeys.get(token.key) || 0;
          if (count > 0) {
            // Duplicate key - add suffix
            finalKey = `${token.key}_${count}`;
          }
          seenKeys.set(token.key, count + 1);

          columns.push({
            education: token.education,
            credits: token.credits,
            key: finalKey,
            original: token.original
          });
        }
      }
    } else if (headerTokens.length === numDataCols) {
      // Same number of tokens as columns, but not all parsed simply
      // Try complex parsing for unparsed tokens
      for (const token of parsedTokens) {
        if (token.parsed) {
          columns.push(token);
        } else {
          const parsed = parseColumnHeader([token.original]);
          if (parsed) {
            columns.push({ ...parsed, original: token.original });
          } else {
            columns.push({ education: 'B', credits: 0, key: `Col${columns.length + 1}`, original: token.original });
          }
        }
      }
    } else {
      // Complex case: tokens may represent multi-word headers
      // Try to group tokens into column headers based on known patterns
      let i = 0;
      while (i < headerTokens.length && columns.length < numDataCols) {
        // First try single token if it parsed successfully
        if (parsedTokens[i]?.parsed) {
          columns.push(parsedTokens[i]);
          i++;
        } else {
          // Try consuming 2-4 tokens as a potential multi-word column header
          let found = false;
          for (let len = 4; len >= 2; len--) {
            if (i + len > headerTokens.length) continue;
            const phrase = headerTokens.slice(i, i + len);
            const parsed = parseColumnHeader(phrase);
            if (parsed) {
              columns.push({ ...parsed, original: phrase.join(' ') });
              i += len;
              found = true;
              break;
            }
          }
          if (!found) {
            // Couldn't parse, use placeholder
            columns.push({ education: 'B', credits: 0, key: `Col${columns.length + 1}`, original: headerTokens[i] });
            i++;
          }
        }
      }

      // Fill in missing columns with defaults
      while (columns.length < numDataCols) {
        columns.push({ education: 'B', credits: 0, key: `Col${columns.length + 1}`, original: `Col${columns.length + 1}` });
      }
    }

    if (columns.length === 0) {
      return { success: false, error: 'Could not identify any education columns' };
    }

    // Parse data rows - enhanced to handle multi-line data and sparse rows
    const steps = [];
    const data = {};
    let currentStep = null;
    let pendingValues = []; // Values waiting to be assigned to a step

    for (let i = dataStartIdx; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const parts = line.split(/\s+/);
      if (parts.length === 0) continue;

      // Check if first part is a step number
      const firstToken = parts[0];
      const stepNum = parseInt(firstToken);

      if (!isNaN(stepNum) && stepNum >= 1) {
        // This line starts with a step number

        // First, process any pending values for previous step
        if (currentStep !== null && pendingValues.length > 0) {
          if (!data[currentStep]) {
            data[currentStep] = {};
          }
          // Right-align: if fewer values than columns, fill from the right
          const startCol = Math.max(0, columns.length - pendingValues.length);
          pendingValues.forEach((val, idx) => {
            const colIdx = startCol + idx;
            if (colIdx < columns.length) {
              const col = columns[colIdx];
              data[currentStep][col.key] = val;
            }
          });
          pendingValues = [];
        }

        // Start new step
        currentStep = stepNum;
        if (!steps.includes(stepNum)) {
          steps.push(stepNum);
        }
        if (!data[stepNum]) {
          data[stepNum] = {};
        }

        // Parse values from this line (after the step number)
        for (let j = 1; j < parts.length; j++) {
          const valueStr = parts[j].replace(/[$,]/g, '').trim();
          // Try to clean up OCR errors like "41.124.59" -> "41124.59"
          const cleaned = valueStr.replace(/\.(\d{3})\./g, '$1.');
          const value = parseFloat(cleaned);
          if (!isNaN(value) && value > 0) {
            pendingValues.push(value);
          }
        }
      } else {
        // This line doesn't start with a step number
        // Could be continuation of previous step's data, or noise

        // Try to extract salary values from this line
        const values = [];
        for (const part of parts) {
          // Skip obvious non-salary text
          if (/^[A-Za-z]+$/.test(part) && !part.match(/^\$?\d/)) continue;

          const valueStr = part.replace(/[$,]/g, '').trim();
          // Try to clean up OCR errors
          const cleaned = valueStr.replace(/\.(\d{3})\./g, '$1.');
          const value = parseFloat(cleaned);
          if (!isNaN(value) && value > 0) {
            values.push(value);
          }
        }

        // If we found values and have a current step, add them as pending
        if (values.length > 0 && currentStep !== null) {
          pendingValues.push(...values);
        }
      }
    }

    // Process any remaining pending values
    if (currentStep !== null && pendingValues.length > 0) {
      if (!data[currentStep]) {
        data[currentStep] = {};
      }
      // Right-align: if fewer values than columns, fill from the right
      const startCol = Math.max(0, columns.length - pendingValues.length);
      pendingValues.forEach((val, idx) => {
        const colIdx = startCol + idx;
        if (colIdx < columns.length) {
          const col = columns[colIdx];
          data[currentStep][col.key] = val;
        }
      });
    }

    if (steps.length === 0) {
      return { success: false, error: 'No valid data rows found' };
    }

    return { success: true, columns, steps, data };
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
                    <label style={{ fontSize: '14px', fontWeight: '500', color: '#000' }}>School Year:</label>
                    <select
                      value={newYearInput}
                      onChange={(e) => setNewYearInput(e.target.value)}
                      style={{
                        padding: '8px 12px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '4px',
                        fontSize: '14px',
                        backgroundColor: '#ffffff',
                        color: '#000',
                        width: '150px'
                      }}
                    >
                      {yearOptions.map(year => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                    <span style={{ fontSize: '14px', color: '#666' }}>(Full Year)</span>
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
                        setNewYearInput('2025-2026');
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
                        <button
                          className="btn btn-secondary"
                          onClick={() => handlePasteData(idx)}
                          style={{ fontSize: '13px', padding: '6px 12px' }}
                          title="Paste salary table from clipboard"
                        >
                          📋 Paste from Clipboard
                        </button>
                        {rawInputs[idx] && (
                          <button
                            className="btn btn-secondary"
                            onClick={() => toggleRawInput(idx)}
                            style={{ fontSize: '13px', padding: '6px 12px' }}
                            title={showRawInputs[idx] ? "Hide raw input" : "Show raw input"}
                          >
                            {showRawInputs[idx] ? '👁️ Hide Raw Input' : '👁️ Show Raw Input'}
                          </button>
                        )}
                      </div>

                      {/* Raw Input Editor */}
                      {showRawInputs[idx] && (
                        <div style={{ marginBottom: '16px', padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '4px', border: '1px solid #cbd5e1' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                            <label style={{ fontSize: '14px', fontWeight: '600', color: '#1f2937' }}>
                              Raw Input (Edit to update table)
                            </label>
                            <button
                              className="btn btn-secondary"
                              onClick={() => setRawInputs(prev => {
                                const updated = { ...prev };
                                delete updated[idx];
                                return updated;
                              })}
                              style={{ fontSize: '12px', padding: '4px 8px' }}
                              title="Clear raw input"
                            >
                              Clear
                            </button>
                          </div>
                          <textarea
                            value={rawInputs[idx] || ''}
                            onChange={(e) => handleRawInputChange(idx, e.target.value)}
                            style={{
                              width: '100%',
                              minHeight: '150px',
                              padding: '8px',
                              border: '1px solid #cbd5e1',
                              borderRadius: '4px',
                              fontSize: '13px',
                              fontFamily: 'monospace',
                              backgroundColor: '#ffffff',
                              color: '#000',
                              resize: 'vertical'
                            }}
                            placeholder="Paste or edit salary data here..."
                          />
                        </div>
                      )}

                      <div className="salary-table-wrapper">
                        <table className="salary-table">
                          <thead>
                            <tr>
                              <th>Step</th>
                              {columns.map(c => (
                                <ColumnHeader
                                  key={c.key}
                                  scheduleIdx={idx}
                                  column={c}
                                  onDelete={handleDeleteColumn}
                                  onRelabel={(newEducation, newCredits) => handleRelabelColumn(idx, c.education, c.credits, newEducation, newCredits)}
                                />
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

// Component for column header with edit capability
function ColumnHeader({ scheduleIdx, column, onDelete, onRelabel }) {
  const [isEditing, setIsEditing] = useState(false);
  const [education, setEducation] = useState(column.education);
  const [credits, setCredits] = useState(column.credits);

  const handleSave = () => {
    onRelabel(education, Number(credits));
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEducation(column.education);
    setCredits(column.credits);
    setIsEditing(false);
  };

  if (!isEditing) {
    return (
      <th key={column.key}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
          <span
            onClick={() => setIsEditing(true)}
            style={{ cursor: 'pointer' }}
            title="Click to edit column label"
          >
            {column.key}
          </span>
          <button
            className="remove-btn"
            onClick={() => onDelete(scheduleIdx, column.education, column.credits)}
            title={`Delete column ${column.key}`}
            style={{ width: '18px', height: '18px', fontSize: '14px' }}
          >
            ×
          </button>
        </div>
      </th>
    );
  }

  return (
    <th key={column.key}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', padding: '8px', minWidth: '180px' }}>
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          <select
            value={education}
            onChange={(e) => setEducation(e.target.value)}
            style={{
              padding: '4px 6px',
              border: '1px solid #cbd5e1',
              borderRadius: '4px',
              fontSize: '12px',
              backgroundColor: '#ffffff',
              color: '#000',
              flex: 1
            }}
          >
            <option value="B">B</option>
            <option value="M">M</option>
            <option value="D">D</option>
          </select>
          <select
            value={credits}
            onChange={(e) => setCredits(e.target.value)}
            style={{
              padding: '4px 6px',
              border: '1px solid #cbd5e1',
              borderRadius: '4px',
              fontSize: '12px',
              backgroundColor: '#ffffff',
              color: '#000',
              flex: 1
            }}
          >
            <option value="0">0</option>
            <option value="15">+15</option>
            <option value="30">+30</option>
            <option value="45">+45</option>
            <option value="60">+60</option>
            <option value="75">+75</option>
          </select>
        </div>
        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            onClick={handleSave}
            style={{
              padding: '4px 8px',
              fontSize: '11px',
              backgroundColor: '#10b981',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              flex: 1
            }}
          >
            ✓
          </button>
          <button
            onClick={handleCancel}
            style={{
              padding: '4px 8px',
              fontSize: '11px',
              backgroundColor: '#6b7280',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              flex: 1
            }}
          >
            ✕
          </button>
        </div>
      </div>
    </th>
  );
}
