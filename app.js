// ── Settings (persistent book selection) ───────────────────────
const SETTINGS_KEY = 'einmishpatnetmitsvah-settings';

const ALL_BOOKS = ['Rambam', 'Tur', 'SMaG', 'Shulchan Aruch', 'Ben Yehoyada', 'Benayahu'];

function defaultSettings() {
  const books = {};
  ALL_BOOKS.forEach(b => books[b] = true);
  return { books };
}

function loadSettings() {
  try {
    const saved = localStorage.getItem(SETTINGS_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      // Merge with defaults so new books default to enabled
      const merged = defaultSettings();
      if (parsed.books) {
        ALL_BOOKS.forEach(b => {
          if (typeof parsed.books[b] === 'boolean') merged.books[b] = parsed.books[b];
        });
      }
      return merged;
    }
  } catch (e) { console.warn('Could not load settings:', e); }
  return defaultSettings();
}

function saveSettings(s) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
}

let _settings = loadSettings();

function isBookEnabled(book) {
  return _settings.books[book] !== false;
}

function toggleBook(book) {
  _settings.books[book] = !_settings.books[book];
  saveSettings(_settings);
  // Update checkbox state
  const label = document.querySelector(`.settings-item[data-book="${book}"]`);
  if (label) {
    const cb = label.querySelector('input[type=checkbox]');
    if (cb) cb.checked = _settings.books[book];
  }
  renderFromLastResults();
}

function toggleSettings() {
  const panel = document.getElementById('settings-panel');
  const btn = document.getElementById('settings-btn');
  if (!panel) return;
  const shown = panel.style.display !== 'none';
  panel.style.display = shown ? 'none' : 'block';
  btn.classList.toggle('active', !shown);
}

// Close settings panel when clicking outside
document.addEventListener('click', function (e) {
  const panel = document.getElementById('settings-panel');
  const btn = document.getElementById('settings-btn');
  if (!panel || panel.style.display === 'none') return;
  if (!panel.contains(e.target) && !btn.contains(e.target)) {
    panel.style.display = 'none';
    btn.classList.remove('active');
  }
});

// Sync the settings checkboxes on page load
function initSettingsUI() {
  ALL_BOOKS.forEach(book => {
    const label = document.querySelector(`.settings-item[data-book="${book}"]`);
    if (label) {
      const cb = label.querySelector('input[type=checkbox]');
      if (cb) cb.checked = _settings.books[book] !== false;
    }
  });
}

// ── Hebrew numerals ──────────────────────────────────────────
function toHebrewNum(n) {
  if (n <= 0) return '';
  const ONES = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט'];
  const TENS = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ'];
  const HUNDREDS = ['', 'ק', 'ר', 'ש', 'ת', 'תק', 'תר', 'תש', 'תת', 'תתק'];
  let r = '';
  if (n >= 100) { r += HUNDREDS[Math.floor(n / 100)]; n %= 100; }
  if (n === 15) return r + 'טו';
  if (n === 16) return r + 'טז';
  if (n >= 10) { r += TENS[Math.floor(n / 10)]; n %= 10; }
  return r + ONES[n];
}

// ── Persistence helpers (localStorage) ────────────────────────
const STORAGE_KEY = 'einmishpatnetmitsvah-last-selection';

function saveSelection() {
  const tractate = document.getElementById('tractate').value;
  const dafNum = document.getElementById('daf-num').value;
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ tractate, dafNum }));
}

function loadSelection() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const { tractate, dafNum } = JSON.parse(saved);
      return { tractate, dafNum };
    }
  } catch (e) {
    console.warn('Could not load saved selection:', e);
  }
  return null;
}

// ── Populate tractate dropdown ───────────────────────────────
const tractSel = document.getElementById('tractate');
TRACTATES.forEach(t => {
  const o = document.createElement('option');
  o.value = o.textContent = t;
  tractSel.appendChild(o);
});

