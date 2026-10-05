/** Chart-internal workload composition. No population scale, level or fused
 * all-library score is an input. Costs are heuristic action units per second. */
import type {Chart, Note} from '../simai/types';
import {TimingTimeline} from '../simai/core/timing/TimingTimeline';
import {RADAR_AXES, type RadarScores} from './five-axis-complexity';
import {STAR_COMPLEXITY_POLICY, type StarComplexityResult} from './star-complexity';
import {chordMovement, inputOnsets, keyboardRhythmComplexity, type KeyboardRhythmOnset, type KeyboardRhythmResult} from './rhythm-complexity';
import {inputComplexity, type InputComplexityResult} from './input-complexity';

export const CHART_RELATIVE_VERSION = 'chart-relative-burden-v1';
export const CHART_RELATIVE_POLICY = Object.freeze({
  version: CHART_RELATIVE_VERSION, blockBeats: 4, sustainedBeats: 32,
  meanWeight: .75, peakQuantile: .9,
  units: 'heuristic action workload / physical second',
  aggregation: '75% duration-weighted mean + 25% duration-weighted P90; peak axis maps to 10 only after independent workload computation',
});

const COMPONENT_LABELS = {
  inputs: '实际输入', starMotion: '滑动运动', starRhythm: '滑动节奏',
  starCoordination: '滑动并发协调', starContext: '滑动接续上下文',
  movement: '输入位置移动', rhythm: '输入节奏变化', starTechnique: '滑动技巧',
  holdLock: 'HOLD 占手协调', holdOccupancy: 'HOLD 持续占用',
  sustained: '周围持续水平支持的负担', excess: '超出周围持续水平的负担',
} as const;
type Component = keyof typeof COMPONENT_LABELS;
type Axis = typeof RADAR_AXES[number];
export type ChartRelativeBlock = {
  startMs: number; endMs: number; startBeat: number; endBeat: number;
  rates: RadarScores; components: Record<Component, number>;
  demand: number; sustainedLevel: number;
  noteIds: number[]; slideIds: number[]; holdIds: number[];
};
export type ChartRelativeAxis = {
  axis: Axis; score: number; raw: number; mean: number; p90: number; formula: string;
  /** Source rates are time means, not additive shares of the P90 statistic. */
  sources: {label: string; meanRate: number; totalCost: number}[];
  windows: ChartRelativeBlock[];
};
export type ChartRelativeResult = {
  version: typeof CHART_RELATIVE_VERSION; scores: RadarScores; rawScores: RadarScores;
  startMs: number; endMs: number; seconds: number; nativeInputIntervalMs: number;
  axes: ChartRelativeAxis[]; profile: ChartRelativeBlock[];
};
export type ChartRelativeObservations = {
  star: StarComplexityResult; rhythm: KeyboardRhythmResult; input: InputComplexityResult;
};

const zeroScores = (): RadarScores => ({键盘: 0, 星星: 0, 技巧: 0, 体力: 0, 爆发: 0});
const zeroComponents = () => Object.fromEntries(Object.keys(COMPONENT_LABELS).map(key => [key, 0])) as Record<Component, number>;
const same = (a: number, b: number) => Math.abs(a - b) <= Number.EPSILON * 32 * Math.max(Math.abs(a), Math.abs(b), Number.MIN_VALUE);
const overlap = (s: number, e: number, from: number, to: number) => Math.max(0, Math.min(e, to) - Math.max(s, from));
const sensor = (position: Note['position']) => position === 'C1' || position === 'C2' ? 'C' : String(position);
const median = (values: number[]) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

/** Display-only final mapping of independently computed, unbounded workloads. */
export function chartRelativeRadar(raw: RadarScores): RadarScores {
  const values = RADAR_AXES.map(axis => raw[axis]);
  if (values.some(value => !Number.isFinite(value) || value < 0)) throw Error('Invalid chart-relative workload');
  const maximum = Math.max(...values);
  return Object.fromEntries(RADAR_AXES.map(axis =>
    [axis, maximum > 0 ? Math.round(raw[axis] / maximum * 100) / 10 : 0])) as RadarScores;
}

