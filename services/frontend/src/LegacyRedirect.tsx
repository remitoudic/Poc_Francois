import { Navigate, useParams } from 'react-router-dom';

/** v1 deep links were /:jobId/:plunetOrderId; the v1 dashboard now lives under /legacy. */
export function LegacyRedirect() {
  const { jobId, rest } = useParams();
  if (!jobId || !/^\d+$/.test(jobId)) return <Navigate to="/orders" replace />;
  return <Navigate to={`/legacy/${jobId}${rest ? `/${rest}` : ''}`} replace />;
}