function buildDafDropdown(tractate) {
  const max = DAF_MAX[tractate] || 64;
  const first = DAF_FIRST[tractate] || 2;
  const dafSel = document.getElementById('daf-num');
  dafSel.innerHTML = '';
  for (let i = first; i <= max; i++) {
    const o = document.createElement('option');
    o.value = i;
    o.textContent = toHebrewNum(i);
    dafSel.appendChild(o);
  }
}

function onTractateChange() {
  buildDafDropdown(document.getElementById('tractate').value);
  saveSelection();
  doSearch();
}

// Load saved selection or defaults
const saved = loadSelection();
const defaultTractate = saved ? saved.tractate : TRACTATES[0];
tractSel.value = defaultTractate;
buildDafDropdown(defaultTractate);

const dafSel = document.getElementById('daf-num');
if (saved && saved.dafNum) {
  dafSel.value = saved.dafNum;
} else {
  // Ensure a value is selected for first-time load so doSearch() doesn't bail
  dafSel.selectedIndex = 0;
}

// Trigger initial search with loaded/default values
function initFirstRender() {
  doSearch();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initSettingsUI();
    initFirstRender();
  }, { once: true });
} else {
  initSettingsUI();
  initFirstRender();
}

function jumpTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth' });
}

// ── Sefaria helpers ──────────────────────────────────────────

function cleanHebrew(text) {
  if (!text) return '';
  return text.replace(/<[^>]+>/g, '').trim();
}

function identifyBook(ref) {
  const refL = ref.toLowerCase();
  for (const [book, patterns] of Object.entries(BOOK_PATTERNS)) {
    for (const p of patterns) {
      if (refL.includes(p)) return book;
    }
  }
  return null;
}

// Extract segment number from an anchorRef like "Pesachim 2b:3"
function extractSegment(anchorRef) {
  const m = anchorRef.match(/:(\d+)$/);
  return m ? parseInt(m[1], 10) : null;
}

// Build a TREF string for Sefaria, e.g. "Pesachim.2b"
function buildTref(tractateEn, dafNum, side) {
  const sideEn = side === 'א' ? 'a' : 'b';
  return `${tractateEn}.${dafNum}${sideEn}`;
}

// Build the mapping of segment → book → [{ref, heRef, text}]
function buildMapping(links, targetDafNorm) {
  const mapping = new Map();

  for (const link of links) {
    if (link.category !== 'Halakhah') continue;

    const anchorRef = link.anchorRef || '';
    const sourceRef = link.sourceRef || '';
    const sourceHeRef = link.sourceHeRef || sourceRef;

    if (!anchorRef.toLowerCase().includes(targetDafNorm)) continue;

    const seg = extractSegment(anchorRef);
    if (seg === null) continue;

    const bookPart = sourceRef.split(',')[0];
    const book = identifyBook(bookPart);
    if (!book) continue;

    let text = '';
    const he = link.he;
    if (Array.isArray(he)) {
      text = cleanHebrew(he.join(' '));
    } else if (typeof he === 'string') {
      text = cleanHebrew(he);
    }

    if (!mapping.has(seg)) mapping.set(seg, new Map());
    const segMap = mapping.get(seg);
    if (!segMap.has(book)) segMap.set(book, []);
    segMap.get(book).push({ heRef: sourceHeRef, text, sourceRef });
  }

  return mapping;
}

// Fetch text segments for a daf side
async function fetchDafText(tref) {
  const url = `${SEFARIA_BASE}/api/v3/texts/${encodeURIComponent(tref)}?version=source&return_format=text_only`;
  const r = await fetch(url);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const data = await r.json();
  if (data.versions && data.versions.length > 0) {
    return data.versions[0].text || [];
  }
  return [];
}

