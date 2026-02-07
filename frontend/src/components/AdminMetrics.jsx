import { useState } from 'react';
import metrics from '../services/metrics';
import './AdminMetrics.css';

function AdminMetrics({ onClose }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState([]);

  const load = async (days = 30) => {
    setLoading(true);
    try {
      const end = new Date().toISOString().slice(0,10);
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - (days-1));
      const start = startDate.toISOString().slice(0,10);
      const resp = await metrics.getDAU(start, end);
      setData(resp.data || []);
    } catch (e) {
      console.error('Failed to load DAU', e);
    } finally {
      setLoading(false);
    }
  };

  const exportCsv = () => {
    const rows = [['date','total','logged_in','anonymous']].concat(
      data.map(d => [d.date, d.total, d.logged_in, d.anonymous])
    );
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'dau.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="admin-metrics-modal">
      <div className="admin-metrics-content">
        <div className="admin-metrics-header">
          <h3>DAU Metrics</h3>
          <div>
            <button className="metric-period-button" onClick={() => load(7)}>Last 7</button>
            <button className="metric-period-button" onClick={() => load(30)}>Last 30</button>
            <button className="metric-period-button" onClick={() => load(90)}>Last 90</button>
            <button className="metric-period-button" onClick={exportCsv} disabled={!data.length}>Export CSV</button>
          </div>
        </div>
        <div className="admin-metrics-body">
          {loading ? <div>Loading...</div> : (
            <table>
              <thead>
                <tr><th>Date</th><th>Total</th><th>Logged In</th><th>Anonymous</th></tr>
              </thead>
              <tbody>
                {data.map(d => (
                  <tr key={d.date}><td>{d.date}</td><td>{d.total}</td><td>{d.logged_in}</td><td>{d.anonymous}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

export default AdminMetrics;
