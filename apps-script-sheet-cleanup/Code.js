// Google Sheets cleanup and daily summary, written for Apps Script (V8 runtime).
// Paste into Extensions > Apps Script. The pure functions are also exported for Node,
// so test.js can check them, and the Sheets glue code, without a Google account.

const CONFIG = {
  rawSheet: 'Leads',     // where people paste or a form writes rows
  cleanSheet: 'Clean',   // rewritten on every run
  issuesSheet: 'Issues', // rows that need a human look
  summaryTo: '',         // e-mail for the daily summary; leave blank to skip sending
  headers: ['Date', 'Name', 'Email', 'Phone', 'Status', 'Amount'],
  issuesHeader: ['Row', 'Field', 'Value', 'Problem'],
  // every spelling people type (lower case) -> the label you want in Clean; the order of labels is the summary order
  statuses: { 'new': 'New', 'contacted': 'Contacted', 'quote sent': 'Quote sent', 'quoted': 'Quote sent',
    'won': 'Won', 'closed won': 'Won', 'lost': 'Lost', 'closed lost': 'Lost' },
  won: 'Won',
  lost: 'Lost',
  amountFormat: '#,##0.00',
  problems: { email: 'missing or not an e-mail', date: 'not a date', status: 'unknown status', amount: 'not a number' },
  menu: { name: 'Cleanup', clean: 'Clean up now', send: 'Send summary now' },
  summary: { title: 'Lead summary', leads: 'Leads', open: 'Open pipeline', won: 'Won', issues: 'Rows that need a look' },
};

// The same script in Korean: add the line `Object.assign(CONFIG, CONFIG_KO);` right after this block.
const CONFIG_KO = {
  rawSheet: '문의', cleanSheet: '정리', issuesSheet: '확인 필요',
  headers: ['날짜', '이름', '이메일', '전화', '상태', '금액'],
  issuesHeader: ['행', '항목', '값', '문제'],
  statuses: { '신규': '신규', '새 문의': '신규', '연락': '연락함', '연락함': '연락함', '견적': '견적 보냄', '견적 보냄': '견적 보냄',
    '계약': '계약', '계약 완료': '계약', '취소': '취소', '무산': '취소' },
  won: '계약',
  lost: '취소',
  amountFormat: '#,##0',
  problems: { email: '이메일이 없거나 형식이 틀림', date: '날짜가 아님', status: '모르는 상태', amount: '숫자가 아님' },
  menu: { name: '정리', clean: '지금 정리', send: '요약 메일 보내기' },
  summary: { title: '문의 요약', leads: '문의', open: '진행 중 금액', won: '계약 금액', issues: '확인할 행' },
};

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
  const key = String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');
  return Object.prototype.hasOwnProperty.call(CONFIG.statuses, key) ? CONFIG.statuses[key] : '';
}

// '$1,200.00', '₩120,000', '1,200원' and '(42.00)' are numbers; text such as '12만원' or 'abc' is null (an issue),
// so a value is never half-read.
function parseAmount(v) {
  if (typeof v === 'number') return v;
  let s = String(v || '').trim();
  if (!s) return 0;
  const accounting = s.startsWith('(') && s.endsWith(')');
  if (accounting) s = s.slice(1, -1).trim();
  const match = s.match(/^([+-]?)\s*(?:(?:usd|krw|eur|gbp|[$€£₩¥원])\s*)?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(?:usd|krw|eur|gbp|[$€£₩¥원])?$/i);
  if (!match || (accounting && match[1])) return null;
  return (accounting || match[1] === '-' ? -1 : 1) * Number(match[2].replace(/,/g, ''));
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
    const [hDate, , hEmail, , hStatus, hAmount] = CONFIG.headers;
    if (!rec.email) problems.push([hEmail, r[2], CONFIG.problems.email]);
    if (!rec.date) problems.push([hDate, r[0], CONFIG.problems.date]);
    if (!rec.status) problems.push([hStatus, r[4], CONFIG.problems.status]);
    if (rec.amount === null) problems.push([hAmount, r[5], CONFIG.problems.amount]);
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
    if (r.status === CONFIG.won) won += r.amount;
    else if (r.status !== CONFIG.lost) open += r.amount;
  });
  return { total: clean.length, byStatus, won: Math.round(won * 100) / 100, open: Math.round(open * 100) / 100 };
}

function summaryText(s, issues, dateStr) {
  const t = CONFIG.summary;
  const order = [...new Set(Object.values(CONFIG.statuses))];
  const lines = order.filter(k => s.byStatus[k]).map(k => `  ${k}: ${s.byStatus[k]}`);
  return [`${t.title} ${dateStr}`, '', `${t.leads}: ${s.total}`, ...lines, '',
    `${t.open}: ${s.open.toFixed(2)}`, `${t.won}: ${s.won.toFixed(2)}`, `${t.issues}: ${issues}`].join('\n');
}

const toRow = r => [r.date, r.name, r.email, r.phone, r.status, r.amount];

// ---- Apps Script entry points (use SpreadsheetApp, MailApp, ScriptApp) ----

function onOpen() {
  const m = CONFIG.menu;
  SpreadsheetApp.getUi().createMenu(m.name).addItem(m.clean, 'cleanUpSheet').addItem(m.send, 'sendDailySummary').addToUi();
}

function writeSheet(ss, name, header, rows) {
  const sh = ss.getSheetByName(name) || ss.insertSheet(name);
  sh.clearContents();
  const values = [header, ...rows].map(row => row.map(value =>
    typeof value === 'string' && value.startsWith('=') ? "'" + value : value));
  sh.getRange(1, 1, values.length, header.length).setValues(values);
  return sh;
}

function cleanUpSheet() {
  const ss = SpreadsheetApp.getActive();
  const raw = ss.getSheetByName(CONFIG.rawSheet);
  if (!raw) throw new Error(`No sheet called "${CONFIG.rawSheet}"`);
  const rows = raw.getDataRange().getValues().slice(1);
  const result = cleanRows(rows);
  const clean = writeSheet(ss, CONFIG.cleanSheet, CONFIG.headers, result.clean.map(toRow));
  if (result.clean.length) clean.getRange(2, CONFIG.headers.length, result.clean.length, 1).setNumberFormat(CONFIG.amountFormat);
  writeSheet(ss, CONFIG.issuesSheet, CONFIG.issuesHeader, result.issues);
  return result;
}

function sendDailySummary() {
  const result = cleanUpSheet();
  const today = normalizeDate(new Date());
  const body = summaryText(summarize(result.clean), result.issues.length, today);
  if (CONFIG.summaryTo) MailApp.sendEmail(CONFIG.summaryTo, `${CONFIG.summary.title} ${today}`, body);
  return body;
}

// Run once by hand: sends the summary every morning at about 8 (script time zone).
function installDailyTrigger() {
  ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'sendDailySummary')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('sendDailySummary').timeBased().everyDays(1).atHour(8).create();
}

if (typeof module !== 'undefined') {
  module.exports = { CONFIG, CONFIG_KO, normalizeName, normalizeEmail, normalizePhone, normalizeDate, normalizeStatus,
    parseAmount, cleanRows, summarize, summaryText, cleanUpSheet, sendDailySummary, installDailyTrigger };
}
