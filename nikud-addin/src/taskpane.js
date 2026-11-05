/* global Office */
// החלונית: ניהול תהליך הניקוד, המילון וההגדרות.

import { Dictionary } from './core/dictionary.js';
import { suggest, decide, insideSkippedBrackets } from './core/analyzer.js';
import { hasNikud, makeKey, normalizeMarks, stripMarks } from './core/hebrew.js';
import { PRESETS, sanitizeSettings } from './core/settings.js';
import { NIKUD, TAAMIM, HOLAM_AFTER_VAV, markForKey, keyLabel } from './core/marks.js';
import {
  loadDictionaryEntries, saveDictionaryChanges, clearDictionaryStore, loadSettings, saveSettings,
} from './storage.js';
import { WordSession, insertAtCursor, stripSelection, getSelectionText } from './word-session.js';

const $ = (id) => document.getElementById(id);

const state = {
  dict: new Dictionary(),
  settings: loadSettings(),
  inWord: false,
  /** @type {WordSession|null} */
  session: null,
  single: false,
  index: -1,
  options: [],
  selected: 0,
  always: new Map(),
  alwaysToggle: false,
  busy: false,
  stopRequested: false,
  applied: 0,
  dictKey: null,
  dictSelected: 0,
};

// ---------- כללי ----------

function setStatus(msg, isError = false) {
  const el = $('status');
  el.textContent = msg ?? '';
  el.classList.toggle('error', isError);
}

/** מריץ פעולה אסינכרונית אחת בכל פעם ומציג שגיאות בשורת המצב. */
async function guarded(fn) {
  if (state.busy) return;
  state.busy = true;
  try {
    await fn();
  } catch (e) {
    console.error(e);
    setStatus(`שגיאה: ${e?.message ?? e}`, true);
  } finally {
    state.busy = false;
  }
}

function requireWord() {
  if (!state.inWord) {
    setStatus('הפעולה הזו עובדת רק בתוך Word.', true);
    return false;
  }
  return true;
}

async function persist() {
  await saveDictionaryChanges(state.dict.takeDirty());
  $('dict-size').textContent = `במילון ${state.dict.size.toLocaleString('he')} מילים.`;
}

function showTab(name) {
  for (const b of document.querySelectorAll('.tabs button')) {
    b.setAttribute('aria-selected', String(b.dataset.tab === name));
  }
  for (const s of document.querySelectorAll('.tab')) s.hidden = s.id !== `tab-${name}`;
}

function markButton(container, { mark, name, standalone }, onClick, label = '') {
  const b = document.createElement('button');
  b.type = 'button';
  b.title = name;
  b.textContent = standalone ? mark : '◌' + mark;
  if (label) {
    const s = document.createElement('small');
    s.textContent = label;
    b.appendChild(s);
  }
  b.addEventListener('mousedown', (e) => e.preventDefault()); // לא לגנוב את המיקוד משדה הקלט
  b.addEventListener('click', () => onClick(mark));
  container.appendChild(b);
}

// ---------- תהליך הניקוד ----------

const currentItem = () => state.session?.items[state.index] ?? null;

async function startSession(single) {
  if (!requireWord()) return;
  state.session = new WordSession();
  state.single = single;
  state.index = -1;
  state.always = new Map();
  state.applied = 0;
  state.stopRequested = false;
  await state.session.open({ singleWord: single });
  $('idle').hidden = true;
  $('session').hidden = false;
  setStatus(single ? '' : 'מנקד…');
  if (single) {
    if (!state.session.items.length) return finish('לא נמצאה מילה עברית במקום הסמן.');
    state.index = 0;
    const item = currentItem();
    return show(item, suggest(item.key, state.dict, state.settings), 'ask');
  }
  await advance(+1);
}

function finish(msg = 'הניקוד הסתיים.') {
  state.session?.close();
  state.session = null;
  $('session').hidden = true;
  $('idle').hidden = false;
  setStatus(msg);
  persist();
}

