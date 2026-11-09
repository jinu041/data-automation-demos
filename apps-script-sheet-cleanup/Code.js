// Google Sheets cleanup and daily summary, written for Apps Script (V8 runtime).
// Paste into Extensions > Apps Script. The pure functions are also exported for Node,
// so test.js can check them, and the Sheets glue code, without a Google account.

const CONFIG = {
  rawSheet: 'Leads',     // where people paste or a form writes rows
  cleanSheet: 'Clean',   // rewritten on every run
  issuesSheet: 'Issues', // rows that need a human look
  summaryTo: '',         // e-mail for the daily summary; leave blank to skip sending
  headers: ['Date', 'Name', 'Email', 'Phone', 'Status', 'Amount'],
};

const STATUSES = { 'new': 'New', 'contacted': 'Contacted', 'quote sent': 'Quote sent', 'quoted': 'Quote sent',
  'won': 'Won', 'closed won': 'Won', 'lost': 'Lost', 'closed lost': 'Lost' };

function normalizeName(s) {
  return String(s || '').trim().replace(/\s+/g, ' ').toLowerCase()
    .replace(/(^|[\s'-])(\p{L})/gu, (m, sep, ch) => sep + ch.toUpperCase());
}

function normalizeEmail(s) {
  const e = String(s || '').trim().toLowerCase();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e) ? e : '';
}

function normalizePhone(s) {
  const raw = String(s || '').trim();
  const d = raw.replace(/\D/g, '');
  if (d.length === 10) return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;            // US
  if (d.length === 11 && d.startsWith('010')) return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`; // Korean mobile
  if (d.length === 11 && d.startsWith('1')) return `(${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7)}`; // US with 1
  return raw;
}

const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

// Returns 'YYYY-MM-DD' or '' when the value is not a real date. Dates from the sheet are read in the
// script's time zone; text is read as 2026-11-03, 2026.11.03, 11/03/2026 (US order) or 3 Nov 2026.
function normalizeDate(v) {
  let y, m, d;
  if (v instanceof Date) {
    if (isNaN(v)) return '';
    [y, m, d] = [v.getFullYear(), v.getMonth() + 1, v.getDate()];
  } else {
    const s = String(v || '').trim();
    let r;
    if ((r = s.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$/))) [y, m, d] = [+r[1], +r[2], +r[3]];
    else if ((r = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/))) [y, m, d] = [+r[3], +r[1], +r[2]];
    else if ((r = s.match(/^(\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4})$/)) && MONTHS[r[2].toLowerCase()]) [y, m, d] = [+r[3], MONTHS[r[2].toLowerCase()], +r[1]];
    else return '';
    const check = new Date(y, m - 1, d);
    if (check.getFullYear() !== y || check.getMonth() !== m - 1 || check.getDate() !== d) return ''; // 2026-02-30
  }
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function normalizeStatus(s) {
  return STATUSES[String(s || '').trim().toLowerCase().replace(/\s+/g, ' ')] || '';
}

function parseAmount(v) {
  if (typeof v === 'number') return v;
  const s = String(v || '').trim();
  if (!s) return 0;
  const neg = /^\(.*\)$/.test(s) || s.startsWith('-');
  const n = parseFloat(s.replace(/[^\d.]/g, ''));
  return isNaN(n) ? null : (neg ? -n : n);
}

// rows: values under the header. Returns clean rows (one per e-mail, newest date wins), issues and a duplicate count.
function cleanRows(rows) {
  const issues = [];
  const byEmail = new Map();
  let duplicates = 0;
  rows.forEach((r, i) => {
    if (r.every(c => c === '' || c === null)) return; // blank line
    const line = i + 2; // sheet row number
    const rec = { date: normalizeDate(r[0]), name: normalizeName(r[1]), email: normalizeEmail(r[2]),
      phone: normalizePhone(r[3]), status: normalizeStatus(r[4]), amount: parseAmount(r[5]) };
    const problems = [];
    if (!rec.email) problems.push(['Email', r[2], 'missing or not an e-mail']);
    if (!rec.date) problems.push(['Date', r[0], 'not a date']);
    if (!rec.status) problems.push(['Status', r[4], 'unknown status']);
    if (rec.amount === null) problems.push(['Amount', r[5], 'not a number']);
    if (problems.length) {
      problems.forEach(([field, value, problem]) => issues.push([line, field, String(value), problem]));
      return;
    }
    const prev = byEmail.get(rec.email);
    if (prev) {
      duplicates++;
      if (rec.date < prev.date) return; // keep the newest row for this e-mail
    }
    byEmail.set(rec.email, rec);
  });
  const clean = [...byEmail.values()].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.email < b.email ? -1 : 1));
  return { clean, issues, duplicates };
}

function summarize(clean) {
  const byStatus = {};
  let won = 0, open = 0;
  clean.forEach(r => {
    byStatus[r.status] = (byStatus[r.status] || 0) + 1;
    if (r.status === 'Won') won += r.amount;
    else if (r.status !== 'Lost') open += r.amount;
  });
  return { total: clean.length, byStatus, won: Math.round(won * 100) / 100, open: Math.round(open * 100) / 100 };
}

function summaryText(s, issues, dateStr) {
  const order = ['New', 'Contacted', 'Quote sent', 'Won', 'Lost'];
  const lines = order.filter(k => s.byStatus[k]).map(k => `  ${k}: ${s.byStatus[k]}`);
  return [`Lead summary for ${dateStr}`, '', `Leads: ${s.total}`, ...lines, '',
    `Open pipeline: ${s.open.toFixed(2)}`, `Won: ${s.won.toFixed(2)}`, `Rows that need a look: ${issues}`].join('\n');
}

const toRow = r => [r.date, r.name, r.email, r.phone, r.status, r.amount];

// ---- Apps Script entry points (use SpreadsheetApp, MailApp, ScriptApp) ----

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Cleanup').addItem('Clean up now', 'cleanUpSheet')
    .addItem('Send summary now', 'sendDailySummary').addToUi();
}

function writeSheet(ss, name, header, rows) {
  const sh = ss.getSheetByName(name) || ss.insertSheet(name);
  sh.clearContents();
  sh.getRange(1, 1, 1, header.length).setValues([header]);
  if (rows.length) sh.getRange(2, 1, rows.length, header.length).setValues(rows);
  return sh;
}

function cleanUpSheet() {
  const ss = SpreadsheetApp.getActive();
  const raw = ss.getSheetByName(CONFIG.rawSheet);
  if (!raw) throw new Error(`No sheet called "${CONFIG.rawSheet}"`);
  const rows = raw.getDataRange().getValues().slice(1);
  const result = cleanRows(rows);
  writeSheet(ss, CONFIG.cleanSheet, CONFIG.headers, result.clean.map(toRow));
  writeSheet(ss, CONFIG.issuesSheet, ['Row', 'Field', 'Value', 'Problem'], result.issues);
  return result;
}

function sendDailySummary() {
  const result = cleanUpSheet();
  const today = normalizeDate(new Date());
  const body = summaryText(summarize(result.clean), result.issues.length, today);
  if (CONFIG.summaryTo) MailApp.sendEmail(CONFIG.summaryTo, `Lead summary ${today}`, body);
  return body;
}

// Run once by hand: sends the summary every morning at about 8 (script time zone).
function installDailyTrigger() {
  ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'sendDailySummary')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('sendDailySummary').timeBased().everyDays(1).atHour(8).create();
}

if (typeof module !== 'undefined') {
  module.exports = { CONFIG, normalizeName, normalizeEmail, normalizePhone, normalizeDate, normalizeStatus,
    parseAmount, cleanRows, summarize, summaryText, cleanUpSheet, sendDailySummary, installDailyTrigger };
}
