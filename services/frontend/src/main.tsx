import { lazy, StrictMode, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import './index.css';
import { Layout } from './components/Layout';
import { I18nProvider } from './i18n';
import { LegacyRedirect } from './LegacyRedirect';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { NewOrderPage } from './pages/NewOrderPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { OrderDetailPage } from './pages/OrderDetailPage';
import { OrdersPage } from './pages/OrdersPage';
import { WorkflowPage } from './pages/WorkflowPage';

// The v1 ETL dashboard keeps its own stylesheet; load it only when visited.
const LegacyApp = lazy(() => import('./App'));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/legacy/*" element={<Suspense fallback={null}><LegacyApp /></Suspense>} />
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/orders" replace />} />
            <Route path="orders" element={<OrdersPage />} />
            <Route path="orders/new" element={<NewOrderPage />} />
            <Route path="orders/:orderId" element={<OrderDetailPage />} />
            <Route path="orders/:orderId/positions/:positionId" element={<WorkflowPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path=":jobId/:rest?" element={<LegacyRedirect />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </I18nProvider>
  </StrictMode>,
);
