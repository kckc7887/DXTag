import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import {parseSimaiChart} from '../src/simai/core/parser/SimaiParser';
import {baseBurden} from '../src/algorithm/base-burden';
import {starComplexity, STAR_COMPLEXITY_POLICY} from '../src/algorithm/star-complexity';
import {keyboardRhythmComplexity} from '../src/algorithm/rhythm-complexity';
import {inputComplexity} from '../src/algorithm/input-complexity';
import {chartRelativeBurden, CHART_RELATIVE_VERSION} from '../src/algorithm/chart-relative-burden';
import {AXES, scoreChart, scoreMaidata} from '../src/index';
import {corpusFile} from './corpus';

const text = (body: string) => '&inote_5=' + body + ',E';
const analyze = (body: string) => {
  const chart = parseSimaiChart(text(body), 5), base = baseBurden(chart);
  return chartRelativeBurden(chart, {star: starComplexity(chart, base.slideEvents),
    rhythm: keyboardRhythmComplexity(chart), input: inputComplexity(chart)});
};
const stream = (count = 128, key = '1') => '(120){4}' + Array(count).fill(key).join(',');
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b)), `${a} != ${b}`);

test('steady keyboard is sustained work, with zero Slide, rhythm-technique and burst', () => {
  const result = analyze(stream());
  assert.equal(result.version, CHART_RELATIVE_VERSION);
  assert.deepEqual(result.scores, {键盘: 10, 星星: 0, 技巧: 0, 体力: 10, 爆发: 0});
  close(result.rawScores.键盘, 2); close(result.rawScores.体力, 2);
  assert.equal(result.rawScores.爆发, 0);
  close(result.seconds, 64);
});

test('the standalone chart-local dependency graph never imports a population scale', async () => {
  const bundle = await build({entryPoints: [fileURLToPath(new URL('../src/algorithm/chart-relative-burden.ts', import.meta.url))],
    bundle: true, write: false, metafile: true, platform: 'node', format: 'esm'});
  assert.ok(!Object.keys(bundle.metafile.inputs).some(path => /(?:^|\/)scale\.json$/.test(path)));
});

test('identical capped library vectors still distinguish different physical chart structures', () => {
  const repeated = '(600){64}' + Array(256).fill('1').join(',');
  const moving = '(600){64}' + Array.from({length: 256}, (_, index) => index % 2 ? '5' : '1').join(',');
  const a = scoreChart(text(repeated), 5), b = scoreChart(text(moving), 5);
  assert.deepEqual(a.scores, b.scores);
  assert.deepEqual(AXES.map(axis => a.scores[axis]), [10, 0, 10, 10, 10]);
  assert.equal(a.chartRelativeScores.技巧, 0);
  assert.ok(b.chartRelativeScores.技巧 > 9);
  assert.notDeepEqual(a.chartRelativeScores, b.chartRelativeScores);
});

test('spatial movement and uneven rhythm add technique at the same input count', () => {
  const steady = analyze(stream(128));
  const wide = analyze('(120){4}' + Array.from({length: 128}, (_, i) => i % 2 ? '5' : '1').join(','));
  close(wide.rawScores.键盘, steady.rawScores.键盘);
  assert.ok(wide.rawScores.技巧 > steady.rawScores.技巧);
  const uneven = analyze('(120){16}' + Array(32).fill('1,,,2').join(','));
  assert.ok(uneven.axes.find(axis => axis.axis === '技巧')!.sources.find(source => source.label === '输入节奏变化')!.meanRate > 0);
});

test('Slide-dominant charts retain full per-trajectory costs before sqrt aggregation', () => {
  const body = '(120){4}' + Array(64).fill('1-5[4:1]').join(','), result = analyze(body);
  assert.equal(result.scores.星星, 10);
  assert.ok(result.rawScores.星星 > result.rawScores.键盘);
  const chart = parseSimaiChart(text(body), 5), star = starComplexity(chart, baseBurden(chart).slideEvents);
  assert.equal(star.actions.length, 64);
  const total = star.actions.reduce((sum, action) => sum + Object.entries(STAR_COMPLEXITY_POLICY.weights)
    .reduce((cost, [key, weight]) => cost + action.components[key as keyof typeof action.components] * weight, 0), 0);
  close(total, star.raw! * Math.sqrt(star.actions.length));
  const distributed = result.profile.reduce((sum, block) => sum + block.rates.星星 * (block.endMs - block.startMs) / 1000, 0);
  close(distributed, total);
});

test('headless Slide contributes motion without an invented keyboard attack or leading wait', () => {
  const result = analyze('(120){4}1-5[4:1]?');
  assert.equal(result.rawScores.键盘, 0);
  assert.ok(result.rawScores.星星 > 0);
  close(result.startMs, 500); close(result.endMs, 1000);
});

test('coincident paths and source heads do not duplicate chart-local work', () => {
  const solo = analyze('(120){4}1-5[4:1]');
  const branches = analyze('(120){4}1-5[4:1]*-5[4:1]');
  const sources = analyze('(120){4}1-5[4:1]/1-5[4:1]');
  for (const axis of AXES) {close(branches.rawScores[axis], solo.rawScores[axis]); close(sources.rawScores[axis], solo.rawScores[axis]);}
  assert.deepEqual(analyze(stream(32, '1/1')).rawScores, analyze(stream(32)).rawScores);
});