// Fetch Halakhah links for a daf side
async function fetchLinks(tref) {
  const url = `${SEFARIA_BASE}/api/links/${encodeURIComponent(tref)}?category=Halakhah`;
  const r = await fetch(url);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

// Fetch Commentary links for a daf side
async function fetchCommentaryLinks(tref) {
  const url = `${SEFARIA_BASE}/api/links/${encodeURIComponent(tref)}?category=Commentary`;
  const r = await fetch(url);
  if (!r.ok) return [];
  return r.json();
}

// Build commentary mapping: Map<segNum, Map<bookName, Array<{heRef, text, sourceRef}>>>
function buildCommentaryMapping(links, targetDafNorm) {
  const mapping = new Map();

  for (const link of links) {
    const anchorRef = link.anchorRef || '';
    const sourceRef = link.sourceRef || '';
    const sourceHeRef = link.sourceHeRef || sourceRef;

    if (!anchorRef.toLowerCase().includes(targetDafNorm)) continue;

    const seg = extractSegment(anchorRef);
    if (seg === null) continue;

    const sourceRefL = sourceRef.toLowerCase();
    let matchedBook = null;
    for (const [book, patterns] of Object.entries(COMMENTARY_PATTERNS)) {
      for (const p of patterns) {
        if (sourceRefL.includes(p)) { matchedBook = book; break; }
      }
      if (matchedBook) break;
    }
    if (!matchedBook) continue;

    let text = '';
    const he = link.he;
    if (Array.isArray(he)) {
      text = cleanHebrew(he.join(' '));
    } else if (typeof he === 'string') {
      text = cleanHebrew(he);
    }

    if (!mapping.has(seg)) mapping.set(seg, new Map());
    const segMap = mapping.get(seg);
    if (!segMap.has(matchedBook)) segMap.set(matchedBook, []);
    segMap.get(matchedBook).push({ heRef: sourceHeRef, text, sourceRef });
  }

  return mapping;
}

// Fetch data for one side (א or ב) and build entries
async function fetchSide(tractateHe, dafNum, side) {
  const tractateEn = TRACTATE_EN[tractateHe] || tractateHe;
  const sideEn = side === 'א' ? 'a' : 'b';
  const tref = `${tractateEn}.${dafNum}${sideEn}`;
  const dafHeb = toHebrewNum(dafNum);

  const targetDafNorm = `${tractateEn.toLowerCase()} ${dafNum}${sideEn}`;

  try {
    const [textSegments, links, commentaryLinks] = await Promise.all([
      fetchDafText(tref),
      fetchLinks(tref),
      fetchCommentaryLinks(tref)
    ]);

    const mapping = buildMapping(links, targetDafNorm);
    const commentaryMapping = buildCommentaryMapping(commentaryLinks, targetDafNorm);

    const entries = [];
    textSegments.forEach((segText, idx) => {
      const segNum = idx + 1;

      const refs = [];
      if (mapping.has(segNum)) {
        const bookMap = mapping.get(segNum);
        for (const book of ['Rambam', 'Tur', 'SMaG', 'Shulchan Aruch']) {
          if (bookMap.has(book)) {
            for (const item of bookMap.get(book)) {
              refs.push({ book, heRef: item.heRef, text: item.text, sourceRef: item.sourceRef });
            }
          }
        }
      }

      const commentaryRefs = [];
      if (commentaryMapping.has(segNum)) {
        const cMap = commentaryMapping.get(segNum);
        for (const book of ['Ben Yehoyada', 'Benayahu']) {
          if (cMap.has(book)) {
            for (const item of cMap.get(book)) {
              commentaryRefs.push({ book, heRef: item.heRef, text: item.text, sourceRef: item.sourceRef });
            }
          }
        }
      }

      if (refs.length > 0 || commentaryRefs.length > 0) {
        entries.push({ segNum, segText: cleanHebrew(segText), refs, commentaryRefs });
      }
    });

    return { side, dafHeb, tractateHe, entries, tref };

  } catch (err) {
    console.warn(`fetchSide failed for ${tref}:`, err);
    return { side, dafHeb, tractateHe, entries: null, tref };
  }
}

// ── Tab switching ────────────────────────────────────────────
let activeTab = 'halachot';

function switchTab(name) {
  activeTab = name;
  ['halachot', 'mefarshim', 'klalei'].forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('active', t === name);
    const panel = document.getElementById('panel-' + t);
    if (panel) panel.classList.toggle('active', t === name);
  });
}

