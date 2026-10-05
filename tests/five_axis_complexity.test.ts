import assert from 'node:assert/strict';
import test from 'node:test';
import { complexityRadar, roundHalfEven } from '../src/algorithm/five-axis-complexity';
import { chartRelativeRadar } from '../src/algorithm/chart-relative-burden';
const old = { 键盘: 34, 星星: 22, 技巧: 40, 体力: 19, 爆发: 30 };
const no = { star_technique: 0, keyboard_rhythm: 0, star_burst: 0 };
test('exported old radar agrees with Python tie-to-even rounding', () => {
  assert.equal(roundHalfEven(40.5), 40); assert.equal(roundHalfEven(41.5), 42);
  assert.equal(roundHalfEven(40.49999999), 40); assert.equal(roundHalfEven(40.50000001), 41);
});
test('independent workload display maps the peak, ties and zeros within one chart', () => {
  assert.deepEqual(chartRelativeRadar({ 键盘: 30, 星星: 20, 技巧: 30, 体力: 0, 爆发: 15 }),
    { 键盘: 10, 星星: 6.7, 技巧: 10, 体力: 0, 爆发: 5 });
  assert.deepEqual(chartRelativeRadar({ 键盘: 0, 星星: 0, 技巧: 0, 体力: 0, 爆发: 0 }),
    { 键盘: 0, 星星: 0, 技巧: 0, 体力: 0, 爆发: 0 });
});
test('chart-relative radar uses values before public-score rounding', () => {
  const internal = { 键盘: 0.4, 星星: 0.8, 技巧: 0, 体力: 0, 爆发: 0 };
  assert.equal(Math.round(internal.键盘) / 10, 0);
  assert.deepEqual(chartRelativeRadar(internal),
    { 键盘: 5, 星星: 10, 技巧: 0, 体力: 0, 爆发: 0 });
  assert.throws(() => chartRelativeRadar({ ...internal, 星星: NaN }), /Invalid chart-relative workload/);
  assert.throws(() => chartRelativeRadar({ ...internal, 星星: -1 }));
  assert.deepEqual(chartRelativeRadar({ 键盘: 400, 星星: 800, 技巧: 0, 体力: 0, 爆发: 0 }),
    { 键盘: 5, 星星: 10, 技巧: 0, 体力: 0, 爆发: 0 });
  assert.deepEqual(chartRelativeRadar({ 键盘: 1e-200, 星星: 2e-200, 技巧: 0, 体力: 0, 爆发: 0 }),
    { 键盘: 5, 星星: 10, 技巧: 0, 体力: 0, 爆发: 0 });
});
test('zero support preserves the existing five-axis baseline and unknown Slide falls back', () => {
  assert.deepEqual(complexityRadar(old, null, no), old);
});
test('star and keyboard rhythm independently lift technique without relabeling keyboard as Slide', () => {
  const keyboard = complexityRadar({ ...old, 星星: 0 }, 0, { ...no, keyboard_rhythm: 60 });
  const star = complexityRadar(old, 65, { ...no, star_technique: 60 });
  const mixed = complexityRadar(old, 65, { ...no, star_technique: 60, keyboard_rhythm: 60 });
  assert.equal(keyboard.星星, 0);
  assert.ok(keyboard.技巧 > old.技巧 && star.技巧 > old.技巧 && mixed.技巧 > star.技巧);
  for (const result of [keyboard, star, mixed]) {
    assert.equal(result.键盘, old.键盘); assert.equal(result.体力, old.体力);
    assert.equal(result.爆发, old.爆发);
  }
});
test('complexity rise only adds burst support, bounded and monotonic at every baseline', () => {
  for (const baseline of [0, 20, 90, 100]) {
    let previous = baseline;
    for (const support of [0, 1, 20, 60, 100]) {
      const result = complexityRadar({ ...old, 爆发: baseline }, 50, { ...no, star_burst: support });
      assert.ok(result.爆发 >= previous && result.爆发 <= 100);
      assert.equal(result.技巧, old.技巧); previous = result.爆发;
    }
  }
});
test('invalid observations cannot silently become zeros', () => {
  assert.throws(() => complexityRadar(old, NaN, no));
  assert.throws(() => complexityRadar(old, 50, { ...no, keyboard_rhythm: -1 }));
});
test('Touch inputs and continuous lock load raise keyboard and technique without inventing Slide or stamina', () => {
  const result = complexityRadar({ ...old, 星星: 0 }, 0, { ...no, touch_input: 70, hold_lock: 70 });
  assert.ok(result.键盘 > old.键盘 && result.技巧 > old.技巧);
  assert.equal(result.星星, 0); assert.equal(result.体力, old.体力); assert.equal(result.爆发, old.爆发);
});
