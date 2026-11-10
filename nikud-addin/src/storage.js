// שמירת המילון ב-IndexedDB ושמירת ההגדרות ב-localStorage.
// אם הדפדפן חוסם אחסון, התוסף ממשיך לעבוד בזיכרון בלבד.

import { sanitizeSettings } from './core/settings.js';

const DB_NAME = 'nikud-kal';
const STORE = 'dictionary';
const SETTINGS_KEY = 'nikud-kal.settings';
const CUSTOM_KEY = 'nikud-kal.custom';

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

let dbPromise = null;
const db = () => (dbPromise ??= openDb());

/** @returns {Promise<Array<[string, string[]]>>} */
export async function loadDictionaryEntries() {
  try {
    const d = await db();
    return await new Promise((resolve, reject) => {
      const tx = d.transaction(STORE, 'readonly');
      const store = tx.objectStore(STORE);
      const keysReq = store.getAllKeys();
      const valsReq = store.getAll();
      tx.oncomplete = () => resolve(keysReq.result.map((k, i) => [k, valsReq.result[i]]));
      tx.onerror = () => reject(tx.error);
    });
  } catch (e) {
    console.warn('לא ניתן לקרוא את המילון מהאחסון', e);
    return [];
  }
}

/** כותב רק את המפתחות ששונו. ערך null מוחק את המפתח. */
export async function saveDictionaryChanges(changes) {
  if (!changes.length) return;
  try {
    const d = await db();
    await new Promise((resolve, reject) => {
      const tx = d.transaction(STORE, 'readwrite');
      const store = tx.objectStore(STORE);
      for (const [k, v] of changes) {
        if (v && v.length) store.put(v, k);
        else store.delete(k);
      }
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  } catch (e) {
    console.warn('לא ניתן לשמור את המילון', e);
  }
}

export async function clearDictionaryStore() {
  try {
    const d = await db();
    await new Promise((resolve, reject) => {
      const tx = d.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).clear();
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  } catch (e) {
    console.warn('לא ניתן לנקות את המילון', e);
  }
}

export function loadSettings() {
  try {
    return sanitizeSettings(JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null'));
  } catch {
    return sanitizeSettings(null);
  }
}

export function saveSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    /* אחסון חסום: ההגדרות יישמרו רק עד סגירת החלונית */
  }
}

/** ההגדרות של "התאמה אישית", שנשמרות בנפרד מהקבוצות המוכנות. */
export function loadCustomSettings() {
  try {
    const raw = JSON.parse(localStorage.getItem(CUSTOM_KEY) || 'null');
    return raw ? sanitizeSettings(raw) : null;
  } catch {
    return null;
  }
}

export function saveCustomSettings(settings) {
  try {
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(settings));
  } catch {
    /* אחסון חסום */
  }
}