/**
 * עובר למילה הבאה (או הקודמת) ומחליט עליה לפי ההגדרות.
 * מילים שמנוקדות אוטומטית עוברות בלי לעצור. חזרה אחורה תמיד עוצרת.
 */
async function advance(dir, { force = false } = {}) {
  const s = state.session;
  if (!s) return;
  if (state.single) return finish('');
  let steps = 0;
  for (;;) {
    if (state.stopRequested) return finish('הניקוד הופסק.');
    let i = state.index + dir;
    if (i < 0) {
      setStatus('זו המילה הראשונה.');
      i = 0;
      force = true;
    }
    while (i >= s.items.length) {
      if (!(await s.loadMore())) return finish();
    }
    state.index = i;
    const item = s.items[i];
    const suggestions = suggest(item.key, state.dict, state.settings);

    if (dir < 0 || force) return show(item, suggestions, suggestions.length ? 'ask' : 'manual');

    const d = decide({
      core: item.text,
      suggestions,
      settings: state.settings,
      always: state.always,
      insideBrackets: insideSkippedBrackets(item.brackets, state.settings),
    });
    if (d.action === 'apply') {
      if (d.text !== item.text) await applyTo(item, d.text);
    } else if (d.action !== 'skip') {
      return show(item, suggestions, d.action);
    }
    dir = +1;
    // לתת לחלונית להגיב (Esc, ציור המונה) גם בהרצה ארוכה
    if (++steps % 25 === 0) {
      $('counter').textContent = `${i + 1}`;
      await new Promise((r) => setTimeout(r, 0));
    }
  }
}

async function applyTo(item, text, { dollars = false } = {}) {
  await state.session.apply(item, text, { dollars, preserveFormatting: state.settings.preserveFormatting });
  state.applied++;
  if (state.settings.autosave && state.applied % state.settings.autosaveEvery === 0) {
    if (await state.session.save()) setStatus(`נשמר אוטומטית (${state.applied} מילים).`);
  }
}

async function show(item, suggestions, mode) {
  state.options = suggestions;
  state.selected = 0;
  $('original').textContent = item.text;
  $('counter').textContent = `${state.index + 1}`;
  renderOptions();
  setManual(suggestions[0]?.text ?? item.text);
  setStatus(mode === 'manual' ? 'המילה אינה במילון. נקדו ידנית או המשיכו.' : '');
  await state.session.select(item);
  if (mode === 'manual') focusManual();
  else $('options').focus();
}

function renderOptions() {
  const ul = $('options');
  ul.replaceChildren();
  if (!state.options.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = 'אין אפשרויות במילון';
    ul.appendChild(li);
    return;
  }
  state.options.forEach((opt, i) => {
    const li = document.createElement('li');
    li.setAttribute('role', 'option');
    li.setAttribute('aria-selected', String(i === state.selected));
    const t = document.createElement('span');
    t.textContent = opt.text;
    li.appendChild(t);
    if (opt.mark) {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = opt.mark;
      tag.title = opt.mark === '+' ? 'נוצר מהוספת אותיות שימוש' : 'הותאם לכתיב חסר';
      li.appendChild(tag);
    }
    li.addEventListener('click', (e) => {
      select(i);
      if (state.settings.singleClick) guarded(() => choose(i, { ctrl: e.ctrlKey, alt: e.altKey }));
    });
    li.addEventListener('dblclick', (e) => {
      if (!state.settings.singleClick) guarded(() => choose(i, { ctrl: e.ctrlKey, alt: e.altKey }));
    });
    ul.appendChild(li);
  });
}

function select(i) {
  const n = state.options.length;
  if (!n) return;
  state.selected = ((i % n) + n) % n;
  const lis = $('options').children;
  for (let k = 0; k < lis.length; k++) lis[k].setAttribute('aria-selected', String(k === state.selected));
  lis[state.selected]?.scrollIntoView({ block: 'nearest' });
  setManual(state.options[state.selected].text);
}

function setManual(text) {
  $('manual-input').value = text;
}

