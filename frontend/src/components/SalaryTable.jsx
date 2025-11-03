import { useState, useEffect } from 'react';
import api from '../services/api';
import './SalaryTable.css';

function SalaryTable({ districtId }) {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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
        console.log('Salary data received:', data);
        console.log('First schedule:', data[0]);
        setSchedules(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchSalaries();
  }, [districtId]);

  if (!districtId) {
    return null;
  }

  if (loading) {
    return <div className="salary-loading">Loading salary data...</div>;
  }

  if (error) {
    return <div className="salary-error">Error: {error}</div>;
  }

  if (schedules.length === 0) {
    return <div className="salary-empty">No salary data available for this district.</div>;
  }

  return (
    <div className="salary-tables">
      {schedules.map((schedule, idx) => {
        console.log(`Schedule ${idx}:`, schedule);
        
        // Group salaries by step for table display
        const salariesByStep = {};
        const educationCreditsSet = new Set();
        
        (schedule.salaries || []).forEach(item => {
          const step = item.step;
          const eduCredKey = item.credits > 0 ? `${item.education}+${item.credits}` : item.education;
          
          if (!salariesByStep[step]) {
            salariesByStep[step] = {};
          }
          salariesByStep[step][eduCredKey] = item.salary;
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
        
        return (
        <div key={idx} className="salary-schedule">
          <h3>
            {schedule.district_name} - {schedule.school_year}
            {schedule.period && <span className="salary-period"> ({schedule.period})</span>}
          </h3>

          <div className="salary-table-wrapper">
            <table className="salary-table">
              <thead>
                <tr>
                  <th>Step</th>
                  {sortedColumns.map(col => (
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
                    {sortedColumns.map(col => (
                      <td key={col.key} className="salary-cell">
                        {salariesByStep[step][col.key] !== undefined && salariesByStep[step][col.key] !== null
                          ? `$${Number(salariesByStep[step][col.key]).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : 'N/A'}
                      </td>
                    ))}
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
