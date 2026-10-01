import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { parseSimaiChart } from '../src/simai/core/parser/SimaiParser';
import { keyboardRhythmComplexity, rhythmComplexity, KEYBOARD_RHYTHM_VERSION } from '../src/algorithm/rhythm-complexity';
import {corpusFile} from './corpus';

const parse = (body: string) => parseSimaiChart(`&title=unused\n&inote_5=${body},E`, 5);
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b)), `${a} != ${b}`);
const cumulative = (gaps: number[]) => gaps.reduce((out, gap) => [...out, out.at(-1)! + gap], [0]);
function stream(count: number, gapCounts: readonly number[], keys: readonly string[]) {
  const tokens: string[] = [];
  for (let i = 0; i < count; i++) {
    tokens.push(keys[i % keys.length]!);
    if (i + 1 < count) tokens.push(...Array(gapCounts[i % gapCounts.length]! - 1).fill(''));
  }
  return tokens.join(',');
}

test('constant IOI and insufficient rhythm evidence have exact zero burden', () => {
  for (const beats of [[], [0], [0, .5], [0, .5, 1, 1.5, 2], [0, .3, .6, .9, 1.2]])
    assert.equal(rhythmComplexity(beats).raw, 0);
});

test('relative beat irregularity is invariant to origin, tempo notation scaling and input order', () => {
  const beats = cumulative([.75, .25, .75, .25, .75, .25, .75, .25]);
  const base = rhythmComplexity(beats);
  const rewritten = rhythmComplexity(beats.map(beat => 8 + beat * 2).reverse());
  close(rewritten.raw, base.raw);
  rewritten.normalizedIOIs.forEach((value, i) => close(value, base.normalizedIOIs[i]!));
  assert.deepEqual(rewritten.repeatedMotif, base.repeatedMotif);
  assert.ok(base.raw > rhythmComplexity(Array.from({ length: beats.length }, (_, i) => i / 2)).raw);
});

test('repeated long-short rhythm keeps execution burden without repeated novelty claims', () => {
  const repeated = rhythmComplexity(cumulative(Array.from({ length: 16 }, (_, i) => i % 2 ? .25 : .75)));
  const disrupted = rhythmComplexity(cumulative([.75, .25, .75, .25, .25, .75, .25, .75, .75, .75, .25, .25, .75, .25, .25, .75]));
  assert.equal(repeated.repeatedMotif.period, 2);
  assert.equal(repeated.repeatedMotif.repetitions, 8);
  assert.ok(repeated.alternationBurden > 1);
  assert.ok(repeated.raw > 0);
  assert.ok(repeated.surprise < disrupted.surprise);
  assert.ok(repeated.surprise < repeated.alternationBurden);
});

test('same-beat copies do not create zero IOIs or multiply rhythm attacks', () => {
  const base = rhythmComplexity([0, .75, 1, 1.75, 2]);
  assert.deepEqual(rhythmComplexity([2, 0, .75, 0, 1, 1.75, 2, 1]), base);
  assert.throws(() => rhythmComplexity([0, Infinity]), /Non-finite/);
  assert.throws(() => rhythmComplexity([NaN]), /Non-finite/);
});

test('irregular rhythm plus displacement is greater than the same repeated-key rhythm', () => {
  const body = stream(17, [3, 1], ['1', '5']);
  const moving = keyboardRhythmComplexity(parse(`(120){16}${body}`));
  const sameKey = keyboardRhythmComplexity(parse(`(120){16}${stream(17, [3, 1], ['1'])}`));
  assert.ok(moving.raw > sameKey.raw && sameKey.raw > 0);
  assert.equal(moving.windows[0]!.movementMean, 4);
  assert.equal(sameKey.windows[0]!.movementMean, 0);
  close(moving.raw, sameKey.raw * 2);
});

test('regular fast or wide source streams remain zero in this rhythm-only view', () => {
  const result = keyboardRhythmComplexity(parse(`(240){32}${stream(33, [1], ['1', '5'])}`));
  assert.equal(result.raw, 0);
  assert.ok(result.windows.every(window => window.raw === 0 && window.movementMean === 4));
});

