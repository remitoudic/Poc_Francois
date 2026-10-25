import React, { useState, useEffect } from 'react';
import './App.css';
import {
  Layers,
  ArrowRight,
  Database,
  Server,
  CloudCheck,
  Play,
  RotateCw,
  FileCode,
  AlertCircle,
  ExternalLink,
  Send,
  Eye,
  Globe
} from 'lucide-react';

interface SystemHealth {
  status: string;
  database: string;
  plunet: {
    success: boolean;
    version: string;
    status: string;
    base_url: string;
  };
}

interface FixtureItem {
  filename: string;
  source_language: string;
  target_language: string;
  segment_count: number;
  word_count: number;
}

interface XLIFFSegment {
  unit_id: string;
  resname?: string;
  source_text: string;
  target_text?: string;
  status?: string;
  notes?: string;
}

interface ETLJob {
  id: number;
  job_name: string;
  source_type: string;
  source_reference: string;
  status: string;
  source_language: string;
  target_language: string;
  segment_count: number;
  word_count: number;
  plunet_synced: string;
  plunet_order_id?: number;
  destination_url?: string;
  destination_status_code?: number;
  error_message?: string;
  created_at: string;
  raw_xliff?: string;
  processed_xliff?: string;
  segments?: XLIFFSegment[];
}

interface Delivery {
  id: number;
  job_id: number;
  source_filename: string;
  source_language: string;
  target_language: string;
  segment_count: number;
  word_count: number;
  payload_size: number;
  received_at: string;
}