// ── Render ──────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function sefariaUrl(sourceRef) {
  return `${SEFARIA_BASE}/${encodeURIComponent(sourceRef)}`;
}

const TEXT_LIMIT = 200;
const NO_LIMIT_BOOKS = new Set(['Ben Yehoyada', 'Benayahu', 'Rambam', 'Shulchan Aruch']);

function renderText(text, book) {
  if (NO_LIMIT_BOOKS.has(book)) return { html: esc(text), truncated: false };
  if (text.length <= TEXT_LIMIT) return { html: esc(text), truncated: false };
  return { html: esc(text.slice(0, TEXT_LIMIT)), truncated: true };
}

// Render a single side's HALACHOT content
function renderSideHalachot(res) {
  const { side, dafHeb, tractateHe, entries, tref } = res;
  const anchorId = side === 'א' ? 'side-aleph' : 'side-bet';
  let html = `<div class="side-section" id="${anchorId}">`;
  html += `<div class="results-title">עמוד ${esc(side)} &nbsp;–&nbsp; <span class="daf-badge">${esc(tractateHe)} ${esc(dafHeb)}</span></div>`;

  if (entries === null) {
    html += `<div class="error-box">לא ניתן לטעון את הדף מ-Sefaria (${esc(tref)})</div>`;
  } else {
    const halachotEntries = entries.filter(e => {
      const enabledRefs = e.refs.filter(r => isBookEnabled(r.book));
      return enabledRefs.length > 0;
    });
    if (halachotEntries.length === 0) {
      html += `<div class="empty-msg">לא נמצאו הלכות לעמוד זה</div>`;
    } else {
      html += `<div class="entries">`;
      halachotEntries.forEach((entry, ei) => {
        html += `<div class="entry">
          <div class="entry-head">
            <span class="entry-seg-label">פסקה ${esc(toHebrewNum(ei + 1))}</span>
          </div>
          <div class="entry-body">`;

        entry.refs.filter(r => isBookEnabled(r.book)).forEach((ref) => {
          const cssClass = BOOK_CLASS[ref.book] || 'rambam-ref';
          const icon = BOOK_ICON[ref.book] || '📖';
          const sefUrl = sefariaUrl(ref.sourceRef);
          let bodyHtml, isTruncated;
          if (!ref.text) {
            bodyHtml = '<span style="color:#7a9fc0;font-style:italic">לא נמצא טקסט</span>';
            isTruncated = false;
          } else {
            const result = renderText(ref.text, ref.book);
            bodyHtml = result.html;
            isTruncated = result.truncated;
            if (isTruncated) {
              const truncatedRaw = ref.text.slice(0, TEXT_LIMIT);
              bodyHtml = `<span class="text-toggle" data-full="${escAttr(ref.text)}" data-trunc="${escAttr(truncatedRaw)}">${bodyHtml}</span>`;
              bodyHtml += `<span class="text-truncated-note">… <button class="toggle-text-btn" type="button" data-expanded="false">להרחיב</button></span>`;
            }
          }
          html += `<div class="${cssClass}">
            <div class="ref-header">
              <div class="ref-title">${icon} ${esc(ref.heRef)}</div>
              ${!isTruncated && !NO_LIMIT_BOOKS.has(ref.book) ? `<div class="ref-actions"><a class="link-ws" href="${esc(sefUrl)}" target="_blank" rel="noopener">Sefaria ↗</a></div>` : ''}
            </div>
            <div class="halacha-box">${bodyHtml}</div>
          </div>`;
        });

        html += `</div></div>`;
      });
      html += `</div>`;
    }
  }

  html += `</div>`;
  return html;
}

