import { NavLink, Outlet } from 'react-router-dom';
import { api } from '../api';
import { useResource } from '../hooks/useResource';
import { useI18n, type Lang } from '../i18n';

interface Health {
  database?: string;
  temporal?: string;
  polylang?: string;
  plunet?: { success?: boolean };
}

async function loadHealth(): Promise<boolean> {
  const res = await fetch('/api/v1/health');
  if (!res.ok) return false;
  const h = (await res.json()) as Health;
  return [h.database, h.temporal, h.polylang].every((s) => s === 'HEALTHY') && !!h.plunet?.success;
}

export function Layout() {
  const { t, lang, setLang } = useI18n();
  const health = useResource(loadHealth, []);
  const healthy = health.data === true;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__inner">
          <NavLink to="/orders" className="brand">
            <span className="brand__badge">FOX</span>
            <span className="brand__name">{t('app.name')}</span>
          </NavLink>
          <nav aria-label="Main" className="topnav">
            <NavLink to="/orders" className="topnav__link">{t('nav.orders')}</NavLink>
            <NavLink to="/analytics" className="topnav__link">{t('nav.analytics')}</NavLink>
            <NavLink to="/legacy" className="topnav__link topnav__link--quiet">{t('nav.legacy')}</NavLink>
          </nav>
          {api.mode === 'mock' && (
            <span className="demo-badge" title={t('demo.title')}>{t('demo.badge')}</span>
          )}
          {!health.loading && (
            <span className="health">
              <span className={`dot ${healthy ? 'tone-bg--done' : 'tone-bg--wait'}`} aria-hidden="true" />
              {healthy ? t('health.ok') : t('health.degraded')}
            </span>
          )}
          <div role="group" aria-label={t('nav.language')} className="seg">
            {(['en', 'fr'] as Lang[]).map((l) => (
              <button key={l} type="button" aria-pressed={lang === l} className="seg__btn" onClick={() => setLang(l)}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}
