// Tests for Code.js with Node's built-in runner: node --test
// The Sheets, Mail and trigger services are replaced by small fakes, so the Apps Script entry points
// run end to end here. (They were not run in a live Google account.)
const test = require('node:test');
const assert = require('node:assert/strict');
const app = require('./Code.js');

class FakeSheet {
  constructor(name, data = []) { this.name = name; this.data = data; }
  getDataRange() { return { getValues: () => this.data.map(r => r.slice()) }; }
  getRange(row, col, nRows, nCols) {
    return {
      setValues: values => {
        assert.equal(values.length, nRows, 'row count must match the range');
        values.forEach((r, i) => {
          assert.equal(r.length, nCols, 'column count must match the range');
          this.data[row - 1 + i] = this.data[row - 1 + i] || [];
          r.forEach((v, j) => { this.data[row - 1 + i][col - 1 + j] = v; });
        });
      },
    };
  }
  clearContents() { this.data = []; }
}

class FakeSpreadsheet {
  constructor(sheets) { this.sheets = new Map(sheets.map(s => [s.name, s])); }
  getSheetByName(name) { return this.sheets.get(name) || null; }
  insertSheet(name) { const s = new FakeSheet(name); this.sheets.set(name, s); return s; }
}

const RAW = [
  ['Date', 'Name', 'Email', 'Phone', 'Status', 'Amount'],
  ['2026-11-03', '  anne-marie  SMITH ', 'Anne.Smith@Example.com ', '555 123 4567', 'quote sent', '$1,200.00'],
  [new Date(2026, 10, 4), "o'neil, pat", 'pat@example.com', '+1 (555) 987-6543', 'WON', 850],
  ['11/05/2026', '김민지', 'minji@example.com', '010-0000-1234', 'New', ''],
  ['3 Nov 2026', 'Pat Oneil', 'PAT@example.com', '5559876543', 'contacted', '300'], // same e-mail, older: dropped
  ['2026-11-06', 'No Email', 'not-an-email', '', 'New', '50'],
  ['2026-02-30', 'Bad Date', 'bad@example.com', '', 'Lost', '10'],
  ['2026-11-07', 'Odd Status', 'odd@example.com', '', 'maybe', 'abc'],
  ['', '', '', '', '', ''],
  ['2026.11.08', 'lost lead', 'lost@example.com', '', 'Closed Lost', '400'],
];

test('normalizers', () => {
  assert.equal(app.normalizeName('  anne-marie  SMITH '), 'Anne-Marie Smith');
  assert.equal(app.normalizeName("o'neil"), "O'Neil");
  assert.equal(app.normalizeName('김민지'), '김민지');
  assert.equal(app.normalizeEmail(' A@B.co '), 'a@b.co');
  assert.equal(app.normalizeEmail('a@b'), '');
  assert.equal(app.normalizePhone('555 123 4567'), '(555) 123-4567');
  assert.equal(app.normalizePhone('+1 555-123-4567'), '(555) 123-4567');
  assert.equal(app.normalizePhone('01000001234'), '010-0000-1234');
  assert.equal(app.normalizePhone('12345'), '12345');
  for (const s of ['2026-11-03', '2026.11.3', '11/03/2026', '3 Nov 2026', '3 November 2026']) assert.equal(app.normalizeDate(s), '2026-11-03', s);
  assert.equal(app.normalizeDate(new Date(2026, 10, 3)), '2026-11-03');
  assert.equal(app.normalizeDate('2026-02-30'), '');
  assert.equal(app.normalizeDate('soon'), '');
  assert.equal(app.normalizeStatus(' Closed  Won '), 'Won');
  assert.equal(app.normalizeStatus('maybe'), '');
  assert.equal(app.parseAmount('$1,200.50'), 1200.5);
  assert.equal(app.parseAmount('(42.00)'), -42);
  assert.equal(app.parseAmount(''), 0);
  assert.equal(app.parseAmount('abc'), null);
  assert.equal(app.parseAmount(7), 7);
  assert.equal(app.parseAmount('₩120,000'), 120000);
  assert.equal(app.parseAmount('1,200원'), 1200);
  assert.equal(app.parseAmount('12만원'), null, 'never half-read a number');
});

