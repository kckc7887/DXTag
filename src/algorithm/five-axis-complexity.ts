/** Display projection for the independent complexity experiment. No constants,
 * difficulty names or tags are inputs. Button baseline and stamina stay intact;
 * Touch input and held-hand support supplement keyboard and technique. */
export const COMPLEXITY_RADAR_VERSION = 'five-axis-complexity-v2';
export const COMPLEXITY_RADAR_POLICY = Object.freeze({
  version: COMPLEXITY_RADAR_VERSION,
  weights: { starTechnique: .65, keyboardRhythm: .65, starBurst: .65, holdLockTechnique: .65, touchKeyboard: .65, holdLockKeyboard: .35 },
  combination: '100 * (1 - product(1 - normalized support)); old technique/burst are the baseline',
  scale: 'independent all-library deduplicated p99.5 / positive p99 anchors',
  activitySupportFloor: 20,
  activity: 'observed complexity/rhythm support, distinct from archived rule labels',
});
export const RADAR_AXES = ['键盘', '星星', '技巧', '体力', '爆发'] as const;
export type RadarScores = Record<typeof RADAR_AXES[number], number>;
export type RadarSupports = { star_technique: number; keyboard_rhythm: number; star_burst: number; touch_input?: number; hold_lock?: number };
export type RadarProjection = {
  baseline: RadarScores; starScore: number; supports: Required<RadarSupports>;
  fused: RadarScores; excess: RadarScores; chartRelativeSource: RadarScores; chartRelativeScores: RadarScores;
};
export const CHART_RELATIVE_VERSION = 'chart-relative-library-v2';
export const CHART_RELATIVE_POLICY = Object.freeze({
  version: CHART_RELATIVE_VERSION,
  source: 'all-library fused axes plus weighted pre-cap normalized excess above 100; library anchors, weights and scores are preserved',
  excess: 'baseline/star: max(0, normalized source - 100); supports: the same excess multiplied by the original fusion weight',
  projection: 'round(axis / maximum * 100) / 10; all-zero axes remain zero',
});
const bounded = (v: number) => Math.max(0, Math.min(100, v));
const rounded = (v: number) => Math.round(bounded(v) * 10) / 10;
/** Compare library-derived axes with their pre-cap excess restored. */
export function chartRelativeRadar(source: RadarScores): RadarScores {
  const values = RADAR_AXES.map(axis => source[axis]);
  if (values.some(value => !Number.isFinite(value) || value < 0))
    throw Error('Invalid chart-relative source score');
  const maximum = Math.max(...values);
  return Object.fromEntries(RADAR_AXES.map(axis =>
    [axis, maximum > 0 ? Math.round(source[axis] / maximum * 100) / 10 : 0])) as RadarScores;
}
/** Match the existing Python radar's round() at exact ties. */
export function roundHalfEven(value: number): number {
  const lower = Math.floor(value), fraction = value - lower;
  return fraction === .5 ? lower + (lower % 2) : Math.round(value);
}
/** Fixed-anchor baseline values before clipping or rounding. */
export function normalizeLegacyRadar(features: Record<string, number>, anchors: Record<string, number>): RadarScores {
  const key = (name: string) => Number(features[name] ?? 0);
  const raw = {
    键盘: key('axis_keyboard_burst') + key('axis_keyboard_stamina') + key('axis_keyboard_technique'),
    星星: key('axis_star_burst') + key('axis_star_stamina') + key('axis_star_technique') + key('axis_star_presence'),
    技巧: key('axis_keyboard_technique') + key('axis_star_technique'),
    体力: key('axis_keyboard_stamina') + key('axis_star_stamina'),
    爆发: key('axis_keyboard_burst') + key('axis_star_burst'),
  };
  for (const axis of RADAR_AXES) {
    if (!(anchors[axis]! > 0) || !Number.isFinite(anchors[axis]) || !Number.isFinite(raw[axis]) || raw[axis] < 0)
      throw Error(`Invalid legacy radar source: ${axis}`);
  }
  return Object.fromEntries(RADAR_AXES.map(axis => [axis, raw[axis] / anchors[axis]! * 100])) as RadarScores;
}
export function legacyRadar(features: Record<string, number>, anchors: Record<string, number>): RadarScores {
  const normalized = normalizeLegacyRadar(features, anchors);
  return Object.fromEntries(RADAR_AXES.map(axis => [axis, roundHalfEven(bounded(normalized[axis]))])) as RadarScores;
}
export function complexityRadar(baseline: RadarScores, starScore: number | null, supports: RadarSupports): RadarScores {
  if (Object.values(baseline).some(v => !Number.isFinite(v) || v < 0 || v > 100)
      || Object.values(supports).some(v => !Number.isFinite(v) || v < 0 || v > 100)
      || (starScore !== null && (!Number.isFinite(starScore) || starScore < 0 || starScore > 100)))
    throw Error('Invalid projection score');
  const weights = COMPLEXITY_RADAR_POLICY.weights;
  const technique = 100 - (100 - baseline.技巧)
    * (1 - weights.starTechnique * supports.star_technique / 100)
    * (1 - weights.keyboardRhythm * supports.keyboard_rhythm / 100)
    * (1 - weights.holdLockTechnique * (supports.hold_lock ?? 0) / 100);
  const keyboard = 100 - (100 - baseline.键盘)
    * (1 - weights.touchKeyboard * (supports.touch_input ?? 0) / 100)
    * (1 - weights.holdLockKeyboard * (supports.hold_lock ?? 0) / 100);
  const burst = 100 - (100 - baseline.爆发) * (1 - weights.starBurst * supports.star_burst / 100);
  return { ...baseline, 键盘: rounded(keyboard), 星星: starScore ?? baseline.星星, 技巧: rounded(technique), 爆发: rounded(burst) };
}