function focusManual() {
  const inp = $('manual-input');
  inp.focus();
  inp.setSelectionRange(inp.value.length, inp.value.length);
}

async function choose(i, { ctrl = false, alt = false } = {}) {
  const item = currentItem();
  const opt = state.options[i];
  if (!item || !opt) return;
  if (ctrl || state.alwaysToggle) state.always.set(item.key, opt.text);
  setAlwaysToggle(false);
  if (opt.text !== item.text || alt) await applyTo(item, opt.text, { dollars: alt });
  await advance(+1);
}

function setAlwaysToggle(on) {
  state.alwaysToggle = on;
  $('btn-always').setAttribute('aria-pressed', String(on));
}

/** "הוסף והמשך": מכניס את הניקוד לטקסט וגם למילון. */
async function manualCommit(addToDict) {
  const item = currentItem();
  if (!item) return;
  const text = normalizeMarks($('manual-input').value.trim());
  if (text && addToDict && (hasNikud(text) || makeKey(text) !== item.key)) {
    if (state.dict.add(text, item.key)) await persist();
  }
  if (text && text !== item.text) await applyTo(item, text);
  await advance(+1);
}

function refreshOptions(keepText) {
  const item = currentItem();
  if (!item) return;
  state.options = suggest(item.key, state.dict, state.settings);
  const j = state.options.findIndex((o) => o.text === keepText);
  state.selected = j >= 0 ? j : 0;
  renderOptions();
}

async function moveOption(delta) {
  const item = currentItem();
  const opt = state.options[state.selected];
  if (!item || !opt) return;
  if (!opt.original) return setStatus('אפשר להזיז רק צורה שנמצאת במילון כפי שהיא. הוסיפו אותה קודם ב"הוסף והמשך".');
  if (state.dict.move(item.key, opt.text, delta)) {
    await persist();
    refreshOptions(opt.text);
  }
}

async function deleteOption() {
  const item = currentItem();
  const opt = state.options[state.selected];
  if (!item || !opt) return;
  if (!opt.original) return setStatus('אפשר למחוק רק צורה שנמצאת במילון כפי שהיא.');
  if (state.dict.remove(item.key, opt.text)) {
    await persist();
    refreshOptions(null);
    setStatus(`"${opt.text}" נמחקה מהמילון.`);
  }
}

async function undo() {
  const item = await state.session?.undo();
  if (!item) return setStatus('אין מה לבטל.');
  state.index = state.session.items.indexOf(item);
  await show(item, suggest(item.key, state.dict, state.settings), 'ask');
}

function stop() {
  if (state.busy) state.stopRequested = true;
  else finish('הניקוד הופסק.');
}

function insertIntoManual(mark) {
  const inp = $('manual-input');
  const start = inp.selectionStart ?? inp.value.length;
  const end = inp.selectionEnd ?? start;
  inp.setRangeText(mark, start, end, 'end');
  inp.focus();
}

// ---------- מקשים בתוך תהליך הניקוד ----------

function onOptionsKey(e) {
  const n = state.options.length;
  const run = (fn) => {
    e.preventDefault();
    guarded(fn);
  };
  if (e.ctrlKey && e.key === 'ArrowDown') { e.preventDefault(); return focusManual(); }
  if (e.ctrlKey && e.key === 'ArrowUp') { e.preventDefault(); return setStatus('ניקוד פסוקים יתווסף בשלב הבא.'); }
  switch (e.key) {
    case 'ArrowDown': e.preventDefault(); return select(state.selected + 1);
    case 'ArrowUp': e.preventDefault(); return select(state.selected - 1);
    case 'Home': e.preventDefault(); return select(0);
    case 'End': e.preventDefault(); return select(n - 1);
    case 'PageDown': e.preventDefault(); return select(Math.min(n - 1, state.selected + 5));
    case 'PageUp': e.preventDefault(); return select(Math.max(0, state.selected - 5));
    case 'Enter':
    case ' ':
      if (n) return run(() => choose(state.selected, { ctrl: e.ctrlKey, alt: e.altKey }));
      return;
    case 'ArrowRight': return run(() => advance(-1));
    case 'ArrowLeft': return run(() => advance(+1, { force: e.shiftKey }));
    case 'Delete': return run(deleteOption);
    default:
  }
  if (e.ctrlKey && (e.key === 'z' || e.key === 'Z' || e.code === 'KeyZ')) run(undo);
}

