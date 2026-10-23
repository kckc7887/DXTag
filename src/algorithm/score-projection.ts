import scale from '../scale.json';

export const COMPLEXITY_RADAR_POLICY = Object.freeze({
  exponent: scale.exponent,
  weights: { starTechnique: .65, keyboardRhythm: .65, starBurst: .65, holdLockTechnique: .65, touchKeyboard: .65, holdLockKeyboard: .35 },
});
export const RADAR_AXES = ['键盘', '星星', '技巧', '体力', '爆发'] as const;
export type RadarScores = Record<typeof RADAR_AXES[number], number>;
export type BaselineScores = Omit<RadarScores, '星星'>;
export type RadarSupports = { star_technique: number; keyboard_rhythm: number; star_burst: number; touch_input?: number; hold_lock?: number };
export function normalizeBurden(raw: number, anchor: number): number {
  if (!Number.isFinite(raw) || raw < 0 || !Number.isFinite(anchor) || anchor <= 0)
    throw Error('Normalization requires a finite nonnegative raw value and a finite positive anchor');
  return 100 * Math.pow(Math.max(0, Math.min(1, raw / anchor)), COMPLEXITY_RADAR_POLICY.exponent);
}
export function baselineRadar(features: Record<string, number>, anchors: Record<string, number>): BaselineScores {
  const key = (name: string) => Number(features[name] ?? 0);
  const raw = {
    键盘: key('axis_keyboard_burst') + key('axis_keyboard_stamina') + key('axis_keyboard_technique'),
    技巧: key('axis_keyboard_technique') + key('axis_star_technique'),
    体力: key('axis_keyboard_stamina') + key('axis_star_stamina'),
    爆发: key('axis_keyboard_burst') + key('axis_star_burst'),
  };
  return Object.fromEntries(Object.entries(raw).map(([axis, value]) => [axis, normalizeBurden(value, anchors[axis]!)])) as BaselineScores;
}
export function complexityRadar(baseline: BaselineScores, starScore: number, supports: RadarSupports): RadarScores {
  if (Object.values(baseline).some(v => !Number.isFinite(v) || v < 0 || v > 100)
      || Object.values(supports).some(v => !Number.isFinite(v) || v < 0 || v > 100)
      || !Number.isFinite(starScore) || starScore < 0 || starScore > 100)
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
  return { ...baseline, 键盘: keyboard, 星星: starScore, 技巧: technique, 爆发: burst };
}
