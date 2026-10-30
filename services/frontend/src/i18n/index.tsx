import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { en, type MessageKey } from './en';
import { fr } from './fr';

export type Lang = 'en' | 'fr';
const DICTS: Record<Lang, Record<MessageKey, string>> = { en, fr };
const STORAGE_KEY = 'fox-mlo.lang';

type Vars = Record<string, string | number>;
export type T = (key: MessageKey, vars?: Vars) => string;

interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: T;
  /** Locale-aware formatting helpers. */
  fmt: {
    number: (n: number) => string;
    money: (n: number, currency?: string) => string;
    date: (iso: string) => string;
    dateTime: (iso: string) => string;
    time: (iso: string) => string;
    relative: (iso: string) => string;
    duration: (seconds: number) => string;
  };
}

const Ctx = createContext<I18n | null>(null);

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'en' || saved === 'fr') return saved;
  } catch {
    // storage unavailable
  }
  return navigator.language.startsWith('fr') ? 'fr' : 'en';
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    document.documentElement.lang = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo<I18n>(() => {
    const dict = DICTS[lang];
    const locale = lang === 'fr' ? 'fr-FR' : 'en-GB';
    const t: T = (key, vars) => {
      let s = dict[key] ?? key;
      if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
      return s;
    };
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
    return {
      lang,
      setLang,
      t,
      fmt: {
        number: (n) => new Intl.NumberFormat(locale).format(n),
        money: (n, currency = 'EUR') => new Intl.NumberFormat(locale, { style: 'currency', currency }).format(n),
        date: (iso) => new Intl.DateTimeFormat('sv-SE', { dateStyle: 'short' }).format(new Date(iso)),
        dateTime: (iso) => new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(iso)),
        time: (iso) => new Intl.DateTimeFormat(locale, { timeStyle: 'medium' }).format(new Date(iso)),
        relative: (iso) => {
          const s = (new Date(iso).getTime() - Date.now()) / 1000;
          const abs = Math.abs(s);
          if (abs < 60) return rtf.format(Math.round(s), 'second');
          if (abs < 3600) return rtf.format(Math.round(s / 60), 'minute');
          if (abs < 86400) return rtf.format(Math.round(s / 3600), 'hour');
          return rtf.format(Math.round(s / 86400), 'day');
        },
        duration: (seconds) => {
          if (seconds < 60) return `${Math.round(seconds)}s`;
          const m = Math.floor(seconds / 60);
          if (m < 60) return `${m}m ${Math.round(seconds % 60)}s`;
          const h = Math.floor(m / 60);
          if (h < 48) return `${h}h ${m % 60}m`;
          return `${Math.floor(h / 24)}d ${h % 24}h`;
        },
      },
    };
  }, [lang, setLang]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useI18n must be used inside I18nProvider');
  return ctx;
}