// Render a single side's MEFARSHIM (commentary) content
function renderSideMefarshim(res) {
  const { side, dafHeb, tractateHe, entries, tref } = res;
  const anchorId = (side === 'א' ? 'mef-side-aleph' : 'mef-side-bet');
  let html = `<div class="side-section" id="${anchorId}">`;
  html += `<div class="results-title">עמוד ${esc(side)} &nbsp;–&nbsp; <span class="daf-badge">${esc(tractateHe)} ${esc(dafHeb)}</span></div>`;

  if (entries === null) {
    html += `<div class="error-box">לא ניתן לטעון את הדף מ-Sefaria (${esc(tref)})</div>`;
  } else {
    const mefEntries = entries.filter(e => {
      const enabledRefs = (e.commentaryRefs || []).filter(r => isBookEnabled(r.book));
      return enabledRefs.length > 0;
    });
    if (mefEntries.length === 0) {
      html += `<div class="empty-msg">לא נמצאו מפרשים לעמוד זה</div>`;
    } else {
      html += `<div class="entries">`;
      mefEntries.forEach((entry, ei) => {
        html += `<div class="entry">
          <div class="entry-head">
            <span class="entry-seg-label">פסקה ${esc(toHebrewNum(ei + 1))}</span>
          </div>
          <div class="entry-body">`;

        entry.commentaryRefs.filter(r => isBookEnabled(r.book)).forEach((ref) => {
          const cssClass = BOOK_CLASS[ref.book] || 'benyehoyada-ref';
          const icon = BOOK_ICON[ref.book] || '📜';
          const sefUrl = sefariaUrl(ref.sourceRef);
          let bodyHtml, isTruncated;
          if (!ref.text) {
            bodyHtml = '<span style="color:#7a9fc0;font-style:italic">לא נמצא טקסט</span>';
            isTruncated = false;
          } else {
            const result = renderText(ref.text, ref.book);
            bodyHtml = result.html;
            isTruncated = result.truncated;
            if (isTruncated) {
              const truncatedRaw = ref.text.slice(0, TEXT_LIMIT);
              bodyHtml = `<span class="text-toggle" data-full="${escAttr(ref.text)}" data-trunc="${escAttr(truncatedRaw)}">${bodyHtml}</span>`;
              bodyHtml += `<span class="text-truncated-note">… <button class="toggle-text-btn" type="button" data-expanded="false">להרחיב</button></span>`;
            }
          }
          html += `<div class="${cssClass}">
            <div class="ref-header">
              <div class="ref-title">${icon} ${esc(ref.heRef)}</div>
              ${!isTruncated && !NO_LIMIT_BOOKS.has(ref.book) ? `<div class="ref-actions"><a class="link-ws" href="${esc(sefUrl)}" target="_blank" rel="noopener">Sefaria ↗</a></div>` : ''}
            </div>
            <div class="halacha-box">${bodyHtml}</div>
          </div>`;
        });

        html += `</div></div>`;
      });
      html += `</div>`;
    }
  }

  html += `</div>`;
  return html;
}

// ── Main search ──────────────────────────────────────────────
let currentSearch = 0;
let lastResults = null;

function renderFromLastResults() {
  if (!lastResults) return;
  const { resAleph, resBet } = lastResults;
  document.getElementById('results-halachot').innerHTML =
    renderSideHalachot(resAleph) + renderSideHalachot(resBet);
  document.getElementById('results-mefarshim').innerHTML =
    renderSideMefarshim(resAleph) + renderSideMefarshim(resBet);
}

async function doSearch() {
  const tractate = document.getElementById('tractate').value;
  const dafNum = parseInt(document.getElementById('daf-num').value, 10);
  if (!tractate || !dafNum) return;

  const searchId = ++currentSearch;
  const dafHeb = toHebrewNum(dafNum);

  document.getElementById('side-nav').style.display = 'none';
  showLoading(`טוען ${tractate} ${dafHeb} מ-Sefaria…`);

  try {
    const [resAleph, resBet] = await Promise.all([
      fetchSide(tractate, dafNum, 'א'),
      fetchSide(tractate, dafNum, 'ב')
    ]);

    if (searchId !== currentSearch) return;

    document.getElementById('results-halachot').innerHTML =
      renderSideHalachot(resAleph) + renderSideHalachot(resBet);

    document.getElementById('results-mefarshim').innerHTML =
      renderSideMefarshim(resAleph) + renderSideMefarshim(resBet);

    document.getElementById('side-nav').style.display = 'flex';

    lastResults = { resAleph, resBet };

  } catch (err) {
    if (searchId !== currentSearch) return;
    console.error(err);
    showError('שגיאה: ' + err.message);
  }
}