test('Korean settings: Korean sheet names, statuses, issue texts and summary', () => {
  const saved = { ...app.CONFIG };
  Object.assign(app.CONFIG, app.CONFIG_KO);
  try {
    const rows = [
      ['2026-11-09', '홍길동', 'hong@example.com', '01000001111', '견적 보냄', '1,200,000원'],
      ['2026.11.10', '이영희', 'lee@example.com', '010 0000 2222', '계약 완료', '₩850,000'],
      ['2026-11-10', '김철수', 'kim@example.com', '', '새 문의', '12만원'],
      ['2026-11-11', '박민지', '', '', '무산', '0'],
    ];
    const { clean, issues } = app.cleanRows(rows);
    assert.deepEqual(clean.map(r => [r.name, r.phone, r.status, r.amount]), [
      ['홍길동', '010-0000-1111', '견적 보냄', 1200000],
      ['이영희', '010-0000-2222', '계약', 850000],
    ]);
    assert.deepEqual(issues, [[4, '금액', '12만원', '숫자가 아님'], [5, '이메일', '', '이메일이 없거나 형식이 틀림']]);
    assert.equal(app.summaryText(app.summarize(clean), issues.length, '2026-11-11'),
      ['문의 요약 2026-11-11', '', '문의: 2', '  견적 보냄: 1', '  계약: 1', '', '진행 중 금액: 1200000.00', '계약 금액: 850000.00', '확인할 행: 2'].join('\n'));
  } finally {
    Object.assign(app.CONFIG, saved);
  }
  assert.equal(app.normalizeStatus('won'), 'Won', 'English settings are back');
});

test('cleanUpSheet writes Clean and Issues, and a second run gives the same result', () => {
  const ss = new FakeSpreadsheet([new FakeSheet('Leads', RAW.map(r => r.slice()))]);
  global.SpreadsheetApp = { getActive: () => ss };
  for (let run = 0; run < 2; run++) {
    const res = app.cleanUpSheet();
    assert.equal(res.duplicates, 1);
    assert.deepEqual(ss.getSheetByName('Clean').data, [
      ['Date', 'Name', 'Email', 'Phone', 'Status', 'Amount'],
      ['2026-11-03', 'Anne-Marie Smith', 'anne.smith@example.com', '(555) 123-4567', 'Quote sent', 1200],
      ['2026-11-04', "O'Neil, Pat", 'pat@example.com', '(555) 987-6543', 'Won', 850],
      ['2026-11-05', '김민지', 'minji@example.com', '010-0000-1234', 'New', 0],
      ['2026-11-08', 'Lost Lead', 'lost@example.com', '', 'Lost', 400],
    ]);
    assert.deepEqual(ss.getSheetByName('Issues').data, [
      ['Row', 'Field', 'Value', 'Problem'],
      [6, 'Email', 'not-an-email', 'missing or not an e-mail'],
      [7, 'Date', '2026-02-30', 'not a date'],
      [8, 'Status', 'maybe', 'unknown status'],
      [8, 'Amount', 'abc', 'not a number'],
    ]);
  }
  assert.deepEqual(ss.getSheetByName('Leads').data, RAW, 'the raw sheet is never changed');
});

test('sendDailySummary e-mails the summary when an address is set', () => {
  const ss = new FakeSpreadsheet([new FakeSheet('Leads', RAW.map(r => r.slice()))]);
  const sent = [];
  global.SpreadsheetApp = { getActive: () => ss };
  global.MailApp = { sendEmail: (...a) => sent.push(a) };
  app.CONFIG.summaryTo = 'owner@example.com';
  const body = app.sendDailySummary();
  app.CONFIG.summaryTo = '';
  const today = app.normalizeDate(new Date());
  assert.equal(body, [`Lead summary ${today}`, '', 'Leads: 4', '  New: 1', '  Quote sent: 1', '  Won: 1', '  Lost: 1', '',
    'Open pipeline: 1200.00', 'Won: 850.00', 'Rows that need a look: 4'].join('\n'));
  assert.deepEqual(sent, [['owner@example.com', `Lead summary ${today}`, body]]);
  app.sendDailySummary();
  assert.equal(sent.length, 1, 'no address, no e-mail');
});

test('installDailyTrigger replaces only its own trigger', () => {
  const triggers = ['sendDailySummary', 'somethingElse'].map(fn => ({ fn, getHandlerFunction: () => fn }));
  const deleted = [], created = [];
  global.ScriptApp = {
    getProjectTriggers: () => triggers,
    deleteTrigger: t => deleted.push(t.fn),
    newTrigger: fn => {
      const spec = { fn };
      const b = { timeBased: () => b, everyDays: n => { spec.days = n; return b; }, atHour: h => { spec.hour = h; return b; }, create: () => created.push(spec) };
      return b;
    },
  };
  app.installDailyTrigger();
  assert.deepEqual(deleted, ['sendDailySummary']);
  assert.deepEqual(created, [{ fn: 'sendDailySummary', days: 1, hour: 8 }]);
});
