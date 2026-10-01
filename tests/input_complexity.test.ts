import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { parseSimaiChart } from '../src/simai/core/parser/SimaiParser';
import { inputComplexity } from '../src/algorithm/input-complexity';
import { inputOnsets, inputDistance, keyboardRhythmComplexity } from '../src/algorithm/rhythm-complexity';
import {corpusFile} from './corpus';
const parse = (body: string) => parseSimaiChart(`&inote_5=${body},E`, 5);
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-8 * Math.max(1, Math.abs(a), Math.abs(b)), `${a} != ${b}`);

test('Touch HOLD, button HOLD and Touch attacks contribute source-backed continuous lock load', () => {
  const chart = parse('(120){8}E5h[4:4]/8h[4:2],B4,B5,7,B4,B5,7');
  const result = inputComplexity(chart), main = result.windows.find(w => w.holdKind === 'touch-hold-start')!;
  assert.ok(main.raw > 0 && result.touchRaw > 0);
  assert.equal(main.touchCount, 4); assert.equal(main.holdCount, 1);
  assert.equal(main.dualHeldTouchCount, 2);
  assert.ok(main.inputs.every(i => i.heldIds.includes(main.holdId) && i.source.text && Number.isFinite(i.beat)));
  assert.ok(main.inputs.some(i => i.kind === 'touch' && i.pressure > 0));
  assert.equal(chart.notes.filter(n => n.type === 'slide').length, 0);
});

test('a Touch at another HOLD tail is a transition, not simultaneous double-held Touch', () => {
  const chart = parse('(120){4}E5h[4:8]/8h[4:1],B4,B5');
  const main = inputComplexity(chart).windows.find(w => w.holdKind === 'touch-hold-start')!;
  assert.equal(main.dualHeldTouchCount, 0);
  assert.ok(main.inputs.filter(i => i.kind === 'touch').every(i => i.heldIds.length === 1));
});

test('an isolated long Touch HOLD has no lock load and Touch-free keyboard retains its baseline', () => {
  const isolated = inputComplexity(parse('(120){4}E5h[4:32]'));
  assert.equal(isolated.raw, 0); assert.deepEqual(isolated.windows, []);
  assert.ok(isolated.touchRaw > 0); assert.equal(isolated.touchHoldCount, 1);
  const keys = inputComplexity(parse('(120){8}1h[4:4],5,2h[4:2],6,3,7'));
  assert.equal(keys.raw, 0); assert.equal(keys.touchRaw, 0); assert.deepEqual(keys.windows, []);
});

test('short / pseudo HOLD occupancy is attenuated rather than treated as a full hand lock', () => {
  const long = inputComplexity(parse('(120){16}E5h[4:8]/8h[4:8],B4,B5,7,B4'));
  const short = inputComplexity(parse('(120){16}E5h[4:8]/8h[64:1],B4,B5,7,B4'));
  const a = long.windows.find(w => w.holdPosition === 'E5')!, b = short.windows.find(w => w.holdPosition === 'E5')!;
  assert.ok(a.components.coordination > b.components.coordination);
  assert.equal(b.dualHeldTouchCount, 0);
});

test('equivalent BPM / division and specified-second HOLD writes retain physical lock load', () => {
  const a = inputComplexity(parse('(120){8}E5h[4:4]/8h[4:2],B4,B5,7,B4'));
  const b = inputComplexity(parse('(240){4}E5h[4:8]/8h[4:4],B4,B5,7,B4'));
  const c = inputComplexity(parse('(120){8}E5h[#2]/8h[#1],B4,B5,7,B4'));
  for (const other of [b, c]) {
    close(a.raw, other.raw); close(a.touchRaw, other.touchRaw);
    assert.equal(a.windows.length, other.windows.length);
    a.windows.forEach((w, i) => { close(w.startMs, other.windows[i]!.startMs); close(w.endMs, other.windows[i]!.endMs); });
  }
});

test('Touch rhythm uses the same irregular attack calculation and keeps actual sensor geometry', () => {
  const rhythm = keyboardRhythmComplexity(parse('(120){16}B4,,,B5,B4,,,B5,B4,,,B5'));
  assert.ok(rhythm.raw > 0 && rhythm.windows[0]!.movementMean > 0);
  assert.equal(inputDistance('C', 'C1'), 0); assert.equal(inputDistance('C', 'C2'), 0);
  assert.ok(inputDistance('E5', 8) > inputDistance('E5', 'B5'));
  assert.ok(rhythm.windows[0]!.onsets.every(o => o.kinds.every(k => k === 'touch')));
});

test('Touch / Touch HOLD share onset groups, IDs are unique and metadata does not affect workload', () => {
  const chart = parse('(120){8}E5h[4:4]/B4/1,B5,8h[4:2],B4');
  const original = inputComplexity(chart);
  const altered = inputComplexity({ ...chart, notes: [...chart.notes, chart.notes[0]!], title: 'other', level: { ...chart.level, master: '15' } });
  assert.deepEqual(altered, original);
  const groups = inputOnsets(chart);
  assert.equal(groups[0]!.noteIds.length, 3);
  assert.ok(groups[0]!.kinds.includes('touch') && groups[0]!.kinds.includes('touch-hold-start'));
});

test('mines and headless Slide are not input attacks; headed Slide remains lock context', () => {
  const chart = parse('(120){4}E5h[4:8],1m,2-6[4:1]?,3-7[4:1],B4');
  const main = inputComplexity(chart).windows.find(w => w.holdKind === 'touch-hold-start')!;
  const mines = new Set(chart.notes.filter(n => n.isMine).map(n => n.id));
  assert.ok(main.noteIds.every(id => !mines.has(id)));
  assert.equal(main.inputs.filter(i => i.kind === 'slide').length, 1);
});

const realFile = corpusFile('27. CiRCLE PLUS/TECHNOPOLIS 2085');
test('TECHNOPOLIS 2085 MASTER retains every E5 lock and five genuinely overlapping Touch attacks in the first', {
  skip: !realFile,
}, () => {
  const chart = parseSimaiChart(fs.readFileSync(realFile!, 'utf8'), 5);
  const result = inputComplexity(chart);
  assert.equal(result.touchTapCount, 119); assert.equal(result.touchHoldCount, 17);
  const first = result.windows.find(w => w.holdId === 164)!;
  assert.equal(first.touchCount, 11); assert.equal(first.holdCount, 5); assert.equal(first.dualHeldTouchCount, 5);
  assert.deepEqual(first.inputs.filter(i => i.kind === 'touch' && i.pressure > 0).map(i => i.noteId), [169, 172, 175, 178, 181]);
  for (const id of [164, 193, 232, 269, 307, 342]) assert.ok(result.windows.find(w => w.holdId === id)!.raw > 0);
  assert.ok(first.startMs > 30447 && first.endMs < 35598 && first.source.text === 'E5h[8:23]');
});