function onManualKey(e) {
  const mark = !e.ctrlKey ? markForKey(e) : null;
  if (mark) {
    e.preventDefault();
    return insertIntoManual(mark);
  }
  const run = (fn) => {
    e.preventDefault();
    guarded(fn);
  };
  if (e.key === 'Enter') return run(() => manualCommit(!e.shiftKey));
  if (e.ctrlKey && e.shiftKey && e.key === 'Delete') {
    e.preventDefault();
    $('manual-input').value = stripMarks($('manual-input').value);
    return;
  }
  if (e.ctrlKey && e.key === 'ArrowRight') return run(() => advance(-1));
  if (e.ctrlKey && e.key === 'ArrowLeft') return run(() => advance(+1, { force: e.shiftKey }));
  if (e.ctrlKey && e.key === 'ArrowUp') { e.preventDefault(); $('options').focus(); }
}

function onSessionKey(e) {
  if (e.key === 'Escape') {
    e.preventDefault();
    stop();
  } else if (e.ctrlKey && e.shiftKey && e.code === 'KeyS') {
    e.preventDefault();
    showTab('settings');
  }
}

// ---------- מילון ----------

function renderDictKeys() {
  const q = $('dict-search').value.trim();
  const keys = state.dict.searchKeys(q, 300);
  const ul = $('dict-keys');
  ul.replaceChildren();
  for (const k of keys) {
    const li = document.createElement('li');
    li.setAttribute('role', 'option');
    li.textContent = k;
    li.setAttribute('aria-selected', String(k === state.dictKey));
    li.addEventListener('click', () => {
      state.dictKey = k;
      state.dictSelected = 0;
      renderDictKeys();
      renderDictValues();
    });
    ul.appendChild(li);
  }
  if (!state.dictKey && keys.length && makeKey(q) && keys[0] === makeKey(q)) {
    state.dictKey = keys[0];
    renderDictValues();
  }
}

function renderDictValues() {
  const ul = $('dict-values');
  ul.replaceChildren();
  const values = state.dictKey ? state.dict.get(state.dictKey) : [];
  values.forEach((v, i) => {
    const li = document.createElement('li');
    li.setAttribute('role', 'option');
    li.textContent = v;
    li.setAttribute('aria-selected', String(i === state.dictSelected));
    li.addEventListener('click', () => {
      state.dictSelected = i;
      renderDictValues();
    });
    ul.appendChild(li);
  });
}

async function dictAction(kind) {
  if (!state.dictKey) return;
  const v = state.dict.get(state.dictKey)[state.dictSelected];
  if (!v) return;
  if (kind === 'delete') {
    state.dict.remove(state.dictKey, v);
    state.dictSelected = 0;
  } else {
    state.dict.move(state.dictKey, v, kind === 'up' ? -1 : 1);
    state.dictSelected = state.dict.get(state.dictKey).indexOf(v);
  }
  await persist();
  if (!state.dict.has(state.dictKey)) state.dictKey = null;
  renderDictKeys();
  renderDictValues();
}

async function dictAdd() {
  const value = $('dict-search').value.trim();
  const key = $('dict-key').value.trim() || null;
  if (!value) return setStatus('כתבו מילה בשדה העליון.');
  const ok = state.dict.add(value, key, { allowUnvocalized: true });
  await persist();
  if (!ok) return setStatus('המילה כבר במילון.');
  setStatus(hasNikud(value) ? `"${value}" נוספה למילון.` : `נוספה מילה לא מנוקדת: "${value}".`);
  state.dictKey = makeKey(key ?? value);
  $('dict-key').value = '';
  renderDictKeys();
  renderDictValues();
}

