import { useI18n } from '../i18n';

export function Loading() {
  const { t } = useI18n();
  return <p className="muted pad">{t('common.loading')}</p>;
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="banner banner--fail" role="alert">
      <strong>{t('common.error')}</strong>
      <span>{error.message}</span>
      {onRetry && (
        <button type="button" className="btn btn--sm" onClick={onRetry}>
          {t('common.retry')}
        </button>
      )}
    </div>
  );
}