test('one long phrase-ending rest is not a repeated uneven rhythm execution burden', () => {
  const repeated = keyboardRhythmComplexity(parse(`(120){16}${stream(17, [3, 1], ['1'])}`));
  const makeRest = (commas: number) => keyboardRhythmComplexity(parse(`(120){16}${stream(17,
    [...Array(8).fill(1), commas, ...Array(7).fill(1)], ['1'])}`));
  const rest = makeRest(16), longer = makeRest(32), longest = makeRest(256);
  assert.ok(rest.windows[0]!.rhythm.raw > 0, 'structural pause remains auditable');
  assert.ok(repeated.raw > rest.raw * 3, 'repeated long-short execution must exceed isolated recovery');
  assert.ok(rest.raw > longer.raw && longer.raw > longest.raw);
  assert.ok(longest.raw < .05);
  close(rest.windows[0]!.recoveryWeights[7]!, 2 / 17);
  assert.ok(repeated.windows[0]!.executionRhythmRaw > 0);
});

test('equivalent BPM/division writes have identical physical windows and burden', () => {
  const phrase = stream(33, [3, 1], ['1', '5', '2', '6']);
  const base = keyboardRhythmComplexity(parse(`(120){16}${phrase}`));
  const rewritten = keyboardRhythmComplexity(parse(`(240){8}${phrase}`));
  assert.equal(base.version, KEYBOARD_RHYTHM_VERSION);
  assert.equal(base.windows.length, 2);
  assert.equal(rewritten.windows.length, base.windows.length);
  close(rewritten.raw, base.raw);
  for (let i = 0; i < base.windows.length; i++) {
    const a = base.windows[i]!, b = rewritten.windows[i]!;
    close(b.startMs, a.startMs); close(b.endMs, a.endMs); close(b.raw, a.raw);
    close(b.startBeat, a.startBeat * 2); close(b.endBeat, a.endBeat * 2);
    b.rhythm.normalizedIOIs.forEach((value, j) => close(value, a.rhythm.normalizedIOIs[j]!));
  }
});

test('tempo scaling retains beat structure and changes actual execution burden', () => {
  const phrase = stream(17, [3, 1], ['1', '5']);
  const base = keyboardRhythmComplexity(parse(`(120){16}${phrase}`));
  const faster = keyboardRhythmComplexity(parse(`(240){16}${phrase}`));
  close(faster.windows[0]!.rhythm.raw, base.windows[0]!.rhythm.raw);
  close(faster.windows[0]!.onsetRate, base.windows[0]!.onsetRate * 2);
  close(faster.raw, base.raw * 2);
});

test('full BPM table converts crossing intervals while rhythmic relations stay in beats', () => {
  const steady = keyboardRhythmComplexity(parse('(120){16}1,,,5,1,,,5,1,,,5,1,,,5,1'));
  const changing = keyboardRhythmComplexity(parse('(120){16}1,,,(240)5,1,,,5,1,,,5,1,,,5,1'));
  assert.deepEqual(changing.windows[0]!.rhythm.iois, steady.windows[0]!.rhythm.iois);
  close(changing.windows[0]!.rhythm.raw, steady.windows[0]!.rhythm.raw);
  assert.ok(changing.windows[0]!.onsetRate > steady.windows[0]!.onsetRate);
  assert.equal(changing.windows[0]!.onsets[1]!.ms, 375);
});

test('pseudo EACH is a display offset and has the same rhythm as regular EACH', () => {
  const normal = keyboardRhythmComplexity(parse('(120){16}1/5,,,2/6,1/5,,,2/6,1/5'));
  const pseudo = keyboardRhythmComplexity(parse('(120){16}1`5,,,2`6,1`5,,,2`6,1`5'));
  close(pseudo.raw, normal.raw);
  assert.equal(pseudo.onsetCount, normal.onsetCount);
  assert.deepEqual(pseudo.windows[0]!.onsets.map(o => [o.ms, o.beat, o.positions]), normal.windows[0]!.onsets.map(o => [o.ms, o.beat, o.positions]));
  assert.ok(pseudo.windows[0]!.onsets.every(o => o.noteIds.length === 2));
});