async function dictExport() {
  const json = JSON.stringify(state.dict.toJSON());
  const stamp = new Date().toISOString().slice(0, 10);
  try {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
    a.download = `nikud-kal-dictionary-${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setStatus('קובץ הגיבוי נוצר.');
  } catch {
    await navigator.clipboard.writeText(json);
    setStatus('ההורדה לא נתמכת כאן, ולכן הגיבוי הועתק ללוח. הדביקו אותו בקובץ טקסט.');
  }
}

async function dictImport(file) {
  const text = await file.text();
  const added = state.dict.importData(text);
  await persist();
  renderDictKeys();
  setStatus(`נוספו ${added.toLocaleString('he')} צורות מהקובץ.`);
}

let clearArmed = 0;
async function dictClear() {
  if (Date.now() - clearArmed > 5000) {
    clearArmed = Date.now();
    return setStatus('לחצו שוב תוך 5 שניות כדי לרוקן את כל המילון. כדאי לשמור גיבוי קודם.', true);
  }
  clearArmed = 0;
  state.dict.loadEntries([]);
  await clearDictionaryStore();
  state.dictKey = null;
  await persist();
  renderDictKeys();
  renderDictValues();
  setStatus('המילון רוקן.');
}

// ---------- הגדרות ----------

function fillSettingsForm() {
  const f = $('settings-form');
  for (const [k, v] of Object.entries(state.settings)) {
    const els = f.elements.namedItem(k);
    if (!els) continue;
    if (els instanceof RadioNodeList) {
      for (const r of els) r.checked = r.value === v;
    } else if (els.type === 'checkbox') els.checked = v;
    else els.value = String(v);
  }
}

function readSettingsForm() {
  const f = $('settings-form');
  const out = {};
  for (const k of Object.keys(state.settings)) {
    const els = f.elements.namedItem(k);
    if (!els) {
      out[k] = state.settings[k];
      continue;
    }
    if (els instanceof RadioNodeList) out[k] = els.value;
    else if (els.type === 'checkbox') out[k] = els.checked;
    else if (els.type === 'number') out[k] = Number(els.value);
    else out[k] = els.value;
  }
  return sanitizeSettings(out);
}

function applySettings(s) {
  state.settings = sanitizeSettings(s);
  saveSettings(state.settings);
  fillSettingsForm();
}

// ---------- אתחול ----------

function wire() {
  for (const b of document.querySelectorAll('.tabs button')) b.addEventListener('click', () => showTab(b.dataset.tab));

  $('btn-start').addEventListener('click', () => guarded(() => startSession(false)));
  $('btn-single').addEventListener('click', () => guarded(() => startSession(true)));
  $('btn-add-selection').addEventListener('click', () => guarded(async () => {
    if (!requireWord()) return;
    const added = state.dict.addFromText(await getSelectionText());
    await persist();
    setStatus(added ? `נוספו ${added.toLocaleString('he')} מילים למילון.` : 'לא נמצאו בבחירה מילים מנוקדות חדשות.');
  }));

  $('btn-back').addEventListener('click', () => guarded(() => advance(-1)));
  $('btn-next').addEventListener('click', (e) => guarded(() => advance(+1, { force: e.shiftKey })));
  $('btn-always').addEventListener('click', () => setAlwaysToggle(!state.alwaysToggle));
  $('btn-top').addEventListener('click', () => guarded(() => moveOption('top')));
  $('btn-up').addEventListener('click', () => guarded(() => moveOption(-1)));
  $('btn-down').addEventListener('click', () => guarded(() => moveOption(1)));
  $('btn-delete').addEventListener('click', () => guarded(deleteOption));
  $('btn-undo').addEventListener('click', () => guarded(undo));
  $('btn-stop').addEventListener('click', stop);
  $('btn-add-continue').addEventListener('click', () => guarded(() => manualCommit(true)));
  $('btn-continue').addEventListener('click', () => guarded(() => manualCommit(false)));
  $('btn-strip-manual').addEventListener('click', () => {
    $('manual-input').value = stripMarks($('manual-input').value);
    focusManual();
  });

  $('options').addEventListener('keydown', onOptionsKey);
  $('manual-input').addEventListener('keydown', onManualKey);
  $('session').addEventListener('keydown', onSessionKey);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.session && !$('session').contains(document.activeElement)) stop();
  });

  const manualMarks = $('manual-marks');
  for (const n of NIKUD) markButton(manualMarks, n, insertIntoManual, keyLabel(n));
  markButton(manualMarks, HOLAM_AFTER_VAV, insertIntoManual);

  const kbN = $('kb-nikud');
  const kbT = $('kb-taamim');
  const toDoc = (m) => guarded(async () => requireWord() && insertAtCursor(m));
  for (const n of NIKUD) markButton(kbN, n, toDoc);
  markButton(kbN, HOLAM_AFTER_VAV, toDoc);
  for (const t of TAAMIM) markButton(kbT, t, toDoc);
  $('btn-strip-selection').addEventListener('click', () => guarded(async () => {
    if (!requireWord()) return;
    const n = await stripSelection();
    setStatus(n ? `הוסר ניקוד מ-${n} מילים.` : 'לא נמצא ניקוד בבחירה.');
  }));
  $('btn-strip-taamim').addEventListener('click', () => guarded(async () => {
    if (!requireWord()) return;
    const n = await stripSelection({ taamimOnly: true });
    setStatus(n ? `הוסרו טעמים מ-${n} מילים.` : 'לא נמצאו טעמים בבחירה.');
  }));

  let searchTimer = 0;
  $('dict-search').addEventListener('input', () => {
    clearTimeout(searchTimer);
    state.dictKey = null;
    searchTimer = setTimeout(() => {
      renderDictKeys();
      renderDictValues();
    }, 150);
  });
  $('dict-search').addEventListener('keydown', (e) => {
    const mark = !e.ctrlKey ? markForKey(e) : null;
    if (mark) {
      e.preventDefault();
      const inp = $('dict-search');
      inp.setRangeText(mark, inp.selectionStart, inp.selectionEnd, 'end');
    } else if (e.key === 'Enter') guarded(dictAdd);
  });
  $('dict-add').addEventListener('click', () => guarded(dictAdd));
  $('dict-up').addEventListener('click', () => guarded(() => dictAction('up')));
  $('dict-down').addEventListener('click', () => guarded(() => dictAction('down')));
  $('dict-delete').addEventListener('click', () => guarded(() => dictAction('delete')));
  $('dict-export').addEventListener('click', () => guarded(dictExport));
  $('dict-import').addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (file) guarded(() => dictImport(file));
    e.target.value = '';
  });
  $('dict-clear').addEventListener('click', () => guarded(dictClear));

  $('settings-form').addEventListener('change', () => applySettings(readSettingsForm()));
  for (const b of document.querySelectorAll('[data-preset]')) {
    b.addEventListener('click', () => {
      applySettings(PRESETS[b.dataset.preset]);
      setStatus(b.dataset.preset === 'run' ? 'הוגדרה הרצת ניקוד.' : 'הוחזרו הגדרות ברירת המחדל.');
    });
  }
}

async function init() {
  wire();
  fillSettingsForm();
  state.dict.loadEntries(await loadDictionaryEntries());
  if (state.dict.size === 0) {
    try {
      const res = await fetch('../data/starter-dictionary.json');
      if (res.ok) {
        state.dict.importData(await res.json());
        await persist();
      }
    } catch {
      /* אין מילון התחלתי: מתחילים ממילון ריק */
    }
  }
  $('dict-size').textContent = `במילון ${state.dict.size.toLocaleString('he')} מילים.`;
  renderDictKeys();
}

if (typeof Office !== 'undefined') {
  Office.onReady((info) => {
    state.inWord = info.host === Office.HostType.Word;
    if (!state.inWord) setStatus('החלונית פתוחה מחוץ ל-Word: אפשר לערוך מילון והגדרות בלבד.');
    init();
  });
} else {
  init();
}