function showLoading(msg) {
  document.getElementById('results-halachot').innerHTML =
    `<div class="loading-msg"><div class="spinner"></div>${esc(msg)}</div>`;
  document.getElementById('results-mefarshim').innerHTML = '';
}

function showError(msg) {
  document.getElementById('results-halachot').innerHTML =
    `<div class="error-box">${esc(msg)}</div>`;
  document.getElementById('results-mefarshim').innerHTML = '';
}

// ── Save as PDF ────────────────────────────────────────────────
function saveAsPdf() {
  const tractate = document.getElementById('tractate').value;
  const dafNum = parseInt(document.getElementById('daf-num').value, 10);
  if (!tractate || !dafNum) return;
  const dafHeb = toHebrewNum(dafNum);

  let tabTitle, contentEl;

  if (activeTab === 'halachot') {
    tabTitle = 'הלכות';
    contentEl = document.getElementById('results-halachot');
  } else if (activeTab === 'mefarshim') {
    tabTitle = 'מפרשים';
    contentEl = document.getElementById('results-mefarshim');
  } else {
    tabTitle = 'כללי הגמרא';
    contentEl = document.getElementById('results-klalei');
  }

  const contentHtml = contentEl ? contentEl.innerHTML : '';
  if (!contentHtml.trim()) {
    alert('אין תוכן לשמירה. אנא טען דף תחילה.');
    return;
  }

  const printWin = window.open('', '_blank');
  if (!printWin) {
    alert('לא ניתן לפתוח חלון חדש. אנא בדוק את חוסם החלונות הקופצים.');
    return;
  }

  const pdfStyles = [
    '* { box-sizing: border-box; margin: 0; padding: 0; }',
    'body { font-family: "David","Frank Ruehl CLM","Times New Roman",serif; direction: rtl; color: #000; padding: 30px; font-size: 12pt; line-height: 1.6; }',
    '.pdf-header { text-align: center; margin-bottom: 30px; padding-bottom: 15px; border-bottom: 2px solid #333; }',
    '.pdf-header h1 { font-size: 22pt; margin-bottom: 5px; }',
    '.pdf-header h2 { font-size: 16pt; color: #444; font-weight: normal; }',
    '.side-section { margin-bottom: 25px; }',
    '.results-title { font-size: 14pt; font-weight: bold; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid #999; }',
    '.daf-badge { font-weight: bold; }',
    '.entries { display: flex; flex-direction: column; gap: 10px; }',
    '.entry { border: 1px solid #666; border-radius: 6px; margin-bottom: 10px; page-break-inside: avoid; }',
    '.entry-head { padding: 6px 12px; background: #f0f0f0; border-bottom: 1px solid #999; }',
    '.entry-seg-label { font-weight: bold; font-size: 11pt; }',
    '.entry-body { padding: 8px 12px; }',
    '.ref-header { display: flex; align-items: center; padding: 4px 0; }',
    '.ref-title { font-weight: bold; font-size: 11pt; }',
    '.halacha-box { padding: 8px 12px; border-right: 3px solid #333; white-space: pre-wrap; margin-bottom: 6px; }',
    '.rambam-ref, .tur-ref, .smag-ref, .sa-ref { border: 1px solid #999; border-radius: 4px; margin-bottom: 6px; }',
    '.benyehoyada-ref, .benayahu-ref { border: 1px solid #999; border-radius: 4px; margin-bottom: 6px; }',
    '.klalei-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }',
    '.klal-card { border: 1px solid #666; border-radius: 6px; page-break-inside: avoid; overflow: hidden; }',
    '.klal-card-head { padding: 6px 12px; background: #f0f0f0; border-bottom: 1px solid #999; }',
    '.klal-card-title { font-weight: bold; font-size: 11pt; }',
    '.klal-card-makor { font-size: 9pt; color: #555; margin-top: 2px; }',
    '.klal-card-body { padding: 8px 12px; white-space: pre-wrap; font-size: 11pt; }',
    '.ref-actions, .link-ws, .toggle-text-btn, .text-truncated-note,',
    '.spinner, .loading-msg, .klalei-search-row, .klalei-clear-btn, .klalei-count { display: none !important; }',
    '.empty-msg, .error-box { text-align: center; padding: 20px; color: #666; font-size: 11pt; }',
    '.pdf-header { page-break-after: avoid; }',
    '@page { margin: 20mm 15mm; }',
    '@media print { body { padding: 0; } }'
  ].join('\n');

  const pageTitle = esc(tractate) + ' דף ' + esc(dafHeb) + ' - ' + esc(tabTitle);

  printWin.document.write('<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="UTF-8"><title>' + pageTitle + '</title><style>' + pdfStyles + '</style></head><body>');
  // Only show header title for halachot/mefarshim tabs, not klalei
  if (activeTab !== 'klalei') {
    printWin.document.write('<div class="pdf-header"><h1>' + esc(tractate) + ' דף ' + esc(dafHeb) + '</h1><h2>' + esc(tabTitle) + '</h2></div>');
  }
  printWin.document.write(contentHtml);
  printWin.document.write('<script>document.querySelectorAll(".text-toggle").forEach(function(e){if(e.dataset.full)e.textContent=e.dataset.full});<\/script>');
  printWin.document.write('</body></html>');
  printWin.document.close();
  printWin.focus();

  setTimeout(function () { printWin.print(); }, 500);
}