export default function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [fixtures, setFixtures] = useState<FixtureItem[]>([]);
  const [jobs, setJobs] = useState<ETLJob[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [activeTab, setActiveTab] = useState<'jobs' | 'deliveries' | 'plunet'>('jobs');
  const [selectedJob, setSelectedJob] = useState<ETLJob | null>(null);

  // Form inputs
  const [sourceType, setSourceType] = useState<'fixture' | 'api' | 'upload'>('fixture');
  const [selectedFixture, setSelectedFixture] = useState('example.fr.xlf');
  const [apiUrl, setApiUrl] = useState('');
  const [destinationUrl, setDestinationUrl] = useState('http://localhost:8000/api/v1/etl/simulate-destination');
  const [syncPlunet, setSyncPlunet] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [plunetAuthTest, setPlunetAuthTest] = useState<any>(null);
  const [testingPlunet, setTestingPlunet] = useState(false);

  // Fetch initial data
  const fetchData = async () => {
    try {
      // Health
      const healthRes = await fetch('/api/v1/health');
      if (healthRes.ok) setHealth(await healthRes.json());

      // Fixtures
      const fixturesRes = await fetch('/api/v1/xliff/fixtures');
      if (fixturesRes.ok) {
        const data = await fixturesRes.json();
        setFixtures(data);
        if (data.length > 0 && !selectedFixture) {
          setSelectedFixture(data[0].filename);
        }
      }

      // Jobs
      const jobsRes = await fetch('/api/v1/etl/jobs');
      if (jobsRes.ok) setJobs(await jobsRes.json());

      // Deliveries
      const delivRes = await fetch('/api/v1/etl/destination-deliveries');
      if (delivRes.ok) setDeliveries(await delivRes.json());
    } catch (err) {
      console.error('Error fetching initial data:', err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  // Run ETL Pipeline
  const handleRunETL = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsRunning(true);
    setErrorMessage(null);

    const payload: any = {
      source_type: sourceType,
      destination_url: destinationUrl,
      sync_with_plunet: syncPlunet,
    };

    if (sourceType === 'fixture') {
      payload.fixture_name = selectedFixture;
      payload.job_name = `ETL-${selectedFixture}`;
    } else if (sourceType === 'api') {
      payload.api_url = apiUrl;
      payload.job_name = `ETL-Remote-API`;
    }

    try {
      const res = await fetch('/api/v1/etl/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'ETL execution failed');
      }

      const completedJob = await res.json();
      setSelectedJob(completedJob);
      fetchData();
    } catch (err: any) {
      setErrorMessage(err.message || 'Error occurred during ETL pipeline run');
    } finally {
      setIsRunning(false);
    }
  };

  // Test Plunet Login
  const handleTestPlunetAuth = async () => {
    setTestingPlunet(true);
    try {
      const res = await fetch('/api/v1/plunet/test-login', { method: 'POST' });
      setPlunetAuthTest(await res.json());
    } catch (err: any) {
      setPlunetAuthTest({ success: false, error: err.message });
    } finally {
      setTestingPlunet(false);
    }
  };

  // View Job Detail
  const handleViewJob = async (jobId: number) => {
    try {
      const res = await fetch(`/api/v1/etl/jobs/${jobId}`);
      if (res.ok) {
        setSelectedJob(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="app-container">
      {/* Top Navbar */}
      <header className="navbar">
        <div className="brand">
          <div className="brand-logo">FOX</div>
          <div>
            <div className="brand-title">FOX MLO</div>
            <div className="brand-sub">Translation ETL & Plunet Orchestration</div>
          </div>
        </div>

        {/* Live Status Indicators */}
        <div className="system-status">
          <div className={`status-badge ${health?.database === 'HEALTHY' ? 'online' : 'warning'}`}>
            <Database size={14} />
            <span>Postgres: {health?.database === 'HEALTHY' ? 'Connected' : 'Connecting'}</span>
          </div>

          <div className={`status-badge ${health?.plunet?.success ? 'online' : 'warning'}`}>
            <Server size={14} />
            <span>Plunet: {health?.plunet?.version ? `v${health.plunet.version}` : '10.26.2'}</span>
          </div>

          <button className="btn btn-outline" style={{ width: 'auto', padding: '0.35rem 0.75rem', fontSize: '0.8rem' }} onClick={fetchData}>
            <RotateCw size={14} />
            <span>Refresh</span>
          </button>
        </div>
      </header>

      {/* Hero Section */}
      <section className="hero">
        <h1>Welcome to <span>FOX MLO</span></h1>
        <p>
          High-performance automated ETL pipeline connecting external translation APIs, parsing & validating XLIFF documents, syncing with Plunet BusinessManager, and transporting payloads to destination servers.
        </p>

        {/* Visual Pipeline Flow */}
        <div className="pipeline-steps">
          <div className="step-pill">
            <Globe size={16} color="#3b82f6" />
            <span>1. Extract XLIFF (API/Fixture)</span>
          </div>
          <span className="step-arrow"><ArrowRight size={16} /></span>
          <div className="step-pill">
            <Layers size={16} color="#f97316" />
            <span>2. Python ETL & Transformation</span>
          </div>
          <span className="step-arrow"><ArrowRight size={16} /></span>
          <div className="step-pill">
            <CloudCheck size={16} color="#10b981" />
            <span>3. Plunet Sync (portal.foxtranslations.com)</span>
          </div>
          <span className="step-arrow"><ArrowRight size={16} /></span>
          <div className="step-pill">
            <Send size={16} color="#8b5cf6" />
            <span>4. Load to Destination Server</span>
          </div>
        </div>
      </section>

      {/* Main Grid Layout */}
      <main className="main-content">
        {/* Left Column: Pipeline Trigger Form */}
        <div>
          <div className="card">
            <div className="card-title">
              <span>Execute ETL Pipeline</span>
              <FileCode size={18} color="var(--primary)" />
            </div>

            <form onSubmit={handleRunETL}>
              {/* Source Type */}
              <div className="form-group">
                <label>Extraction Source</label>
                <select
                  className="form-select"
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as any)}
                >
                  <option value="fixture">Local Fixture (XLIFF Sample File)</option>
                  <option value="api">External REST API</option>
                </select>
              </div>

              {/* Source Details */}
              {sourceType === 'fixture' ? (
                <div className="form-group">
                  <label>Select Sample XLIFF Fixture</label>
                  <select
                    className="form-select"
                    value={selectedFixture}
                    onChange={(e) => setSelectedFixture(e.target.value)}
                  >
                    {fixtures.map((f) => (
                      <option key={f.filename} value={f.filename}>
                        {f.filename} ({f.source_language} &rarr; {f.target_language}, {f.word_count} words)
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="form-group">
                  <label>Remote XLIFF API Endpoint</label>
                  <input
                    type="url"
                    className="form-input"
                    placeholder="https://api.partner.com/v1/translations/job123.xlf"
                    value={apiUrl}
                    onChange={(e) => setApiUrl(e.target.value)}
                    required
                  />
                </div>
              )}

              {/* Destination URL */}
              <div className="form-group">
                <label>Destination Server URL</label>
                <input
                  type="text"
                  className="form-input"
                  value={destinationUrl}
                  onChange={(e) => setDestinationUrl(e.target.value)}
                  required
                />
                <small style={{ color: 'var(--slate-500)', fontSize: '0.75rem', marginTop: '0.25rem', display: 'block' }}>
                  Target server that receives the processed XLIFF payload.
                </small>
              </div>

              {/* Plunet Sync Option */}
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  id="syncPlunet"
                  checked={syncPlunet}
                  onChange={(e) => setSyncPlunet(e.target.checked)}
                />
                <label htmlFor="syncPlunet" style={{ marginBottom: 0, cursor: 'pointer' }}>
                  Synchronize with Plunet BusinessManager (SOAP)
                </label>
              </div>

              {/* Error Display */}
              {errorMessage && (
                <div style={{ background: '#fee2e2', color: '#991b1b', padding: '0.75rem', borderRadius: '8px', fontSize: '0.85rem', marginBottom: '1rem' }}>
                  <AlertCircle size={14} style={{ marginRight: '0.35rem', verticalAlign: 'middle' }} />
                  {errorMessage}
                </div>
              )}

              {/* Submit Button */}
              <button type="submit" className="btn btn-primary" disabled={isRunning}>
                {isRunning ? (
                  <>
                    <RotateCw className="spin" size={16} />
                    <span>Processing & Transporting...</span>
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    <span>Run ETL Pipeline</span>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Quick Plunet Status Card */}
          <div className="card" style={{ marginTop: '1.5rem' }}>
            <div className="card-title">
              <span>Plunet Server Integration</span>
              <ExternalLink size={16} color="var(--slate-500)" />
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--slate-700)' }}>
              <div style={{ marginBottom: '0.5rem' }}>
                <strong>Target Portal:</strong>{' '}
                <a href="https://portal.foxtranslations.com/" target="_blank" rel="noreferrer" style={{ color: 'var(--primary)', textDecoration: 'none' }}>
                  portal.foxtranslations.com
                </a>
              </div>
              <div style={{ marginBottom: '0.5rem' }}>
                <strong>Server Version:</strong> 10.26.2 (Active)
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <strong>API User:</strong> API integration
              </div>

              <button
                type="button"
                className="btn btn-outline"
                onClick={handleTestPlunetAuth}
                disabled={testingPlunet}
              >
                {testingPlunet ? 'Authenticating...' : 'Test Plunet Authentication'}
              </button>

              {plunetAuthTest && (
                <div style={{ marginTop: '0.75rem', padding: '0.6rem', borderRadius: '6px', fontSize: '0.8rem', background: plunetAuthTest.success ? '#ecfdf5' : '#fee2e2' }}>
                  {plunetAuthTest.success ? (
                    <div>
                      <div style={{ color: '#065f46', fontWeight: 600 }}>Authenticated Successfully</div>
                      <div style={{ fontFamily: 'monospace', fontSize: '0.75rem', marginTop: '0.2rem' }}>
                        UUID: {plunetAuthTest.session_uuid}
                      </div>
                    </div>
                  ) : (
                    <div style={{ color: '#991b1b' }}>Failed: {plunetAuthTest.error || plunetAuthTest.message}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Execution History & Details */}
        <div>
          <div className="card">
            {/* Tabs */}
            <div className="tabs">
              <button
                className={`tab-btn ${activeTab === 'jobs' ? 'active' : ''}`}
                onClick={() => setActiveTab('jobs')}
              >
                ETL Execution Jobs ({jobs.length})
              </button>
              <button
                className={`tab-btn ${activeTab === 'deliveries' ? 'active' : ''}`}
                onClick={() => setActiveTab('deliveries')}
              >
                Destination Deliveries ({deliveries.length})
              </button>
            </div>

            {/* Tab 1: Jobs Table */}
            {activeTab === 'jobs' && (
              <div className="table-container">
                {jobs.length === 0 ? (
                  <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--slate-500)' }}>
                    No ETL jobs executed yet. Select a source on the left and run the pipeline!
                  </div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Job ID</th>
                        <th>Name</th>
                        <th>Languages</th>
                        <th>Words / Segments</th>
                        <th>Plunet Sync</th>
                        <th>Destination</th>
                        <th>Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id}>
                          <td><strong>#{j.id}</strong></td>
                          <td>{j.job_name}</td>
                          <td>
                            <span className="badge badge-info">{j.source_language} &rarr; {j.target_language}</span>
                          </td>
                          <td>{j.word_count} w / {j.segment_count} segs</td>
                          <td>
                            {j.plunet_synced === 'SYNCED' ? (
                              <span className="badge badge-success">Order #{j.plunet_order_id}</span>
                            ) : (
                              <span className="badge badge-warning">{j.plunet_synced}</span>
                            )}
                          </td>
                          <td>
                            <span className={`badge ${j.destination_status_code === 200 ? 'badge-success' : 'badge-danger'}`}>
                              HTTP {j.destination_status_code || '---'}
                            </span>
                          </td>
                          <td>
                            <span className={`badge ${j.status === 'COMPLETED' ? 'badge-success' : 'badge-warning'}`}>
                              {j.status}
                            </span>
                          </td>
                          <td>
                            <button
                              className="btn btn-outline"
                              style={{ width: 'auto', padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                              onClick={() => handleViewJob(j.id)}
                            >
                              <Eye size={12} />
                              <span>View</span>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* Tab 2: Destination Deliveries */}
            {activeTab === 'deliveries' && (
              <div className="table-container">
                {deliveries.length === 0 ? (
                  <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--slate-500)' }}>
                    No payloads received on destination server yet.
                  </div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Delivery #</th>
                        <th>Job ID</th>
                        <th>Source File</th>
                        <th>Language Pair</th>
                        <th>Segments</th>
                        <th>Payload Size</th>
                        <th>Received At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deliveries.map((d) => (
                        <tr key={d.id}>
                          <td><strong>Deliv #{d.id}</strong></td>
                          <td>Job #{d.job_id}</td>
                          <td>{d.source_filename}</td>
                          <td>{d.source_language} &rarr; {d.target_language}</td>
                          <td>{d.segment_count} segs ({d.word_count} w)</td>
                          <td>{(d.payload_size / 1024).toFixed(1)} KB</td>
                          <td>{new Date(d.received_at).toLocaleTimeString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>

          {/* Selected Job Inspection Detail */}
          {selectedJob && (
            <div className="card" style={{ marginTop: '1.5rem' }}>
              <div className="card-title">
                <span>Job Inspection: {selectedJob.job_name}</span>
                <span className="badge badge-success">{selectedJob.status}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)' }}>Plunet Order ID</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary)' }}>
                    {selectedJob.plunet_order_id ? `#${selectedJob.plunet_order_id}` : 'N/A'}
                  </div>
                </div>

                <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)' }}>Total Words</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>{selectedJob.word_count}</div>
                </div>

                <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)' }}>Total Segments</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>{selectedJob.segment_count}</div>
                </div>

                <div style={{ background: 'var(--slate-50)', padding: '0.75rem', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)' }}>Destination Delivery</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#10b981' }}>
                    HTTP {selectedJob.destination_status_code} OK
                  </div>
                </div>
              </div>

              {/* Segments Preview */}
              {selectedJob.segments && selectedJob.segments.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <h4 style={{ fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--slate-800)' }}>
                    Extracted Translation Units ({selectedJob.segments.length})
                  </h4>
                  <div className="table-container" style={{ maxHeight: '240px', overflowY: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Unit ID</th>
                          <th>Source ({selectedJob.source_language})</th>
                          <th>Target ({selectedJob.target_language})</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedJob.segments.map((seg, idx) => (
                          <tr key={idx}>
                            <td><code>{seg.unit_id}</code></td>
                            <td style={{ maxWidth: '280px' }}>{seg.source_text}</td>
                            <td style={{ maxWidth: '280px', color: '#047857' }}>{seg.target_text || '—'}</td>
                            <td><span className="badge badge-success">{seg.status || 'translated'}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Processed XLIFF Preview */}
              {selectedJob.processed_xliff && (
                <div style={{ marginTop: '1rem' }}>
                  <h4 style={{ fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--slate-800)' }}>
                    Transformed XLIFF XML Payload
                  </h4>
                  <pre className="xml-preview">
                    {selectedJob.processed_xliff.slice(0, 1500)}
                    {selectedJob.processed_xliff.length > 1500 && '\n... [truncated]'}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer>
        FOX MLO &copy; {new Date().getFullYear()} Fox Translations &bull; FastAPI + UV + React + PostgreSQL + Plunet SOAP API
      </footer>
    </div>
  );
}
