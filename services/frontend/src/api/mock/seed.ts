// Reference data for the in-memory mock API. Mirrors the Polylang mock service seed
// (services/polylang-mock/data/seed.json) plus a second site.

import type { Language, Ref, Template } from '../types';

export const CUSTOMERS: Ref[] = [
  { id: 1, name: 'Maison Lumière SA' },
  { id: 2, name: 'Alpentech GmbH' },
  { id: 3, name: 'Nordwind AG' },
  { id: 4, name: 'Kestrel Labs' },
];

export const RESOURCES: Ref[] = [
  { id: 11, name: 'Claire Dubois' },
  { id: 12, name: 'Jonas Weber' },
  { id: 13, name: 'Sofia Marin' },
];

/** Translators and reviewers assigned in Plunet (by language). */
export const LINGUISTS: Record<string, { tra: Ref; rev: Ref }> = {
  fr: { tra: { id: 21, name: 'A. Laurent' }, rev: { id: 22, name: 'M. Rousseau' } },
  'de-at': { tra: { id: 23, name: 'K. Gruber' }, rev: { id: 24, name: 'M. Huber' } },
  it: { tra: { id: 25, name: 'G. Ferri' }, rev: { id: 26, name: 'L. Conti' } },
  es: { tra: { id: 27, name: 'P. Ortega' }, rev: { id: 28, name: 'R. Vidal' } },
  en: { tra: { id: 29, name: 'J. Carter' }, rev: { id: 30, name: 'E. Hughes' } },
};

export const TEMPLATES: Template[] = [
  { code: 'standard', name: 'Standard', tasks: ['IMPORT', 'PM', 'TRA', 'REV', 'QA', 'DELIVER'] },
  { code: 'light', name: 'Light', tasks: ['IMPORT', 'TRA', 'QA', 'DELIVER'] },
  { code: 'regulated', name: 'Regulated', tasks: ['IMPORT', 'PM', 'TRA', 'REV', 'REV', 'QA', 'DELIVER'] },
];

export const LANGUAGES: Language[] = [
  { slug: 'en', name: 'English', locale: 'en_US' },
  { slug: 'fr', name: 'Français', locale: 'fr_FR' },
  { slug: 'de-at', name: 'Deutsch (Österreich)', locale: 'de_AT' },
  { slug: 'it', name: 'Italiano', locale: 'it_IT' },
  { slug: 'es', name: 'Español', locale: 'es_ES' },
];

export interface SeedPost {
  id: number;
  site: string;
  type: 'post' | 'page';
  lang: string;
  title: string;
  segments: string[];
  translations: Record<string, number>;
  /** Demo: the first QA run of this post's translations finds placeholder errors. */
  qaFailsFirst?: boolean;
}

export const SITES = ['maison-lumiere.com', 'alpentech.at'];

export const POSTS: SeedPost[] = [
  {
    id: 412, site: 'maison-lumiere.com', type: 'page', lang: 'en', title: 'Spring collection — overview',
    segments: [
      'Our spring collection celebrates light fabrics and natural colours.',
      'Discover {0} new pieces designed in our Paris atelier.',
      'Every item ships within %s business days.',
      'Linen, cotton and silk, chosen for comfort and durability.',
    ],
    translations: { fr: 512 },
  },
  {
    id: 418, site: 'maison-lumiere.com', type: 'post', lang: 'en', title: 'Linen shirt — product page',
    segments: ['A relaxed linen shirt for warm days.', 'Available in {count} colours and sizes XS to XXL.', 'Machine wash at 30°C.'],
    translations: {},
  },
  {
    id: 421, site: 'maison-lumiere.com', type: 'page', lang: 'en', title: 'Care guide',
    segments: ['Wash linen inside out to protect the fibres.', 'Dry flat in the shade.', 'Iron while slightly damp for the best result.'],
    translations: { 'de-at': 621 },
  },
  {
    id: 433, site: 'maison-lumiere.com', type: 'post', lang: 'en', title: 'Behind the atelier',
    segments: [
      'Every piece begins at the cutting table.',
      'Over {0} artisans work in our atelier.',
      'Shipped in %s business days.',
      'Linen is grown in Normandy.',
      'We visit our weavers twice a year.',
    ],
    translations: {},
    qaFailsFirst: true,
  },
  {
    id: 440, site: 'maison-lumiere.com', type: 'page', lang: 'en', title: 'Shipping & returns',
    segments: ['Free shipping on orders over %1$s.', 'Returns are accepted within 30 days.', 'Contact us at support@example.com for help.'],
    translations: {},
  },
  {
    id: 445, site: 'maison-lumiere.com', type: 'page', lang: 'en', title: 'Privacy policy',
    segments: ['We collect only the data needed to process your order.', 'You can request deletion of your data at any time.', 'Data is stored in the EU.'],
    translations: {},
  },
  {
    id: 702, site: 'alpentech.at', type: 'page', lang: 'de-at', title: 'Hilfe-Center — Startseite',
    segments: ['Willkommen im Hilfe-Center.', 'Suchen Sie in {0} Artikeln.', 'Unser Support antwortet innerhalb von %s Stunden.'],
    translations: {},
  },
  {
    id: 705, site: 'alpentech.at', type: 'post', lang: 'de-at', title: 'Erste Schritte',
    segments: ['Erstellen Sie Ihr Konto.', 'Verbinden Sie Ihr erstes Gerät.', 'Laden Sie {count} Kollegen ein.'],
    translations: {},
  },
  {
    id: 711, site: 'alpentech.at', type: 'post', lang: 'de-at', title: 'Willkommens-E-Mail',
    segments: ['Hallo {name}, willkommen bei Alpentech!', 'Ihr Testzeitraum endet in %s Tagen.'],
    translations: {},
  },
  {
    id: 712, site: 'alpentech.at', type: 'post', lang: 'de-at', title: 'Erinnerungs-E-Mail',
    segments: ['Sie haben noch {0} offene Schritte.', 'Brauchen Sie Hilfe?'],
    translations: {},
  },
  {
    id: 713, site: 'alpentech.at', type: 'post', lang: 'de-at', title: 'Abschluss-E-Mail',
    segments: ['Geschafft!', 'Ihr Konto ist eingerichtet.'],
    translations: {},
  },
];


/** Full word count of each post (the segments above are an excerpt). */
export const POST_WORDS: Record<number, number> = {
  412: 1240, 418: 486, 421: 932, 433: 1710, 440: 655, 445: 820,
  702: 540, 705: 610, 711: 180, 712: 150, 713: 120,
};