/** Keep the library projection intact and retain each input's clipped excess
 * for the chart-relative view. Never feed values above 100 into noisy-OR:
 * negative factors there would make greater workload reduce a score. */
export function projectLibraryRadar(baselineRaw: RadarScores, starRaw: number, supportRaw: RadarSupports): RadarProjection {
  if ([...RADAR_AXES.map(axis => baselineRaw[axis]), starRaw,
      supportRaw.star_technique, supportRaw.keyboard_rhythm, supportRaw.star_burst,
      supportRaw.touch_input ?? 0, supportRaw.hold_lock ?? 0].some(value => !Number.isFinite(value) || value < 0))
    throw Error('Invalid pre-cap radar source');
  const baseline = Object.fromEntries(RADAR_AXES.map(axis =>
    [axis, roundHalfEven(bounded(baselineRaw[axis]))])) as RadarScores;
  const supports: Required<RadarSupports> = {
    star_technique: rounded(supportRaw.star_technique), keyboard_rhythm: rounded(supportRaw.keyboard_rhythm),
    star_burst: rounded(supportRaw.star_burst), touch_input: rounded(supportRaw.touch_input ?? 0),
    hold_lock: rounded(supportRaw.hold_lock ?? 0),
  };
  const starScore = rounded(starRaw), fused = complexityRadar(baseline, starScore, supports);
  const over = (value: number) => Math.max(0, value - 100), weights = COMPLEXITY_RADAR_POLICY.weights;
  const excess: RadarScores = {
    键盘: over(baselineRaw.键盘) + weights.touchKeyboard * over(supportRaw.touch_input ?? 0)
      + weights.holdLockKeyboard * over(supportRaw.hold_lock ?? 0),
    星星: over(starRaw),
    技巧: over(baselineRaw.技巧) + weights.starTechnique * over(supportRaw.star_technique)
      + weights.keyboardRhythm * over(supportRaw.keyboard_rhythm) + weights.holdLockTechnique * over(supportRaw.hold_lock ?? 0),
    体力: over(baselineRaw.体力),
    爆发: over(baselineRaw.爆发) + weights.starBurst * over(supportRaw.star_burst),
  };
  const chartRelativeSource = Object.fromEntries(RADAR_AXES.map(axis => [axis, fused[axis] + excess[axis]])) as RadarScores;
  return {baseline, starScore, supports, fused, excess, chartRelativeSource, chartRelativeScores: chartRelativeRadar(chartRelativeSource)};
}
