import { useState, useEffect, useContext } from 'react';
import './DistrictEditor.css';
import api from '../services/api';
import { DataCacheContext } from '../contexts/DataCacheContext';
import { logger } from '../utils/logger';

function DistrictEditor({ district, onClose, onSave }) {
  const [formData, setFormData] = useState({
    name: '',
    main_address: '',
    district_url: '',
    towns: [],
    district_type: ''
  });
  const [newTownInput, setNewTownInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [contractPdfFile, setContractPdfFile] = useState(null);
  const [uploadingContract, setUploadingContract] = useState(false);
  const [contractUploadProgress, setContractUploadProgress] = useState('');
  const _cache = useContext(DataCacheContext);
  const updateDistrictInCache = _cache?.updateDistrictInCache;

  const districtTypeOptions = [
    { value: 'municipal', label: 'Municipal' },
    { value: 'regional_academic', label: 'Regional' },
    { value: 'regional_vocational', label: 'Vocational' },
    { value: 'county_agricultural', label: 'Agricultural' },
    { value: 'charter', label: 'Charter' }
  ];

  useEffect(() => {
    if (district) {
      setFormData({
        name: district.name || '',
        main_address: district.main_address || '',
        district_url: district.district_url || '',
        towns: district.towns || [],
        district_type: district.district_type || ''
      });
    }
  }, [district]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleAddTown = () => {
    const townName = newTownInput.trim();
    if (townName && !formData.towns.includes(townName)) {
      setFormData(prev => ({
        ...prev,
        towns: [...prev.towns, townName]
      }));
      setNewTownInput('');
    }
  };

  const handleRemoveTown = (townToRemove) => {
    setFormData(prev => ({
      ...prev,
      towns: prev.towns.filter(t => t !== townToRemove)
    }));
  };

  const handleTownInputKeyPress = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddTown();
    }
  };

  const handleContractFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.type !== 'application/pdf') {
        setError('Contract must be a PDF file');
        setContractPdfFile(null);
        return;
      }
      if (file.size > 60 * 1024 * 1024) { // 60MB limit
        setError('Contract PDF must be less than 60MB');
        setContractPdfFile(null);
        return;
      }
      setContractPdfFile(file);
      setError(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // Validate that at least one town is added
    if (formData.towns.length === 0) {
      setError('Please add at least one town');
      return;
    }

    setSaving(true);

    try {
      // call onSave (which will persist changes server-side)
      await onSave(formData);

      // Upload contract PDF if one was selected
      if (contractPdfFile) {
        setUploadingContract(true);
        setContractUploadProgress('Uploading contract PDF...');
        try {
          await api.uploadContractPdf(district.id, contractPdfFile);
          setContractUploadProgress('Contract PDF uploaded successfully');
        } catch (uploadErr) {
          logger.debug('Failed to upload contract PDF:', uploadErr?.message || uploadErr);
          setError(`District saved, but contract upload failed: ${uploadErr.message}`);
          setSaving(false);
          setUploadingContract(false);
          setContractUploadProgress('');
          return;
        } finally {
          setUploadingContract(false);
        }
      }

      // After save, fetch the fresh district data from API to ensure cache consistency
      try {
        const fresh = await api.getDistrict(district.id);
        // Compare towns before/after
        const beforeTowns = new Set(district.towns || []);
        const afterTowns = new Set(fresh.towns || []);
        const added = [...afterTowns].filter(t => !beforeTowns.has(t));
        const removed = [...beforeTowns].filter(t => !afterTowns.has(t));

        // Update cache using context helper (if available)
        if (updateDistrictInCache) {
          updateDistrictInCache(fresh);
        }

        if (added.length > 0 || removed.length > 0) {
          logger.debug(`Towns changed for ${district.id}: added=${JSON.stringify(added)}, removed=${JSON.stringify(removed)}`);
        }
      } catch (err) {
        // Non-fatal: log and continue — still close editor
        logger.debug('Failed to refresh district after save:', err?.message || err);
      }

      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
      setContractUploadProgress('');
    }
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!district) return null;

  return (
    <div className="district-editor-backdrop" onClick={handleBackdropClick}>
      <div className="district-editor-modal">
        <div className="district-editor-header">
          <h2>Edit District</h2>
          <button
            className="close-button"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="district-editor-form">
          {error && (
            <div className="editor-error">
              <strong>Error:</strong> {error}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="name">District Name</label>
            <input
              type="text"
              id="name"
              name="name"
              value={formData.name}
              onChange={handleInputChange}
              required
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="district_type">District Type</label>
            <select
              id="district_type"
              name="district_type"
              value={formData.district_type}
              onChange={handleInputChange}
              required
              className="form-select"
            >
              {districtTypeOptions.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="main_address">Main Address</label>
            <textarea
              id="main_address"
              name="main_address"
              value={formData.main_address}
              onChange={handleInputChange}
              rows="3"
              className="form-textarea"
            />
          </div>

          <div className="form-group">
            <label htmlFor="district_url">District URL</label>
            <input
              type="url"
              id="district_url"
              name="district_url"
              value={formData.district_url}
              onChange={handleInputChange}
              placeholder="https://example.com"
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="new-town">Towns</label>
            <div className="town-input-container">
              <input
                type="text"
                id="new-town"
                value={newTownInput}
                onChange={(e) => setNewTownInput(e.target.value)}
                onKeyPress={handleTownInputKeyPress}
                placeholder="Enter town name"
                className="form-input"
              />
              <button
                type="button"
                onClick={handleAddTown}
                className="btn-add-town"
              >
                + Add
              </button>
            </div>
            <div className="towns-list">
              {formData.towns.length === 0 ? (
                <small className="form-help">No towns added yet. Add at least one town.</small>
              ) : (
                formData.towns.map((town, idx) => (
                  <div key={idx} className="town-tag">
                    <span>{town}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveTown(town)}
                      className="remove-town-btn"
                      title="Remove town"
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="contract-pdf">Contract PDF</label>
            <input
              type="file"
              id="contract-pdf"
              accept="application/pdf"
              onChange={handleContractFileChange}
              className="form-input"
            />
            {contractPdfFile && (
              <small className="form-help">
                Selected: {contractPdfFile.name} ({(contractPdfFile.size / 1024 / 1024).toFixed(2)} MB)
              </small>
            )}
            {district.contract_pdf && !contractPdfFile && (
              <small className="form-help">
                Current contract: {district.contract_pdf.split('/').pop()} (upload new file to replace)
              </small>
            )}
            {uploadingContract && (
              <small className="form-help uploading">
                {contractUploadProgress}
              </small>
            )}
          </div>

          <div className="form-actions">
            <button
              type="button"
              onClick={onClose}
              className="btn btn-cancel"
              disabled={saving || uploadingContract}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-save"
              disabled={saving || uploadingContract}
            >
              {saving || uploadingContract ? (uploadingContract ? 'Uploading...' : 'Saving...') : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default DistrictEditor;