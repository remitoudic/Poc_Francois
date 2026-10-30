import { Link } from 'react-router-dom';
import { useI18n } from '../i18n';

export function NotFoundPage() {
  const { t } = useI18n();
  return (
    <div className="stack-md pad-lg">
      <span className="label">404</span>
      <h1 className="h1">{t('notFound.title')}</h1>
      <Link to="/orders" className="btn btn--primary">{t('notFound.back')}</Link>
    </div>
  );
}