test('Touch follows the same input rhythm path; star TAP is not a Slide, headless paths not a TAP', () => {
  const chart = parse('(120){8}1$,2-6[8:1],3!-7[8:1],B4,4m,5h[4:1],6b');
  const result = keyboardRhythmComplexity(chart);
  assert.equal(result.onsetCount, 4);
  assert.deepEqual(result.windows[0]!.onsets.flatMap(o => o.kinds), ['tap', 'touch', 'hold-start', 'break']);
  assert.deepEqual(result.windows[0]!.onsets.flatMap(o => o.positions), [1, 'B4', 5, 6]);
});

test('each adjacent IOI belongs to exactly one bounded source window', () => {
  const result = keyboardRhythmComplexity(parse(`(120){16}${stream(40, [3, 1], ['1', '5'])}`));
  assert.deepEqual(result.windows.map(window => window.onsets.length), [17, 17, 8]);
  assert.equal(result.windows.reduce((n, window) => n + window.rhythm.iois.length, 0), result.onsetCount - 1);
  assert.equal(result.windows[0]!.endMs, result.windows[1]!.startMs);
  assert.equal(result.windows[1]!.endMs, result.windows[2]!.startMs);
  for (const window of result.windows) {
    assert.deepEqual(window.noteIds, window.onsets.flatMap(onset => onset.noteIds));
    assert.equal(window.startBeat, window.onsets[0]!.beat);
    assert.equal(window.endBeat, window.onsets.at(-1)!.beat);
    assert.ok(window.onsets.every(onset => onset.source.length === onset.noteIds.length));
  }
});

test('metadata and original EACH ordering cannot alter the raw computation', () => {
  const body = '(120){16}1/5,,,2/6,1/5,,,2/6,1/5';
  const chart = parse(body), baseline = keyboardRhythmComplexity(chart);
  for (const field of ['title', 'artist', 'designer', 'difficulty', 'level', 'designers', 'availableDifficulties'])
    Object.defineProperty(chart, field, { get() { throw new Error(`Forbidden metadata ${field}`); } });
  close(keyboardRhythmComplexity(chart).raw, baseline.raw);
  close(keyboardRhythmComplexity(parse(body.replaceAll('1/5', '5/1').replaceAll('2/6', '6/2'))).raw, baseline.raw);
});

test('seconds-compatible divisions use the same TimingTimeline coordinates as ratio divisions', () => {
  const phrase = stream(17, [3, 1], ['1', '5']);
  const ratio = keyboardRhythmComplexity(parse(`(120){16}${phrase}`));
  const seconds = keyboardRhythmComplexity(parse(`(120){#0.125}${phrase}`));
  close(seconds.raw, ratio.raw);
  assert.deepEqual(seconds.windows[0]!.rhythm.iois, ratio.windows[0]!.rhythm.iois);
});

const realFile = corpusFile('19. UNiVERSE PLUS/enchanted love');
test('real enchanted love MASTER preserves repeated uneven beat evidence and button displacement', { skip: !realFile }, () => {
  const chart = parseSimaiChart(fs.readFileSync(realFile!, 'utf8'), 5), result = keyboardRhythmComplexity(chart);
  assert.ok(result.raw > 0 && result.windows.length > 0);
  const repeated = result.windows.filter(window => window.rhythm.repeatedMotif.period !== null &&
    window.rhythm.alternationBurden > 0 && window.movementMean > 0);
  assert.ok(repeated.length > 0);
  assert.ok(repeated.some(window => window.rhythm.iois.some(gap => Math.abs(gap - 1 / 6) < 1e-9)));
  assert.ok(repeated.some(window => window.rhythm.iois.some(gap => Math.abs(gap - 1 / 3) < 1e-9)));
  assert.ok(result.windows.every(window => Number.isFinite(window.raw) && window.endMs > window.startMs));
});