function physicalInputs(chart: Chart): KeyboardRhythmOnset[] {
  const notes = new Map(chart.notes.map(note => [note.id, note]));
  return inputOnsets(chart, true, true).map(onset => {
    const chosen = new Map<string, number>();
    onset.positions.forEach((position, index) => {
      const key = sensor(position), previous = chosen.get(key);
      const candidate = notes.get(onset.noteIds[index]!)!, old = previous === undefined ? undefined : notes.get(onset.noteIds[previous]!);
      // Keep the longer HOLD when heads coincide; a non-Slide attack retains
      // its rhythm input when also represented by a Slide head.
      if (previous === undefined || candidate.endTimeMs > old!.endTimeMs && (candidate.type === 'hold-start' || candidate.type === 'touch-hold-start') ||
          old!.type === 'slide' && candidate.type !== 'slide') chosen.set(key, index);
    });
    const indexes = [...chosen.values()];
    return {...onset, noteIds: indexes.map(i => onset.noteIds[i]!), positions: indexes.map(i => onset.positions[i]!),
      kinds: indexes.map(i => onset.kinds[i]!), source: indexes.map(i => onset.source[i]!)};
  });
}

/** Independent chart-relative calculation shared by the API and Web analysis. */
export function chartRelativeBurden(chart: Chart, observations: ChartRelativeObservations): ChartRelativeResult {
  const {star} = observations;
  if (!star.coverage.complete || star.raw === null) throw Error('Incomplete Slide workload');
  const notes = [...new Map(chart.notes.filter(note => !note.isMine).map(note => [note.id, note])).values()];
  if (!notes.length) throw Error('Empty chart');
  const timeline = TimingTimeline.fromChart(chart), onsets = physicalInputs(chart);
  const audio = (note: Note) => note.timingMs - timeline.msFromBeat(4) + chart.firstMs;
  const inputIds = new Set(onsets.flatMap(onset => onset.noteIds));
  const duplicateHeads = inputOnsets(chart, true, true).some(onset => onset.noteIds.some(id => !inputIds.has(id)));
  const canonicalChart = duplicateHeads ? {...chart, notes: chart.notes.filter(note => inputIds.has(note.id) || note.type === 'slide' && note.isHeadless)} : chart;
  const rhythm = duplicateHeads ? keyboardRhythmComplexity(canonicalChart) : observations.rhythm;
  const input = duplicateHeads ? inputComplexity(canonicalChart) : observations.input;
  const held = notes.filter(note => (note.type === 'hold-start' || note.type === 'touch-hold-start') && note.endTimeMs > note.timingMs);
  const starts = [...onsets.map(onset => onset.ms), ...star.actions.map(action => action.hasHead ? action.headMs : action.startMs)];
  if (!starts.length) throw Error('Empty chart actions');
  const startMs = Math.min(...starts), startBeat = timeline.scoreBeatFromAudioMs(startMs, chart.firstMs);
  const gaps = onsets.slice(1).map((onset, i) => onset.ms - onsets[i]!.ms).filter(gap => gap > 0);
  const nativeInputIntervalMs = median(gaps) ?? timeline.audioMsFromScoreBeat(startBeat + 1, chart.firstMs) - startMs;
  const endMs = Math.max(...held.map(note => audio(note) + note.endTimeMs - note.timingMs), ...star.actions.map(action => action.endMs),
    ...(onsets.length ? [onsets.at(-1)!.ms + nativeInputIntervalMs] : []));
  if (!(nativeInputIntervalMs > 0) || !(endMs > startMs) || ![startMs, endMs, nativeInputIntervalMs].every(Number.isFinite))
    throw Error('Invalid chart-relative timing');
  const seconds = (endMs - startMs) / 1000, profile: ChartRelativeBlock[] = [];
  for (let index = 0; ; index++) {
    const fromBeat = startBeat + index * CHART_RELATIVE_POLICY.blockBeats;
    const from = index === 0 ? startMs : timeline.audioMsFromScoreBeat(fromBeat, chart.firstMs);
    if (from >= endMs || same(from, endMs)) break;
    const to = Math.min(endMs, timeline.audioMsFromScoreBeat(fromBeat + CHART_RELATIVE_POLICY.blockBeats, chart.firstMs));
    if (!(to > from)) throw Error('Invalid chart-relative block');
    profile.push({startMs: from, endMs: to, startBeat: fromBeat, endBeat: timeline.scoreBeatFromAudioMs(to, chart.firstMs),
      rates: zeroScores(), components: zeroComponents(), demand: 0, sustainedLevel: 0, noteIds: [], slideIds: [], holdIds: []});
  }
  const blockAt = (ms: number) => {
    let lo = 0, hi = profile.length;
    while (lo < hi) { const mid = (lo + hi) >>> 1; const start = profile[mid]!.startMs;
      if (start <= ms || same(start, ms)) lo = mid + 1; else hi = mid; }
    return Math.max(0, lo - 1);
  };
  const pointCost = (key: Component, cost: number, onset: KeyboardRhythmOnset) => {
    const block = profile[blockAt(onset.ms)]!;
    block.components[key] += cost * 1000 / (block.endMs - block.startMs);
    block.noteIds.push(...onset.noteIds);
  };
  const intervalCost = (key: Component, cost: number, from: number, to: number, ids?: {slideIds?: number[]; holdIds?: number[]; noteIds?: number[]}) => {
    if (!Number.isFinite(cost) || cost < 0 || !Number.isFinite(from) || !Number.isFinite(to) || !(to > from))
      throw Error('Invalid chart-relative action cost');
    if (cost === 0) return;
    for (let i = blockAt(from); i < profile.length && profile[i]!.startMs < to; i++) {
      const block = profile[i]!, length = overlap(block.startMs, block.endMs, from, to);
      if (!length) continue;
      block.components[key] += cost * length / (to - from) * 1000 / (block.endMs - block.startMs);
      if (ids?.slideIds) block.slideIds.push(...ids.slideIds);
      if (ids?.holdIds) block.holdIds.push(...ids.holdIds);
      if (ids?.noteIds) block.noteIds.push(...ids.noteIds);
    }
  };

  onsets.forEach((onset, index) => {
    pointCost('inputs', onset.noteIds.length, onset);
    if (index) { const previous = onsets[index - 1]!;
      pointCost('movement', chordMovement(previous, onset) / 4 * (previous.noteIds.length + onset.noteIds.length) / 2, onset); }
  });
  const starKeys = {motion: 'starMotion', rhythm: 'starRhythm', coordination: 'starCoordination', context: 'starContext'} as const;
  for (const action of star.actions) for (const key of Object.keys(starKeys) as (keyof typeof starKeys)[]) {
    const from = key === 'motion' || !action.hasHead ? action.startMs : action.headMs;
    intervalCost(starKeys[key], action.components[key] * STAR_COMPLEXITY_POLICY.weights[key], from, action.endMs, {slideIds: action.slideIds});
    intervalCost('starTechnique', action.components[key] * STAR_COMPLEXITY_POLICY.techniqueWeights[key], from, action.endMs, {slideIds: action.slideIds});
  }
  for (const window of rhythm.windows) {
    // A rhythm context can span a phrase-ending rest. Preserve its full
    // rate×duration cost, but allocate execution only to attack intervals,
    // capped by the chart's native IOI, so empty recovery blocks stay empty.
    const spans = window.onsets.slice(0, -1).map((onset, index) => ({from: onset.ms,
      to: Math.min(window.onsets[index + 1]!.ms, onset.ms + nativeInputIntervalMs), noteIds: onset.noteIds}));
    const activeMs = spans.reduce((sum, span) => sum + span.to - span.from, 0);
    for (const span of spans) intervalCost('rhythm', window.raw * (window.endMs - window.startMs) / 1000 * (span.to - span.from) / activeMs,
      span.from, span.to, {noteIds: span.noteIds});
  }
  for (const window of input.allHoldWindows)
    intervalCost('holdLock', window.raw, window.startMs, window.endMs, {holdIds: [window.holdId], noteIds: window.noteIds});

  const bySensor = new Map<string, {from: number; to: number; ids: number[]}[]>();
  for (const note of held) {
    const key = sensor(note.position), intervals = bySensor.get(key) ?? [];
    intervals.push({from: audio(note), to: audio(note) + note.endTimeMs - note.timingMs, ids: [note.id]}); bySensor.set(key, intervals);
  }
  for (const intervals of bySensor.values()) {
    intervals.sort((a, b) => a.from - b.from); const merged: typeof intervals = [];
    for (const interval of intervals) { const previous = merged.at(-1);
      if (previous && interval.from <= previous.to) { previous.to = Math.max(previous.to, interval.to); previous.ids.push(...interval.ids); }
      else merged.push({...interval, ids: [...interval.ids]}); }
    for (const interval of merged)
      intervalCost('holdOccupancy', (interval.to - interval.from) / nativeInputIntervalMs, interval.from, interval.to, {holdIds: interval.ids});
  }
  for (const block of profile) {
    const c = block.components;
    block.rates.键盘 = c.inputs;
    block.rates.星星 = c.starMotion + c.starRhythm + c.starCoordination + c.starContext;
    block.rates.技巧 = c.movement + c.rhythm + c.starTechnique + c.holdLock;
    block.demand = Math.max(block.rates.键盘, block.rates.星星, block.rates.技巧, c.holdOccupancy);
  }
  // Piecewise-constant time integration, including interior recovery blocks.
  const prefix = [0];
  for (const block of profile) prefix.push(prefix.at(-1)! + block.demand * (block.endMs - block.startMs) / 1000);
  const integral = (ms: number) => {
    if (ms <= startMs) return 0;
    if (ms >= endMs) return prefix.at(-1)!;
    const index = blockAt(ms), block = profile[index]!;
    return prefix[index]! + block.demand * (ms - block.startMs) / 1000;
  };
  for (const block of profile) {
    const center = (block.startBeat + block.endBeat) / 2, radius = CHART_RELATIVE_POLICY.sustainedBeats / 2;
    const from = Math.max(startMs, timeline.audioMsFromScoreBeat(center - radius, chart.firstMs));
    const to = Math.min(endMs, timeline.audioMsFromScoreBeat(center + radius, chart.firstMs));
    const level = Math.max(0, (integral(to) - integral(from)) * 1000 / (to - from));
    block.sustainedLevel = same(level, block.demand) ? block.demand : level;
    block.rates.体力 = block.components.sustained = Math.min(block.demand, block.sustainedLevel);
    block.rates.爆发 = block.components.excess = Math.max(0, block.demand - block.sustainedLevel);
    for (const key of ['noteIds', 'slideIds', 'holdIds'] as const) block[key] = [...new Set(block[key])].sort((a, b) => a - b);
  }
  const meanRate = (value: (block: ChartRelativeBlock) => number) =>
    profile.reduce((sum, block) => sum + value(block) * (block.endMs - block.startMs) / 1000, 0) / seconds;
  const statistics = RADAR_AXES.map(axis => {
    const mean = meanRate(block => block.rates[axis]); let covered = 0, p90 = 0;
    for (const block of [...profile].sort((a, b) => a.rates[axis] - b.rates[axis])) {
      covered += (block.endMs - block.startMs) / 1000;
      if (covered >= seconds * CHART_RELATIVE_POLICY.peakQuantile) { p90 = block.rates[axis]; break; }
    }
    return {axis, mean, p90, raw: CHART_RELATIVE_POLICY.meanWeight * mean + (1 - CHART_RELATIVE_POLICY.meanWeight) * p90};
  });
  const rawScores = Object.fromEntries(statistics.map(stat => [stat.axis, stat.raw])) as RadarScores;
  const scores = chartRelativeRadar(rawScores);
  const sources: Record<Axis, Component[]> = {键盘: ['inputs'], 星星: ['starMotion', 'starRhythm', 'starCoordination', 'starContext'],
    技巧: ['movement', 'rhythm', 'starTechnique', 'holdLock'], 体力: ['sustained'], 爆发: ['excess']};
  const formulas: Record<Axis, string> = {键盘: '实际输入数 / 块时长', 星星: '(运动 + 0.7×节奏 + 1.2×并发协调 + 1.5×上下文) / 块时长',
    技巧: '输入位移 + 节奏变化 + 滑动技巧 + HOLD 占手协调', 体力: 'min(当前负担 L, 周围 32 拍持续水平 C)', 爆发: 'max(0, 当前负担 L − 周围 32 拍持续水平 C)'};
  const axes = statistics.map(stat => ({...stat, score: scores[stat.axis], formula: formulas[stat.axis],
    sources: sources[stat.axis].map(key => ({label: COMPONENT_LABELS[key], meanRate: meanRate(block => block.components[key]),
      totalCost: meanRate(block => block.components[key]) * seconds})),
    windows: profile.filter(block => block.rates[stat.axis] > 0).sort((a, b) => b.rates[stat.axis] - a.rates[stat.axis]).slice(0, 5),
  }));
  return {version: CHART_RELATIVE_VERSION, scores, rawScores, startMs, endMs, seconds, nativeInputIntervalMs, axes, profile};
}
