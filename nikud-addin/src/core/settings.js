// הגדרות התוסף וקבוצות ההגדרות המוכנות.

export const DEFAULT_SETTINGS = Object.freeze({
  whenMultiple: 'ask',      // 'ask' | 'first'
  whenNone: 'bigManual',    // 'next' | 'manual' (חלון קטן) | 'bigManual' (חלון גדול)
  askSingle: false,
  singleClick: true,
  addPrefixes: true,
  prefixAlways: false,
  abbreviationMode: 'ask',  // 'ask' | 'apply' | 'skip'
  spellingMode: 'ask',      // 'ask' | 'apply' | 'skip'
  skipVocalized: false,
  skipSingleLetters: false,
  skipAbbreviations: false,
  skipRound: false,
  skipSquare: false,
  skipCurly: false,
  autosave: true,
  autosaveEvery: 1000,
  preserveFormatting: true,
  verseSource: true,
  verseQuotes: false,
  verseTaamim: false,
  verseNoNikud: false,
});

/** הרצת ניקוד על כל הטקסט, ואחריה הגהה. */
export const RUN_PRESET = Object.freeze({
  ...DEFAULT_SETTINGS,
  whenMultiple: 'first',
  whenNone: 'next',
  abbreviationMode: 'skip',
  spellingMode: 'skip',
  skipVocalized: true,
});

export const PRESETS = { default: DEFAULT_SETTINGS, run: RUN_PRESET };

/** משלים הגדרות חסרות מברירת המחדל ומתקן ערכים לא חוקיים. */
export function sanitizeSettings(raw) {
  const s = { ...DEFAULT_SETTINGS, ...(raw && typeof raw === 'object' ? raw : {}) };
  for (const [k, v] of Object.entries(DEFAULT_SETTINGS)) {
    if (typeof s[k] !== typeof v) s[k] = v;
  }
  if (!['ask', 'first'].includes(s.whenMultiple)) s.whenMultiple = 'ask';
  if (!['manual', 'next', 'bigManual'].includes(s.whenNone)) s.whenNone = 'bigManual';
  for (const k of ['abbreviationMode', 'spellingMode']) {
    if (!['ask', 'apply', 'skip'].includes(s[k])) s[k] = 'ask';
  }
  s.autosaveEvery = Math.max(100, Math.round(Number(s.autosaveEvery) || 1000));
  return s;
}
