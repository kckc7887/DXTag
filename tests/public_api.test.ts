import assert from 'node:assert/strict';
import test from 'node:test';
import {AXES, scoreChart, scoreMaidata, type ScoreError} from '../src/index';

const taps = '(120){8}1,2,3,4,5,6,7,8,E';
const maidata = '&title=测试\n&lv_5=14+\n&inote_5=' + taps;

test('public scores contain exactly five finite axes in 0.0–10.0', () => {
  const chart = scoreChart(maidata, 5), scores = chart.scores;
  assert.deepEqual(Object.keys(chart), ['title', 'difficulty', 'scores']);
  assert.equal(chart.title, '测试');
  assert.equal(chart.difficulty, 'MASTER');
  assert.deepEqual(Object.keys(scores), [...AXES]);
  for (const value of Object.values(scores)) {
    assert.ok(Number.isFinite(value) && value >= 0 && value <= 10);
    assert.ok(Math.abs(value * 10 - Math.round(value * 10)) < 1e-10);
  }
  assert.equal(scores.星星, 0);
});

test('title, level, author and selected difficulty do not change the same chart score', () => {
  const original = scoreChart(maidata, 5).scores;
  const changed = '&title=另一首\n&artist=任意\n&des_3=测试\n&lv_3=2\n&inote_3=' + taps;
  assert.deepEqual(scoreChart(changed, 3).scores, original);
});

test('default selects only the present ordinary inote_2 through inote_6', () => {
  const text = [1, 2, 4, 5, 6, 7].map(slot => '&inote_' + slot + '=' + taps).join('\n');
  const result = scoreMaidata(text);
  assert.deepEqual(result.map(chart => chart.difficulty), ['BASIC', 'EXPERT', 'MASTER', 'Re:MASTER']);
  assert.ok(result.every(chart=>chart.title===''&&Object.keys(chart).join(',')==='title,difficulty,scores'));
  assert.deepEqual(scoreMaidata(text, 6).map(chart => chart.difficulty), ['Re:MASTER']);
});

test('a broken difficulty is reported without discarding valid other charts', () => {
  const errors:ScoreError[]=[];
  const text='&inote_4=(120){0}1,E\n&inote_5=' + taps;
  const result = scoreMaidata(text, undefined, error=>errors.push(error));
  assert.deepEqual(result.map(chart => chart.difficulty), ['MASTER']);
  assert.equal(errors.length, 1);
  assert.equal(errors[0]!.difficulty, 'EXPERT');
  assert.match(errors[0]!.message, /Invalid/);
  assert.throws(() => scoreMaidata(text), /Invalid/);
  assert.throws(() => scoreMaidata('&inote_1=' + taps), /没有普通谱/);
  assert.throws(() => scoreMaidata(maidata, 6), /not found/);
});

test('star TAP is zero Slide load while a genuine Slide contributes complexity', () => {
  const starTap = scoreChart('&inote_5=(120){4}1$,2$,3$,4$,E', 5);
  const slide = scoreChart('&inote_5=(120){4}1-5[4:2],2,3,4,E', 5);
  assert.equal(starTap.scores.星星, 0);
  assert.ok(slide.scores.星星 > 0);
});

test('unresolved chained geometry fails explicitly instead of making up five scores', () => {
  const errors:ScoreError[]=[];
  const result = scoreMaidata('&inote_5=(120){4}1V72[4:1]V64[4:1],E', undefined, error=>errors.push(error));
  assert.equal(result.length, 0);
  assert.equal(errors.length, 1);
  assert.match(errors[0]!.message, /Slide 路径不完整/);
});
