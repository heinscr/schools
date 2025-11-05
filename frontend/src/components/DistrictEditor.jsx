import { useState, useEffect } from 'react';
import './DistrictEditor.css';

function DistrictEditor({ district, onClose, onSave }) {
  const [formData, setFormData] = useState({
    name: '',
    main_address: '',
    towns: [],
    district_type: ''
  });
  const [newTownInput, setNewTownInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

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
      await onSave(formData);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
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

          <div className="form-actions">
            <button
              type="button"
              onClick={onClose}
              className="btn btn-cancel"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-save"
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default DistrictEditor;
