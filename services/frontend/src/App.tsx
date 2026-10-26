import React, { useState, useEffect } from 'react';
import './App.css';
import {
  Database,
  Server,
  Play,
  RotateCw,
  FileCode,
  AlertCircle,
  ExternalLink,
  Eye
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
  const [activeTab, setActiveTab] = useState<'jobs' | 'deliveries'>('jobs');
  const [selectedJob, setSelectedJob] = useState<ETLJob | null>(null);

  // Form inputs
  const [sourceType, setSourceType] = useState<'fixture' | 'api'>('fixture');
  const [selectedFixture, setSelectedFixture] = useState('example.fr.xlf');
  const [apiUrl, setApiUrl] = useState('');
  const [destinationUrl, setDestinationUrl] = useState('http://backend:8000/api/v1/etl/simulate-destination');
  const [syncPlunet, setSyncPlunet] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [plunetAuthTest, setPlunetAuthTest] = useState<any>(null);
  const [testingPlunet, setTestingPlunet] = useState(false);

  // Fetch initial data
  const fetchData = async () => {
    try {
      const healthRes = await fetch('/api/v1/health');
      if (healthRes.ok) setHealth(await healthRes.json());

      const fixturesRes = await fetch('/api/v1/xliff/fixtures');
      if (fixturesRes.ok) {
        const data = await fixturesRes.json();
        setFixtures(data);
        if (data.length > 0 && !selectedFixture) {
          setSelectedFixture(data[0].filename);
        }
      }

      const jobsRes = await fetch('/api/v1/etl/jobs');
      if (jobsRes.ok) setJobs(await jobsRes.json());

      const delivRes = await fetch('/api/v1/etl/destination-deliveries');
      if (delivRes.ok) setDeliveries(await delivRes.json());
    } catch (err) {
      console.error('Error fetching data:', err);
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
      setErrorMessage(err.message || 'Error occurred during ETL pipeline execution');
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
      {/* Swiss Navigation Bar */}
      <header className="navbar">
        <div className="brand">
          <div className="brand-badge">FOX</div>
          <div>
            <div className="brand-title">FOX MLO</div>
            <div className="brand-sub">Translation ETL &amp; Plunet Orchestrator</div>
          </div>
        </div>

        {/* Live System Status Badges */}
        <div className="system-status">
          <div className={`status-badge ${health?.database === 'HEALTHY' ? 'online' : 'warning'}`}>
            <Database size={13} />
            <span>POSTGRES: {health?.database === 'HEALTHY' ? 'ONLINE' : 'CONNECTING'}</span>
          </div>

          <div className={`status-badge ${health?.plunet?.success ? 'online' : 'warning'}`}>
            <Server size={13} />
            <span>PLUNET: {health?.plunet?.version ? `v${health.plunet.version}` : '10.26.2'}</span>
          </div>

          <button className="btn btn-outline btn-sm" onClick={fetchData} title="Refresh Live Data">
            <RotateCw size={12} />
            <span>SYNC</span>
          </button>
        </div>
      </header>

      {/* Swiss Poster Hero Section */}
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-meta-tag">
            DESIGN.MD // MINIMALISM &amp; SWISS STYLE // GRID SPECIFICATION
          </div>
          <h1>
            Welcome to <span>FOX MLO</span>
          </h1>
          <p>
            Objective, grid-based localization transport linking remote XLIFF data sources, Plunet BusinessManager SOAP API (portal.foxtranslations.com), and downstream destination endpoints.
          </p>

          {/* Sequential Process Grid */}
          <div className="pipeline-bar">
            <div className="pipeline-step-item">
              <span className="step-num">PHASE 01</span>
              <span className="step-name">EXTRACT</span>
              <span className="step-desc">Acquire XLIFF via API / Fixture</span>
            </div>
            <div className="pipeline-step-item">
              <span className="step-num">PHASE 02</span>
              <span className="step-name">TRANSFORM</span>
              <span className="step-desc">Parse segments &amp; validate tags</span>
            </div>
            <div className="pipeline-step-item">
              <span className="step-num">PHASE 03</span>
              <span className="step-name">SYNCHRONIZE</span>
              <span className="step-desc">Plunet SOAP order registration</span>
            </div>
            <div className="pipeline-step-item">
              <span className="step-num">PHASE 04</span>
              <span className="step-name">DELIVER</span>
              <span className="step-desc">Transport to destination server</span>
            </div>
          </div>
        </div>
      </section>

      {/* Main Grid Workspace */}
      <main className="main-content">
        {/* Left Column: Pipeline Execution Controls */}
        <div>
          <div className="card">
            <div className="card-header">
              <span className="card-title">Execution Controls</span>
              <FileCode size={16} color="var(--accent-swiss)" />
            </div>

            <form onSubmit={handleRunETL}>
              {/* Source Type */}
              <div className="form-group">
                <label className="form-label">Data Extraction Source</label>
                <select
                  className="form-select"
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as any)}
                >
                  <option value="fixture">Local Fixture (XLIFF 1.2 Specification)</option>
                  <option value="api">External REST API Source</option>
                </select>
                <span className="form-help">SELECT DATA ORIGIN FOR PROCESSING</span>
              </div>

              {/* Source Details */}
              {sourceType === 'fixture' ? (
                <div className="form-group">
                  <label className="form-label">XLIFF Sample File</label>
                  <select
                    className="form-select"
                    value={selectedFixture}
                    onChange={(e) => setSelectedFixture(e.target.value)}
                  >
                    {fixtures.map((f) => (
                      <option key={f.filename} value={f.filename}>
                        {f.filename} [{f.source_language} &rarr; {f.target_language}] ({f.word_count} words)
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="form-group">
                  <label className="form-label">Remote API Endpoint</label>
                  <input
                    type="url"
                    className="form-input"
                    placeholder="https://api.translations.com/v1/job-101.xlf"
                    value={apiUrl}
                    onChange={(e) => setApiUrl(e.target.value)}
                    required
                  />
                </div>
              )}

              {/* Destination URL */}
              <div className="form-group">
                <label className="form-label">Destination Server Endpoint</label>
                <input
                  type="text"
                  className="form-input"
                  value={destinationUrl}
                  onChange={(e) => setDestinationUrl(e.target.value)}
                  required
                />
                <span className="form-help">TARGET SERVER RECEIVING TRANSFORMED PAYLOAD</span>
              </div>

              {/* Plunet Synchronization Checkbox */}
              <div className="checkbox-row">
                <input
                  type="checkbox"
                  id="syncPlunet"
                  checked={syncPlunet}
                  onChange={(e) => setSyncPlunet(e.target.checked)}
                />
                <label htmlFor="syncPlunet" className="checkbox-label">
                  Synchronize with Plunet BusinessManager (SOAP 1.2)
                </label>
              </div>

              {/* Error Alert Box */}
              {errorMessage && (
                <div className="alert-box">
                  <AlertCircle size={15} />
                  <span>{errorMessage}</span>
                </div>
              )}

              {/* Submit Button */}
              <div style={{ marginTop: '1.25rem' }}>
                <button type="submit" className="btn btn-primary" disabled={isRunning}>
                  {isRunning ? (
                    <>
                      <RotateCw size={14} className="spin" />
                      <span>EXECUTING ETL PIPELINE...</span>
                    </>
                  ) : (
                    <>
                      <Play size={14} />
                      <span>DISPATCH PIPELINE</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Plunet Connection Inspector Card */}
          <div className="card" style={{ marginTop: '1.5rem' }}>
            <div className="card-header">
              <span className="card-title">Plunet SOAP Status</span>
              <ExternalLink size={15} color="var(--text-muted)" />
            </div>

            <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
              <div style={{ marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>HOST:</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>portal.foxtranslations.com</span>
              </div>
              <div style={{ marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>VERSION:</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>10.26.2 (Active)</span>
              </div>
              <div style={{ marginBottom: '1.25rem', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>API USER:</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>API integration</span>
              </div>

              <button
                type="button"
                className="btn btn-outline"
                onClick={handleTestPlunetAuth}
                disabled={testingPlunet}
              >
                {testingPlunet ? 'AUTHENTICATING...' : 'TEST AUTHENTICATION'}
              </button>

              {plunetAuthTest && (
                <div style={{ marginTop: '0.875rem', padding: '0.75rem', border: '1px solid var(--border-hairline)', background: plunetAuthTest.success ? '#F0FDF4' : '#FFF1F2' }}>
                  {plunetAuthTest.success ? (
                    <div>
                      <div style={{ color: 'var(--success-swiss)', fontWeight: 700, fontSize: '0.75rem', textTransform: 'uppercase' }}>
                        &bull; SESSION ACTIVE &amp; AUTHENTICATED
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', marginTop: '0.35rem', color: 'var(--text-secondary)' }}>
                        UUID: {plunetAuthTest.session_uuid}
                      </div>
                    </div>
                  ) : (
                    <div style={{ color: 'var(--accent-swiss)', fontSize: '0.75rem' }}>
                      REFUSED: {plunetAuthTest.error || plunetAuthTest.message}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Execution History & Inspection */}
        <div>
          <div className="card">
            {/* Swiss Underline Tabs */}
            <div className="tabs-container">
              <button
                className={`tab-btn ${activeTab === 'jobs' ? 'active' : ''}`}
                onClick={() => setActiveTab('jobs')}
              >
                EXECUTION JOBS ({jobs.length})
              </button>
              <button
                className={`tab-btn ${activeTab === 'deliveries' ? 'active' : ''}`}
                onClick={() => setActiveTab('deliveries')}
              >
                DESTINATION RECEIPTS ({deliveries.length})
              </button>
            </div>

            {/* Tab 1: Execution Jobs Table */}
            {activeTab === 'jobs' && (
              <div className="table-wrap">
                {jobs.length === 0 ? (
                  <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>
                    NO JOBS EXECUTED YET. TRIGGER PIPELINE FROM LEFT PANEL.
                  </div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>JOB IDENTIFIER</th>
                        <th>PAIR</th>
                        <th>VOLUME</th>
                        <th>PLUNET</th>
                        <th>DESTINATION</th>
                        <th>STATUS</th>
                        <th>INSPECT</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id}>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>#{j.id}</td>
                          <td style={{ fontWeight: 600 }}>{j.job_name}</td>
                          <td>
                            <span className="tag">{j.source_language} &rarr; {j.target_language}</span>
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{j.word_count}w / {j.segment_count}s</td>
                          <td>
                            {j.plunet_synced === 'SYNCED' ? (
                              <span className="tag tag-success">#{j.plunet_order_id}</span>
                            ) : (
                              <span className="tag tag-warning">{j.plunet_synced}</span>
                            )}
                          </td>
                          <td>
                            <span className={`tag ${j.destination_status_code === 200 ? 'tag-success' : 'tag-accent'}`}>
                              HTTP {j.destination_status_code || '---'}
                            </span>
                          </td>
                          <td>
                            <span className={`tag ${j.status === 'COMPLETED' ? 'tag-success' : 'tag-warning'}`}>
                              {j.status}
                            </span>
                          </td>
                          <td>
                            <button
                              className="btn btn-outline btn-sm"
                              onClick={() => handleViewJob(j.id)}
                            >
                              <Eye size={12} />
                              <span>VIEW</span>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* Tab 2: Destination Server Deliveries */}
            {activeTab === 'deliveries' && (
              <div className="table-wrap">
                {deliveries.length === 0 ? (
                  <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>
                    DESTINATION SERVER HAS NOT RECEIVED DELIVERIES YET.
                  </div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>RECEIPT</th>
                        <th>JOB REF</th>
                        <th>FILE IDENTIFIER</th>
                        <th>LANGUAGE PAIR</th>
                        <th>SEGMENTS</th>
                        <th>PAYLOAD</th>
                        <th>TIMESTAMP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deliveries.map((d) => (
                        <tr key={d.id}>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>REC-{d.id}</td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>JOB-{d.job_id}</td>
                          <td style={{ fontWeight: 600 }}>{d.source_filename}</td>
                          <td><span className="tag">{d.source_language} &rarr; {d.target_language}</span></td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{d.segment_count} segs ({d.word_count} w)</td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{(d.payload_size / 1024).toFixed(1)} KB</td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{new Date(d.received_at).toLocaleTimeString()}</td>
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
            <div className="card" style={{ marginTop: '1.5rem', borderTop: '2px solid var(--border-strong)' }}>
              <div className="card-header">
                <div>
                  <span className="card-title">INSPECTION // {selectedJob.job_name}</span>
                </div>
                <span className="tag tag-success">{selectedJob.status}</span>
              </div>

              {/* Swiss Metric Grid */}
              <div className="metric-grid">
                <div className="metric-cell">
                  <div className="metric-label">PLUNET ORDER</div>
                  <div className="metric-value" style={{ color: 'var(--accent-swiss)' }}>
                    {selectedJob.plunet_order_id ? `#${selectedJob.plunet_order_id}` : 'N/A'}
                  </div>
                </div>

                <div className="metric-cell">
                  <div className="metric-label">TOTAL WORDS</div>
                  <div className="metric-value">{selectedJob.word_count}</div>
                </div>

                <div className="metric-cell">
                  <div className="metric-label">TOTAL SEGMENTS</div>
                  <div className="metric-value">{selectedJob.segment_count}</div>
                </div>

                <div className="metric-cell">
                  <div className="metric-label">DESTINATION STATUS</div>
                  <div className="metric-value" style={{ color: 'var(--success-swiss)' }}>
                    HTTP {selectedJob.destination_status_code}
                  </div>
                </div>
              </div>

              {/* Translation Segments Table */}
              {selectedJob.segments && selectedJob.segments.length > 0 && (
                <div style={{ marginTop: '1.25rem' }}>
                  <div style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
                    EXTRACTED SEGMENTS [{selectedJob.segments.length}]
                  </div>
                  <div className="table-wrap" style={{ maxHeight: '260px', overflowY: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>UNIT</th>
                          <th>SOURCE [{selectedJob.source_language}]</th>
                          <th>TARGET [{selectedJob.target_language}]</th>
                          <th>STATUS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedJob.segments.map((seg, idx) => (
                          <tr key={idx}>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{seg.unit_id}</td>
                            <td style={{ maxWidth: '280px' }}>{seg.source_text}</td>
                            <td style={{ maxWidth: '280px', color: 'var(--success-swiss)' }}>{seg.target_text || '—'}</td>
                            <td><span className="tag tag-success">{seg.status || 'translated'}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Raw Processed XLIFF Code View */}
              {selectedJob.processed_xliff && (
                <div style={{ marginTop: '1.25rem' }}>
                  <div style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
                    DELIVERED XLIFF XML PAYLOAD
                  </div>
                  <pre className="xml-box">
                    {selectedJob.processed_xliff.slice(0, 1600)}
                    {selectedJob.processed_xliff.length > 1600 && '\n... [TRUNCATED]'}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {/* Swiss Minimalist Footer */}
      <footer>
        <div className="footer-inner">
          <div className="footer-mono">
            FOX MLO &bull; DESIGN.MD SWISS SPECIFICATION &bull; JOSEF MÜLLER-BROCKMANN GRID
          </div>
          <div className="footer-mono">
            FASTAPI // UV // REACT // POSTGRES // PLUNET 10.26.2
          </div>
        </div>
      </footer>
    </div>
  );
}