test('Touch attacks, both HOLD kinds and overlapping sensor occupancy are observed', () => {
  const touch = analyze(stream(32, 'A1'));
  assert.equal(touch.rawScores.星星, 0); close(touch.rawScores.键盘, 2);
  const buttonBody = '(120){8}1h[4:8],5,2,6,3,7,4,8';
  const chart = parseSimaiChart(text(buttonBody), 5), input = inputComplexity(chart);
  assert.equal(input.raw, 0); assert.deepEqual(input.windows, []);
  assert.ok(input.allHoldWindows.length > 0);
  for (const body of [buttonBody, '(120){8}Ch[4:8],A1,A5,A1,A5,A1,A5,A1']) {
    const result = analyze(body);
    assert.ok(result.axes.find(axis => axis.axis === '技巧')!.sources.find(source => source.label === 'HOLD 占手协调')!.meanRate > 0);
    assert.ok(result.profile.some(block => block.components.holdOccupancy > 0));
  }
  const single = analyze('(120){4}Ch[4:16]'), duplicated = analyze('(120){4}Ch[4:16]/C1h[4:16]');
  for (const axis of AXES) close(single.rawScores[axis], duplicated.rawScores[axis]);
  const overlapping = analyze('(120){4}1h[4:8],1h[4:8]');
  close(overlapping.profile.reduce((sum, block) => sum + block.components.holdOccupancy * (block.endMs - block.startMs) / 1000, 0), 9);
});

test('a short dense spike increases burst without replacing whole-chart composition with its peak', () => {
  const body = stream(64) + ',{64}' + Array(32).fill('1/2/3/4').join(',') + ',{4}' + Array(64).fill('1').join(',');
  const result = analyze(body), burst = result.axes.find(axis => axis.axis === '爆发')!;
  assert.ok(burst.raw > 0); assert.equal(burst.p90, 0);
  assert.ok(burst.raw < Math.max(...result.profile.map(block => block.rates.爆发)) * .1);
  assert.ok(result.rawScores.体力 < result.rawScores.键盘);
});

test('interior recovery remains zero while leading and trailing blank time is excluded', () => {
  const original = analyze(stream(32));
  const padded = analyze('(120){4},,,,' + Array(32).fill('1').join(',') + ',,,,,,,,');
  assert.deepEqual(padded.rawScores, original.rawScores); close(padded.seconds, original.seconds);
  const rest = analyze(stream(16) + ',' + Array(32).fill('').join(',') + ',' + Array(16).fill('1').join(','));
  assert.ok(rest.profile.some(block => AXES.every(axis => block.rates[axis] === 0)));
  assert.ok(rest.rawScores.体力 < original.rawScores.体力);
  assert.ok(rest.rawScores.爆发 > 0);
});

test('single inputs, partial blocks and BPM changes retain finite duration-weighted evidence', () => {
  const single = analyze('(120){4}1'); close(single.seconds, .5);
  close(single.rawScores.键盘, 2); close(single.nativeInputIntervalMs, 500);
  const varying = analyze('(123){8}1,2,3,(246)4,5,6h[4:2],7,8');
  assert.ok(varying.profile.length > 1);
  close(varying.profile.reduce((sum, block) => sum + (block.endMs - block.startMs) / 1000, 0), varying.seconds);
  for (const block of varying.profile) assert.ok(Object.values(block.rates).every(value => Number.isFinite(value) && value >= 0));
});

test('Mine exclusion, source metadata and other difficulty slots preserve independent results', () => {
  assert.deepEqual(analyze(stream(32, '1/5m')).rawScores, analyze(stream(32)).rawScores);
  const body = stream(32), original = scoreChart(text(body), 5);
  const changed = '&title=other\n&lv_3=1\n&first=12\n&inote_3=' + body + ',E\n&inote_6=(600){64}1/2/3/4,E';
  assert.deepEqual(scoreChart(changed, 3).chartRelativeScores, original.chartRelativeScores);
  assert.deepEqual(scoreMaidata(changed, 3)[0]!.chartRelativeScores, scoreMaidata(changed)[0]!.chartRelativeScores);
});

const realFile = corpusFile('22. BUDDiES/系ぎて');
test('系ぎて all slots keep frozen library scores while saturated Re:MASTER gets independent ratios', {skip: !realFile}, () => {
  const source = fs.readFileSync(realFile!, 'utf8'), expected = [
    [3.4,1.3,2.6,2.9,3.5], [5.9,1.4,4.7,4.1,4.4], [6.7,7.2,7.9,5.1,7.3],
    [9.2,7.4,8.4,8.4,8.5], [10,8.7,9.2,10,9.7],
  ];
  const batch = scoreMaidata(source);
  assert.equal(batch.length, 5);
  batch.forEach((result, index) => {
    assert.deepEqual(AXES.map(axis => result.scores[axis]), expected[index]);
    assert.deepEqual(scoreMaidata(source, (index + 2) as 2 | 3 | 4 | 5 | 6)[0], result);
    assert.equal(Math.max(...Object.values(result.chartRelativeScores)), 10);
  });
  const remaster = batch[4]!;
  assert.notDeepEqual(remaster.chartRelativeScores, remaster.scores);
  const ratios = AXES.map(axis => remaster.chartRelativeScores[axis] / remaster.scores[axis]);
  assert.ok(Math.max(...ratios) - Math.min(...ratios) > .1);
});
