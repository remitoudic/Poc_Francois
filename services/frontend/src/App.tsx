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
  ArrowLeft,
  Copy,
  Download,
  Search,
  Check,
  Link2
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
  const [viewMode, setViewMode] = useState<'dashboard' | 'detail'>('dashboard');
  const [mainTab, setMainTab] = useState<'translations' | 'technical'>('translations');
  const [techSubTab, setTechSubTab] = useState<'processed' | 'raw' | 'audit' | 'json'>('processed');
  const [segmentSearch, setSegmentSearch] = useState('');
  const [copied, setCopied] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  // Form inputs
  const [sourceType, setSourceType] = useState<'fixture' | 'api'>('fixture');
  const [selectedFixture, setSelectedFixture] = useState('example.fr.xlf');
  const [apiUrl, setApiUrl] = useState('');
  const [workflowType, setWorkflowType] = useState('type 1');
  const [destinationUrl, setDestinationUrl] = useState('Wordpress Server 1');
  const [syncPlunet] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [plunetAuthTest, setPlunetAuthTest] = useState<any>(null);
  const [testingPlunet, setTestingPlunet] = useState(false);

  // Load and sync URL route (Base URL / :job_id / :plunet_order_id)
  useEffect(() => {
    const handleUrlRoute = () => {
      const path = window.location.pathname;
      const match = path.match(/^\/(\d+)(?:\/([^/]+))?/);
      if (match) {
        const jobId = parseInt(match[1], 10);
        const plunetOrderId = match[2] && match[2] !== '0' ? match[2] : undefined;
        loadJobDetail(jobId, plunetOrderId, false);
      } else {
        setViewMode('dashboard');
        setSelectedJob(null);
      }
    };

    handleUrlRoute();
    window.addEventListener('popstate', handleUrlRoute);
    return () => window.removeEventListener('popstate', handleUrlRoute);
  }, []);

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

  // View / Open Job Detail Page with /:job_id/:plunet_order URL
  const loadJobDetail = async (jobId: number, plunetOrderId?: string | number, pushState: boolean = true) => {
    try {
      const res = await fetch(`/api/v1/etl/jobs/${jobId}`);
      if (res.ok) {
        const jobData = await res.json();
        setSelectedJob(jobData);
        setViewMode('detail');
        setMainTab('translations');
        setTechSubTab('processed');
        setSegmentSearch('');
        if (pushState) {
          const orderSlug = jobData.plunet_order_id ?? plunetOrderId ?? '0';
          window.history.pushState(null, '', `/${jobId}/${orderSlug}`);
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch (err) {
      console.error('Failed to load job details:', err);
    }
  };

  const handleBackToDashboard = (pushState: boolean = true) => {
    setViewMode('dashboard');
    setSelectedJob(null);
    if (pushState) {
      window.history.pushState(null, '', '/');
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCopyUrl = (jobId: number, plunetOrderId?: number) => {
    const orderSlug = plunetOrderId ?? 0;
    const fullUrl = `${window.location.origin}/${jobId}/${orderSlug}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  // Run ETL Pipeline
  const handleRunETL = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsRunning(true);
    setErrorMessage(null);

    const payload: any = {
      source_type: sourceType,
      destination_url: destinationUrl,
      workflow_type: workflowType,
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
      setViewMode('detail');
      setMainTab('translations');
      setTechSubTab('processed');
      setSegmentSearch('');
      const orderSlug = completedJob.plunet_order_id ?? 0;
      window.history.pushState(null, '', `/${completedJob.id}/${orderSlug}`);
      fetchData();
      window.scrollTo({ top: 0, behavior: 'smooth' });
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

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadXliff = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'application/xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredSegments = (selectedJob?.segments || []).filter((s) => {
    if (!segmentSearch.trim()) return true;
    const query = segmentSearch.toLowerCase();
    return (
      s.unit_id.toLowerCase().includes(query) ||
      (s.resname && s.resname.toLowerCase().includes(query)) ||
      s.source_text.toLowerCase().includes(query) ||
      (s.target_text && s.target_text.toLowerCase().includes(query))
    );
  });

  return (
    <div className="app-container">
      {/* Swiss Navigation Bar */}
      <header className="navbar">
        <div className="brand" style={{ cursor: 'pointer' }} onClick={() => handleBackToDashboard(true)} title="Back to Dashboard">
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

      {/* Main View: Job Detail View or Pipeline Dashboard */}
      {viewMode === 'detail' && selectedJob ? (
        <div className="detail-view">
          {/* Top Bar: Navigation + Shareable URL Pill + Actions */}
          <div className="detail-top-nav">
            <button className="back-btn" onClick={() => handleBackToDashboard(true)}>
              <ArrowLeft size={14} />
              <span>&larr; BACK TO JOBS</span>
            </button>

            {/* Shareable Direct URL Pill: Base URL / :job_id / :plunet_order_id */}
            <div
              className="job-url-pill"
              onClick={() => handleCopyUrl(selectedJob.id, selectedJob.plunet_order_id)}
              title="Click to copy shareable direct URL"
            >
              <Link2 size={13} color="var(--accent-plunet)" />
              <span style={{ color: 'var(--text-muted)' }}>URL:</span>
              <span className="url-text">/{selectedJob.id}/{selectedJob.plunet_order_id || 0}</span>
              <span className="copy-tag">{copiedUrl ? 'COPIED!' : 'COPY LINK'}</span>
            </div>

            <div className="detail-actions">
              {selectedJob.plunet_order_id && (
                <a
                  href="https://portal.foxtranslations.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-outline btn-sm"
                  style={{ width: 'auto' }}
                  title="Open Plunet BusinessManager Portal"
                >
                  <ExternalLink size={12} />
                  <span>PLUNET PORTAL</span>
                </a>
              )}
              {selectedJob.processed_xliff && (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  style={{ width: 'auto' }}
                  onClick={() => handleDownloadXliff(selectedJob.processed_xliff!, `${selectedJob.job_name}.xlf`)}
                >
                  <Download size={12} />
                  <span>DOWNLOAD .XLF</span>
                </button>
              )}
              <button
                type="button"
                className="btn btn-outline btn-sm"
                style={{ width: 'auto' }}
                onClick={() => loadJobDetail(selectedJob.id, selectedJob.plunet_order_id, false)}
                title="Reload latest job state"
              >
                <RotateCw size={12} />
                <span>REFRESH</span>
              </button>
            </div>
          </div>

          {/* Clean Hero Header Card */}
          <div className="detail-header-card">
            <div className="detail-meta-row">
              <div>
                <div className="detail-sub">
                  JOB #{selectedJob.id} &bull; {selectedJob.source_type.toUpperCase()} INGESTION &bull; {new Date(selectedJob.created_at).toLocaleString()}
                </div>
                <h2 className="detail-title">{selectedJob.job_name}</h2>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <span className={`tag ${selectedJob.status === 'COMPLETED' ? 'tag-success' : 'tag-warning'}`}>
                  {selectedJob.status}
                </span>
                {selectedJob.plunet_order_id ? (
                  <span className="tag tag-plunet">
                    PLUNET ORDER #{selectedJob.plunet_order_id}
                  </span>
                ) : (
                  <span className="tag tag-warning">{selectedJob.plunet_synced}</span>
                )}
                <span className="tag tag-pair">
                  {selectedJob.source_language.toUpperCase()} &rarr; {selectedJob.target_language.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Streamlined Minimalist Stepper */}
            <div className="detail-progress-strip">
              <div className="detail-progress-box done">
                <span className="detail-progress-step-num">01</span>
                <div className="detail-progress-text">
                  <span className="detail-progress-title">EXTRACT</span>
                  <span className="detail-progress-desc">{selectedJob.source_reference || selectedJob.job_name}</span>
                </div>
              </div>

              <div className="detail-progress-box done">
                <span className="detail-progress-step-num">02</span>
                <div className="detail-progress-text">
                  <span className="detail-progress-title">VALIDATE</span>
                  <span className="detail-progress-desc">{selectedJob.segment_count} segs ({selectedJob.word_count} words)</span>
                </div>
              </div>

              <div className="detail-progress-box done">
                <span className="detail-progress-step-num">03</span>
                <div className="detail-progress-text">
                  <span className="detail-progress-title">PROCESS</span>
                  <span className="detail-progress-desc">
                    {selectedJob.plunet_order_id ? `Order #${selectedJob.plunet_order_id}` : selectedJob.plunet_synced}
                  </span>
                </div>
              </div>

              <div className="detail-progress-box done">
                <span className="detail-progress-step-num">04</span>
                <div className="detail-progress-text">
                  <span className="detail-progress-title">DELIVER</span>
                  <span className="detail-progress-desc">
                    {selectedJob.destination_url || 'Wordpress Server 1'} (HTTP {selectedJob.destination_status_code || 200})
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* 4 Compact KPIs */}
          <div className="detail-kpi-grid">
            <div className="detail-kpi-card">
              <div className="detail-kpi-label">PLUNET ORDER</div>
              <div className="detail-kpi-val" style={{ color: 'var(--accent-plunet)' }}>
                {selectedJob.plunet_order_id ? `#${selectedJob.plunet_order_id}` : 'N/A'}
              </div>
              <div className="detail-kpi-sub">SOAP 1.2 Connected</div>
            </div>

            <div className="detail-kpi-card">
              <div className="detail-kpi-label">VOLUME METRICS</div>
              <div className="detail-kpi-val">{selectedJob.word_count} Words</div>
              <div className="detail-kpi-sub">{selectedJob.segment_count} translation units</div>
            </div>

            <div className="detail-kpi-card">
              <div className="detail-kpi-label">DESTINATION SERVER</div>
              <div className="detail-kpi-val" style={{ fontSize: '1.05rem' }}>
                {selectedJob.destination_url || 'Wordpress Server 1'}
              </div>
              <div className="detail-kpi-sub" style={{ color: 'var(--success-swiss)' }}>
                HTTP {selectedJob.destination_status_code || 200} Dispatched
              </div>
            </div>

            <div className="detail-kpi-card">
              <div className="detail-kpi-label">PAYLOAD SIZE</div>
              <div className="detail-kpi-val">
                {((selectedJob.processed_xliff?.length || 0) / 1024).toFixed(1)} KB
              </div>
              <div className="detail-kpi-sub">XLIFF 1.2 XML Document</div>
            </div>
          </div>

          {/* Main Content Card: Clean 2-Tab Navigation */}
          <div className="card">
            <div className="detail-main-tab-bar">
              <button
                className={`detail-main-tab-btn ${mainTab === 'translations' ? 'active' : ''}`}
                onClick={() => setMainTab('translations')}
              >
                BILINGUAL TRANSLATIONS ({selectedJob.segments?.length || 0})
              </button>
              <button
                className={`detail-main-tab-btn ${mainTab === 'technical' ? 'active' : ''}`}
                onClick={() => setMainTab('technical')}
              >
                TECHNICAL DETAILS &amp; XML
              </button>
            </div>

            {/* TAB 1: Bilingual Segments */}
            {mainTab === 'translations' && (
              <div>
                <div className="search-bar">
                  <Search size={15} color="var(--text-muted)" />
                  <input
                    type="text"
                    className="search-input"
                    placeholder="Search translated segments by source text, translation, or unit ID..."
                    value={segmentSearch}
                    onChange={(e) => setSegmentSearch(e.target.value)}
                  />
                  {segmentSearch && (
                    <button className="btn btn-outline btn-sm" onClick={() => setSegmentSearch('')}>
                      CLEAR
                    </button>
                  )}
                  <span className="tag" style={{ marginLeft: 'auto' }}>
                    SHOWING {filteredSegments.length} OF {selectedJob.segments?.length || 0}
                  </span>
                </div>

                <div className="bilingual-table-wrap">
                  <table className="bilingual-table">
                    <thead>
                      <tr>
                        <th style={{ width: '1%', textAlign: 'center' }}>#</th>
                        <th style={{ width: '14%' }}>RESOURCE / KEY</th>
                        <th style={{ width: '42%' }}>
                          SOURCE [{selectedJob.source_language.toUpperCase()}]
                        </th>
                        <th style={{ width: '42%' }}>
                          TARGET [{selectedJob.target_language.toUpperCase()}]
                        </th>
                        <th style={{ width: '1%', textAlign: 'center' }}>STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSegments.length === 0 ? (
                        <tr>
                          <td colSpan={5} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                            No segments match "{segmentSearch}".
                          </td>
                        </tr>
                      ) : (
                        filteredSegments.map((s, idx) => (
                          <tr key={s.unit_id || idx}>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, textAlign: 'center' }}>
                              {s.unit_id}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                              {s.resname || '---'}
                            </td>
                            <td className="source-cell">
                              {s.source_text}
                            </td>
                            <td className="target-cell">
                              {s.target_text || <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Pending translation</span>}
                            </td>
                            <td style={{ textAlign: 'center' }}>
                              <span className="tag tag-success" style={{ fontSize: '0.625rem' }}>
                                {s.status || 'translated'}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB 2: Technical & XML */}
            {mainTab === 'technical' && (
              <div>
                <div className="tabs-container" style={{ marginBottom: '1.25rem' }}>
                  <button
                    className={`tab-btn ${techSubTab === 'processed' ? 'active' : ''}`}
                    onClick={() => setTechSubTab('processed')}
                  >
                    PROCESSED XLIFF (XML)
                  </button>
                  <button
                    className={`tab-btn ${techSubTab === 'raw' ? 'active' : ''}`}
                    onClick={() => setTechSubTab('raw')}
                  >
                    RAW SOURCE XLIFF
                  </button>
                  <button
                    className={`tab-btn ${techSubTab === 'audit' ? 'active' : ''}`}
                    onClick={() => setTechSubTab('audit')}
                  >
                    AUDIT LOGS
                  </button>
                  <button
                    className={`tab-btn ${techSubTab === 'json' ? 'active' : ''}`}
                    onClick={() => setTechSubTab('json')}
                  >
                    RAW JSON SPEC
                  </button>
                </div>

                {techSubTab === 'processed' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
                        DISPATCHED XLIFF 1.2 PAYLOAD
                      </span>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => handleCopy(selectedJob.processed_xliff || '')}
                        >
                          {copied ? <Check size={12} /> : <Copy size={12} />}
                          <span>{copied ? 'COPIED!' : 'COPY XML'}</span>
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => handleDownloadXliff(selectedJob.processed_xliff || '', `${selectedJob.job_name}.xlf`)}
                        >
                          <Download size={12} />
                          <span>DOWNLOAD .XLF</span>
                        </button>
                      </div>
                    </div>
                    <pre className="xml-box" style={{ maxHeight: '440px' }}>
                      {selectedJob.processed_xliff || 'No processed XLIFF payload available.'}
                    </pre>
                  </div>
                )}

                {techSubTab === 'raw' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
                        ORIGINAL SOURCE XLIFF
                      </span>
                      <button
                        className="btn btn-outline btn-sm"
                        onClick={() => handleCopy(selectedJob.raw_xliff || '')}
                      >
                        {copied ? <Check size={12} /> : <Copy size={12} />}
                        <span>{copied ? 'COPIED!' : 'COPY RAW XML'}</span>
                      </button>
                    </div>
                    <pre className="xml-box" style={{ maxHeight: '440px' }}>
                      {selectedJob.raw_xliff || 'No raw XLIFF payload stored.'}
                    </pre>
                  </div>
                )}

                {techSubTab === 'audit' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
                    <div style={{ border: '1px solid var(--border-hairline)', padding: '1.25rem' }}>
                      <div className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Server size={15} color="var(--accent-plunet)" />
                        <span>Plunet BusinessManager Audit</span>
                      </div>
                      <div style={{ fontSize: '0.8125rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div><span style={{ color: 'var(--text-muted)' }}>SOAP Endpoint: </span><span style={{ fontFamily: 'var(--font-mono)' }}>https://portal.foxtranslations.com/</span></div>
                        <div><span style={{ color: 'var(--text-muted)' }}>Plunet Version: </span><span style={{ fontFamily: 'var(--font-mono)' }}>10.26.2</span></div>
                        <div><span style={{ color: 'var(--text-muted)' }}>Order ID: </span><span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--accent-plunet)' }}>#{selectedJob.plunet_order_id || 'N/A'}</span></div>
                        <div><span style={{ color: 'var(--text-muted)' }}>Sync Status: </span><span className="tag tag-success">{selectedJob.plunet_synced}</span></div>
                      </div>
                    </div>

                    <div style={{ border: '1px solid var(--border-hairline)', padding: '1.25rem' }}>
                      <div className="card-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Database size={15} color="var(--success-swiss)" />
                        <span>Destination Dispatch Audit</span>
                      </div>
                      <div style={{ fontSize: '0.8125rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div><span style={{ color: 'var(--text-muted)' }}>Target Server: </span><span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{selectedJob.destination_url || 'Wordpress Server 1'}</span></div>
                        <div><span style={{ color: 'var(--text-muted)' }}>HTTP Status: </span><span className="tag tag-success">HTTP {selectedJob.destination_status_code || 200}</span></div>
                        <div><span style={{ color: 'var(--text-muted)' }}>Source Reference: </span><span style={{ fontFamily: 'var(--font-mono)' }}>{selectedJob.source_reference || selectedJob.job_name}</span></div>
                        <div><span style={{ color: 'var(--text-muted)' }}>Timestamp: </span><span style={{ fontFamily: 'var(--font-mono)' }}>{new Date(selectedJob.created_at).toISOString()}</span></div>
                      </div>
                    </div>
                  </div>
                )}

                {techSubTab === 'json' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
                        RAW JOB JSON SPECIFICATION
                      </span>
                      <button
                        className="btn btn-outline btn-sm"
                        onClick={() => handleCopy(JSON.stringify(selectedJob, null, 2))}
                      >
                        {copied ? <Check size={12} /> : <Copy size={12} />}
                        <span>{copied ? 'COPIED!' : 'COPY JSON'}</span>
                      </button>
                    </div>
                    <pre className="xml-box" style={{ maxHeight: '440px' }}>
                      {JSON.stringify(selectedJob, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          {/* Swiss Poster Hero Section */}
          <section className="hero">
            <div className="hero-inner">
              <div className="hero-meta-tag">
                FOX TRANSLATIONS // ETL PIPELINE SYSTEM // PLUNET API v10.26.2
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
                  <span className="step-name">VALIDATE</span>
                  <span className="step-desc">Parse segments &amp; validate tags</span>
                </div>
                <div className="pipeline-step-item">
                  <span className="step-num">PHASE 03</span>
                  <span className="step-name">PROCESS</span>
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
              <FileCode size={16} color="var(--accent-plunet)" />
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
                  <label className="form-label">XLIFF file EXPLORER</label>
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

              {/* Workflow Type */}
              <div className="form-group">
                <label className="form-label">Workflow Type</label>
                <select
                  className="form-select"
                  value={workflowType}
                  onChange={(e) => setWorkflowType(e.target.value)}
                >
                  <option value="type 1">Type 1</option>
                  <option value="type 2">Type 2</option>
                  <option value="type 3">Type 3</option>
                </select>
                <span className="form-help">WORKFLOW PRESET CONFIGURATION</span>
              </div>

              {/* Destination URL */}
              <div className="form-group">
                <label className="form-label">Destination Server Endpoint</label>
                <select
                  className="form-select"
                  value={destinationUrl}
                  onChange={(e) => setDestinationUrl(e.target.value)}
                >
                  <option value="Wordpress Server 1">Wordpress Server 1</option>
                  <option value="Wordpress Server 2">Wordpress Server 2</option>
                </select>
                <span className="form-help">TARGET SERVER RECEIVING TRANSFORMED PAYLOAD</span>
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
                <div style={{ marginTop: '0.875rem', padding: '0.75rem', border: '1px solid var(--border-hairline)', background: plunetAuthTest.success ? '#F0FDF4' : 'var(--danger-tint)' }}>
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
                    <div style={{ color: 'var(--danger-swiss)', fontSize: '0.75rem' }}>
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
                        <th className="th-id">ID</th>
                        <th>JOB IDENTIFIER</th>
                        <th className="text-center">LANGUAGE PAIR</th>
                        <th className="text-center">VOLUME</th>
                        <th className="text-center">PLUNET ORDER</th>
                        <th className="text-center">DESTINATION</th>
                        <th className="text-center">STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr
                          key={j.id}
                          className="clickable-row"
                          onClick={() => loadJobDetail(j.id, j.plunet_order_id, true)}
                          title="Click row to open detailed job breakdown"
                        >
                          <td className="td-id">#{j.id}</td>
                          <td className="td-job-name" title={j.job_name}>{j.job_name}</td>
                          <td className="text-center">
                            <span className="tag tag-pair">{j.source_language} &rarr; {j.target_language}</span>
                          </td>
                          <td className="text-center" style={{ fontFamily: 'var(--font-mono)' }}>
                            {j.word_count}w &bull; {j.segment_count}s
                          </td>
                          <td className="text-center">
                            {j.plunet_synced === 'SYNCED' ? (
                              <span className="tag tag-plunet">#{j.plunet_order_id}</span>
                            ) : (
                              <span className="tag tag-warning">{j.plunet_synced}</span>
                            )}
                          </td>
                          <td className="text-center">
                            <span className={`tag ${j.destination_status_code === 200 ? 'tag-success' : 'tag-accent'}`}>
                              HTTP {j.destination_status_code || '---'}
                            </span>
                          </td>
                          <td className="text-center">
                            <span className={`tag ${j.status === 'COMPLETED' ? 'tag-success' : 'tag-warning'}`}>
                              {j.status}
                            </span>
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
                        <th className="th-id">RECEIPT</th>
                        <th className="text-center">JOB REF</th>
                        <th>FILE IDENTIFIER</th>
                        <th className="text-center">LANGUAGE PAIR</th>
                        <th className="text-center">SEGMENTS</th>
                        <th className="text-center">PAYLOAD</th>
                        <th className="text-center">TIMESTAMP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deliveries.map((d) => (
                        <tr
                          key={d.id}
                          className="clickable-row"
                          onClick={() => loadJobDetail(d.job_id, undefined, true)}
                          title="Click row to open job breakdown"
                        >
                          <td className="td-id">REC-{d.id}</td>
                          <td className="text-center" style={{ fontFamily: 'var(--font-mono)' }}>JOB-{d.job_id}</td>
                          <td className="td-job-name" title={d.source_filename}>{d.source_filename}</td>
                          <td className="text-center"><span className="tag tag-pair">{d.source_language} &rarr; {d.target_language}</span></td>
                          <td className="text-center" style={{ fontFamily: 'var(--font-mono)' }}>{d.segment_count} segs ({d.word_count} w)</td>
                          <td className="text-center" style={{ fontFamily: 'var(--font-mono)' }}>{(d.payload_size / 1024).toFixed(1)} KB</td>
                          <td className="text-center" style={{ fontFamily: 'var(--font-mono)' }}>{new Date(d.received_at).toLocaleTimeString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  )}

      {/* Swiss Minimalist Footer */}
      <footer>
        <div className="footer-inner">
          <div className="footer-mono">
            FOX MLO &bull; ENTERPRISE LOCALIZATION PIPELINE
          </div>
          <div className="footer-mono">
            FASTAPI // UV // REACT // POSTGRES // PLUNET 10.26.2
          </div>
        </div>
      </footer>
    </div>
  );
}