// ── Klalei Gemara search and render ──────────────────────────

function renderKlalei(filter) {
  const resultsContainer = document.getElementById('results-klalei');
  const countEl = document.getElementById('klalei-count');
  const clearBtn = document.getElementById('klalei-clear');
  if (!resultsContainer) return;

  const q = (filter || '').trim();

  if (clearBtn) clearBtn.style.display = q ? 'block' : 'none';

  const items = q
    ? KLALEI_DATA.filter(r => r.klal.includes(q))
    : KLALEI_DATA;

  if (countEl) countEl.textContent = items.length + ' כללים';

  let html = '';
  if (items.length === 0) {
    html = '<div class="empty-msg">לא נמצאו כללים תואמים</div>';
  } else {
    html = '<div class="klalei-grid">';
    items.forEach(r => {
      const makorLine = r.makor
        ? `<div class="klal-card-makor">מקור: ${esc(r.makor)}</div>` : '';
      html += `<div class="klal-card">
        <div class="klal-card-head">
          <div class="klal-card-title">${esc(r.klal)}</div>
          ${makorLine}
        </div>
        <div class="klal-card-body">${esc(r.hesber || '—')}</div>
      </div>`;
    });
    html += '</div>';
  }
  resultsContainer.innerHTML = html;
}

function clearKlaleiSearch() {
  const input = document.getElementById('klalei-search');
  if (input) {
    input.value = '';
    input.focus();
  }
  renderKlalei('');
}

// Patch switchTab to lazy-init klalei panel
const _origSwitchTab = switchTab;
switchTab = function (name) {
  _origSwitchTab(name);
  if (name === 'klalei') {
    renderKlalei(document.getElementById('klalei-search')?.value || '');
  }
};

// ── Toggle truncated text expand/collapse ────────────────────
document.addEventListener('click', function (e) {
  const btn = e.target.closest('.toggle-text-btn');
  if (!btn) return;
  const container = btn.closest('.halacha-box');
  if (!container) return;
  const toggleSpan = container.querySelector('.text-toggle');
  if (!toggleSpan) return;
  const expanded = btn.dataset.expanded === 'true';
  if (expanded) {
    toggleSpan.innerHTML = esc(toggleSpan.dataset.trunc);
    btn.textContent = 'להרחיב';
    btn.dataset.expanded = 'false';
  } else {
    toggleSpan.innerHTML = esc(toggleSpan.dataset.full);
    btn.textContent = 'לצמצם';
    btn.dataset.expanded = 'true';
  }
});

