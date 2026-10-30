import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError, type Destination, type OrderKind } from '../api';
import { ErrorState } from '../components/Feedback';
import { useResource } from '../hooks/useResource';
import { useI18n } from '../i18n';

const STEPS = ['basics', 'source', 'workflow', 'review'] as const;
const DESTINATIONS: Destination[] = ['POLYLANG', 'ENDPOINT', 'NONE'];

function defaultDeadline(): string {
  const d = new Date(Date.now() + 7 * 24 * 3600_000);
  return d.toISOString().slice(0, 10);
}

export function NewOrderPage() {
  const { t, fmt } = useI18n();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [kind, setKind] = useState<OrderKind>('ORDER');
  const [title, setTitle] = useState('');
  const [customerId, setCustomerId] = useState<number>();
  const [pmId, setPmId] = useState<number>();
  const [deadline, setDeadline] = useState(defaultDeadline);
  const [site, setSite] = useState<string>();
  const [sourceLang, setSourceLang] = useState<string>();
  const [postIds, setPostIds] = useState<number[]>([]);
  const [targets, setTargets] = useState<string[]>([]);
  const [templateCode, setTemplateCode] = useState('standard');
  const [destination, setDestination] = useState<Destination>('POLYLANG');
  const [destinationUrl, setDestinationUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<Error>();

  const customers = useResource(() => api.listCustomers(), []);
  const pms = useResource(() => api.listResources(), []);
  const templates = useResource(() => api.listTemplates(), []);
  const sites = useResource(() => api.listSites(), []);
  const languages = useResource(() => (site ? api.listLanguages(site) : Promise.resolve([])), [site]);
  const posts = useResource(() => (site && sourceLang ? api.listPosts(site, sourceLang) : Promise.resolve([])), [site, sourceLang]);

  // Defaults once reference data arrives.
  useEffect(() => setCustomerId((v) => v ?? customers.data?.[0]?.id), [customers.data]);
  useEffect(() => setPmId((v) => v ?? pms.data?.[0]?.id), [pms.data]);
  useEffect(() => setSite((v) => v ?? sites.data?.[0]), [sites.data]);
  useEffect(() => {
    if (!languages.data?.length) return;
    setSourceLang((v) => (v && languages.data!.some((l) => l.slug === v) ? v : languages.data![0].slug));
  }, [languages.data]);
  useEffect(() => {
    setPostIds([]);
    setTargets((ts) => ts.filter((l) => l !== sourceLang));
  }, [site, sourceLang]);

  const selectedPosts = useMemo(() => (posts.data ?? []).filter((p) => postIds.includes(p.id)), [posts.data, postIds]);
  const positionCount = selectedPosts.length * targets.length;
  const words = selectedPosts.reduce((n, p) => n + p.words, 0) * targets.length;
  const template = templates.data?.find((tp) => tp.code === templateCode);
  const langName = (slug: string) => languages.data?.find((l) => l.slug === slug)?.name ?? slug;
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const canCreate = positionCount > 0 && customerId && pmId && site && sourceLang;

  async function submit() {
    if (!canCreate) {
      setSubmitError(new Error(t('wizard.validation')));
      return;
    }
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      const order = await api.createOrder({
        kind,
        title: title.trim() || t('wizard.untitled'),
        customer_id: customerId!,
        pm_resource_id: pmId!,
        // A date means the end of that day, in the user's time zone.
        deadline: deadline ? new Date(`${deadline}T23:59:59`).toISOString() : null,
        source_site: site!,
        source_lang: sourceLang!,
        post_ids: postIds,
        target_langs: targets,
        template_code: templateCode,
        destination,
        destination_url: destination === 'ENDPOINT' ? destinationUrl : null,
      });
      navigate(`/orders/${order.id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError || err instanceof Error ? err : new Error(String(err)));
      setSubmitting(false);
    }
  }

  return (
    <div className="stack-md">
      <div className="stack-xs">
        <Link to="/orders" className="crumb">← {t('order.breadcrumb')}</Link>
        <h1 className="h1 h1--sm">{kind === 'QUOTE' ? t('wizard.newQuote') : t('wizard.newOrder')}</h1>
      </div>

      <div className="wizard">
        <ol className="steps" aria-label="Steps">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button type="button" className={`step${i === step ? ' step--current' : ''}`} aria-current={i === step ? 'step' : undefined} onClick={() => setStep(i)}>
                <span className={`step__num${i <= step ? ' step__num--on' : ''}`}>{i < step ? '✓' : i + 1}</span>
                <span className="stack-0">
                  <span className="strong small">{t(`wizard.step.${s}`)}</span>
                  <span className="small muted">{t(`wizard.step.${s}.sub`)}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>

        <section className="card">
          {step === 0 && (
            <div className="pad-lg stack-lg">
              <h2 className="h2">{t('wizard.step.basics')}</h2>
              <fieldset className="fieldset">
                <legend className="label">{t('wizard.type')}</legend>
                <div className="grid-2">
                  {(['ORDER', 'QUOTE'] as const).map((k) => (
                    <button key={k} type="button" aria-pressed={kind === k} className={`choice${kind === k ? ' choice--on' : ''}`} onClick={() => setKind(k)}>
                      <span className="strong">{t(`kind.${k}`)}</span>
                      <span className="small muted">{t(`kind.${k}.plunet`)}</span>
                      <span className="small">{t(k === 'ORDER' ? 'wizard.order.desc' : 'wizard.quote.desc')}</span>
                    </button>
                  ))}
                </div>
              </fieldset>
              <div className="grid-2">
                <label className="field span-2">
                  <span className="label">{t('wizard.title')}</span>
                  <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Spring product pages" />
                </label>
                <label className="field">
                  <span className="label">{t('wizard.customer')}</span>
                  <select className="select" value={customerId ?? ''} onChange={(e) => setCustomerId(Number(e.target.value))}>
                    {customers.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="label">{t('wizard.pm')}</span>
                  <select className="select" value={pmId ?? ''} onChange={(e) => setPmId(Number(e.target.value))}>
                    {pms.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="label">{t('wizard.deadline')}</span>
                  <input type="date" className="input" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
                </label>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="pad-lg stack-lg">
              <h2 className="h2">{t('wizard.sourceTitle')}</h2>
              <div className="grid-2">
                <label className="field">
                  <span className="label">{t('wizard.site')}</span>
                  <select className="select" value={site ?? ''} onChange={(e) => setSite(e.target.value)}>
                    {sites.data?.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="label">{t('wizard.sourceLang')}</span>
                  <select className="select" value={sourceLang ?? ''} onChange={(e) => setSourceLang(e.target.value)}>
                    {languages.data?.map((l) => <option key={l.slug} value={l.slug}>{l.name} · {l.slug}</option>)}
                  </select>
                </label>
              </div>

              <div className="stack-sm">
                <span className="label">{t('wizard.posts', { n: postIds.length })}</span>
                <div className="checklist">
                  {posts.data?.length === 0 && <p className="empty">{t('wizard.noPosts')}</p>}
                  {posts.data?.map((p) => {
                    const others = Object.keys(p.translations).filter((l) => l !== p.lang);
                    return (
                      <label key={p.id} className="checklist__row">
                        <input type="checkbox" className="check" checked={postIds.includes(p.id)} onChange={() => setPostIds(toggle(postIds, p.id))} />
                        <span className="stack-0 min0">
                          <span className="strong small">{p.title}</span>
                          <span className="mono tiny muted">#{p.id} · {p.type} · {p.lang}</span>
                        </span>
                        <span className="mono small right">{t('common.words', { n: fmt.number(p.words) })}</span>
                        <span className="small muted">
                          {others.length ? t('wizard.hasTranslations', { langs: others.join(', ') }) : t('wizard.noTranslations')}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <fieldset className="fieldset">
                <legend className="label">{t('wizard.targets')}</legend>
                <div className="wrap">
                  {languages.data
                    ?.filter((l) => l.slug !== sourceLang)
                    .map((l) => (
                      <button key={l.slug} type="button" aria-pressed={targets.includes(l.slug)} className={`pill${targets.includes(l.slug) ? ' pill--on' : ''}`} onClick={() => setTargets(toggle(targets, l.slug))}>
                        {l.name} · {l.slug}
                      </button>
                    ))}
                </div>
              </fieldset>

              <div className="callout">
                <span className="callout__value">{positionCount}</span>
                <span className="small">{t('wizard.positionsInfo', { posts: selectedPosts.length, langs: targets.length })}</span>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="pad-lg stack-lg">
              <h2 className="h2">{t('wizard.workflowTitle')}</h2>
              <fieldset className="fieldset stack-sm">
                <legend className="label">{t('wizard.template')}</legend>
                {templates.data?.map((tp) => (
                  <button key={tp.code} type="button" aria-pressed={templateCode === tp.code} className={`choice${templateCode === tp.code ? ' choice--on' : ''}`} onClick={() => setTemplateCode(tp.code)}>
                    <span className="row-between">
                      <span className="strong">{tp.name}</span>
                      <span className="small muted">{t(`wizard.template.${tp.code}` as 'wizard.template.standard')}</span>
                    </span>
                    <span className="chain">
                      {tp.tasks.map((task, i) => (
                        <span key={i} className="chain__item">
                          <span className={`chain__task${task === 'IMPORT' || task === 'DELIVER' ? ' chain__task--auto' : ''}`}>{t(`task.${task}`)}</span>
                          {i < tp.tasks.length - 1 && <span aria-hidden="true" className="muted">→</span>}
                        </span>
                      ))}
                    </span>
                  </button>
                ))}
              </fieldset>

              <fieldset className="fieldset stack-sm">
                <legend className="label">{t('wizard.returnTrip')}</legend>
                {DESTINATIONS.map((d) => (
                  <label key={d} className={`choice choice--row${destination === d ? ' choice--on' : ''}`}>
                    <input type="radio" name="dest" className="check" checked={destination === d} onChange={() => setDestination(d)} />
                    <span className="stack-0">
                      <span className="strong small">{t(`dest.${d}`)}</span>
                      <span className="small muted">{t(`dest.${d}.desc`)}</span>
                    </span>
                  </label>
                ))}
                {destination === 'ENDPOINT' && (
                  <label className="field indent">
                    <span className="label">{t('wizard.endpointUrl')}</span>
                    <input type="url" className="input" placeholder="https://" value={destinationUrl} onChange={(e) => setDestinationUrl(e.target.value)} />
                  </label>
                )}
              </fieldset>
            </div>
          )}

          {step === 3 && (
            <div className="pad-lg stack-lg">
              <h2 className="h2">{t('wizard.reviewTitle')}</h2>
              <dl className="summary">
                {[
                  [t('wizard.summary.type'), `${t(`kind.${kind}`)} · ${t(`kind.${kind}.plunet`)}`],
                  [t('order.meta.customer'), customers.data?.find((c) => c.id === customerId)?.name],
                  [t('order.meta.pm'), pms.data?.find((p) => p.id === pmId)?.name],
                  [t('wizard.summary.positions'), t('wizard.summary.positionsValue', { n: positionCount, posts: selectedPosts.length, langs: targets.length })],
                  [t('wizard.summary.words'), fmt.number(words)],
                  [t('wizard.summary.template'), template?.name],
                  [t('wizard.summary.returnTrip'), t(`dest.${destination}`)],
                  [t('order.meta.deadline'), deadline || t('common.none')],
                  [t('wizard.summary.cost'), t('wizard.summary.costValue')],
                ].map(([k, v]) => (
                  <div key={k} className="summary__cell">
                    <dt className="label">{k}</dt>
                    <dd className="strong">{v ?? t('common.none')}</dd>
                  </div>
                ))}
              </dl>
              {targets.length > 0 && (
                <p className="small muted">{targets.map(langName).join(' · ')}</p>
              )}
              <div className="stack-sm">
                <span className="label">{t('wizard.next')}</span>
                <ol className="numbered">
                  {([1, 2, 3] as const).map((n) => (
                    <li key={n}>{t(`wizard.next.${kind === 'QUOTE' ? 'quote' : 'order'}.${n}`)}</li>
                  ))}
                </ol>
              </div>
              {submitError && <ErrorState error={submitError} />}
            </div>
          )}

          <div className="card__footer">
            <button type="button" className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>
              {t('common.back')}
            </button>
            {step < STEPS.length - 1 ? (
              <button type="button" className="btn btn--primary" onClick={() => setStep(step + 1)}>
                {t('common.continue')}
              </button>
            ) : (
              <button type="button" className="btn btn--primary" disabled={submitting} onClick={submit}>
                {submitting ? t('wizard.creating') : t(kind === 'QUOTE' ? 'wizard.create.quote' : 'wizard.create.order')}
              </button>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
