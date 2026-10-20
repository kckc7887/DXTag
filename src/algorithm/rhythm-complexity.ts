import type { Chart, Note } from '../simai/types';
import { TimingTimeline } from '../simai/core/timing/TimingTimeline';
import { buttonPoint, touchPoint } from '../simai/core/geometry/slidePath';

export const RHYTHM_COMPLEXITY_PARAMETERS = Object.freeze({
  maximumMotifPeriod: 4, motifPeriodPenalty: .25,
  keyboardWindowOnsets: 17, chartPeakQuantile: .9, chartMeanWeight: .5,
});
const sum = (values: readonly number[]) => values.reduce((total, value) => total + value, 0);
const mean = (values: readonly number[]) => sum(values) / Math.max(1, values.length);
const sameNumber = (a: number, b: number) => Math.abs(a - b) <=
  Number.EPSILON * 16 * Math.max(1, Math.abs(a), Math.abs(b));

export type RhythmComplexityEvidence = {
  raw: number; onsetBeats: number[]; iois: number[]; normalizedIOIs: number[];
  adjacentRatioLogs: number[]; ratioVariation: number; dispersion: number;
  repeatedMotif: { period: number | null; repetitions: number; error: number; adaptation: number };
  surprise: number; alternationBurden: number;
};

export function rhythmComplexity(onsetBeats: readonly number[]): RhythmComplexityEvidence {
  if (!onsetBeats.every(Number.isFinite)) throw new Error('Non-finite rhythm onset beat');
  const ordered = [...onsetBeats].sort((a, b) => a - b), unique: number[] = [];
  for (const beat of ordered) if (!unique.length || !sameNumber(beat, unique.at(-1)!)) unique.push(beat);
  const iois = unique.slice(1).map((beat, index) => beat - unique[index]!);
  if (iois.some(ioi => ioi <= 0 || !Number.isFinite(ioi))) throw new Error('Invalid rhythm IOI');
  const logIOIs = iois.map(ioi => Math.log2(ioi)), centre = mean(logIOIs);
  const logs = logIOIs.map(value => sameNumber(value, centre) ? 0 : value - centre);
  const normalizedIOIs = logs.map(value => 2 ** value);
  const adjacentRatioLogs = logs.slice(1).map((value, index) => Math.abs(value - logs[index]!));
  const ratioVariation = mean(adjacentRatioLogs), dispersion = Math.sqrt(mean(logs.map(value => value ** 2)));
  let period: number | null = null, error = 0, objective = Infinity;
  if (logs.length >= 4) for (let candidate = 1; candidate <= Math.min(
    RHYTHM_COMPLEXITY_PARAMETERS.maximumMotifPeriod, Math.floor(logs.length / 2)); candidate++) {
    const mismatch = mean(logs.slice(candidate).map((value, index) => Math.abs(value - logs[index]!)));
    const cost = mismatch + RHYTHM_COMPLEXITY_PARAMETERS.motifPeriodPenalty * (candidate - 1) / logs.length;
    if (cost < objective) { objective = cost; period = candidate; error = mismatch; }
  }
  const repetitions = period === null ? 0 : Math.floor(logs.length / period);
  const adaptation = period === null ? 0 : (logs.length - period) / logs.length / (1 + error);
  const surprise = ratioVariation * (1 - adaptation), alternationBurden = ratioVariation;
  const raw = dispersion + .5 * alternationBurden + .5 * surprise;
  const result: RhythmComplexityEvidence = { raw, onsetBeats: unique, iois, normalizedIOIs,
    adjacentRatioLogs, ratioVariation, dispersion,
    repeatedMotif: { period, repetitions, error, adaptation }, surprise, alternationBurden };
  if (![raw, ...normalizedIOIs, dispersion, ratioVariation, error, adaptation, surprise].every(Number.isFinite))
    throw new Error('Non-finite rhythm complexity');
  return result;
}

export type KeyboardRhythmOnset = {
  ms: number; beat: number; noteIds: number[]; positions: Note['position'][]; kinds: Note['type'][];
  source: { noteId: number; line: number; column: number; text: string; division: number | null }[];
};
export type KeyboardRhythmWindow = {
  startMs: number; endMs: number; startBeat: number; endBeat: number; raw: number; noteIds: number[];
  rhythm: RhythmComplexityEvidence; onsets: KeyboardRhythmOnset[];
  movementSteps: number[]; movementMean: number; onsetRate: number;
  recoveryWeights: number[]; executionRhythmRaw: number;
  components: { rhythm: number; execution: number; movementCoupling: number };
};
export type KeyboardRhythmResult = {
  raw: number;
  windows: KeyboardRhythmWindow[]; onsetCount: number;
  parameters: typeof RHYTHM_COMPLEXITY_PARAMETERS;
};

export function inputOnsets(chart: Chart, includeSlideHeads = false, physicalTimes = false): KeyboardRhythmOnset[] {
  const timeline = TimingTimeline.fromChart(chart), onsets: KeyboardRhythmOnset[] = [];
  const sources = chart.notes.filter(note => !note.isMine &&
    (note.type !== 'slide' || (includeSlideHeads && !note.isHeadless)))
    .map(note => ({ note, chartMs: note.timingMs - (note.pseudoEachOffsetMs ?? 0) }))
    .sort((a, b) => (physicalTimes ? a.note.timingMs - b.note.timingMs : a.chartMs - b.chartMs) || String(a.note.position).localeCompare(String(b.note.position)) ||
      a.note.type.localeCompare(b.note.type) || a.note.id - b.note.id);
  const seen = new Set<number>();
  for (const { note, chartMs } of sources) {
    if (seen.has(note.id)) continue;
    seen.add(note.id);
    const beat = timeline.scoreBeatFromChartMs(chartMs), ms = physicalTimes ?
      note.timingMs - timeline.msFromBeat(4) + chart.firstMs : timeline.audioMsFromScoreBeat(beat, chart.firstMs);
    if (!Number.isFinite(beat) || !Number.isFinite(ms)) throw new Error('Non-finite keyboard source timing');
    const source = { noteId: note.id, line: note.source.line, column: note.source.column,
      text: note.source.text, division: note.declaredDivisor ?? null };
    const previous = onsets.at(-1);
    if (previous && sameNumber(previous.ms, ms)) {
      previous.noteIds.push(note.id); previous.positions.push(note.position);
      previous.kinds.push(note.type); previous.source.push(source);
    } else onsets.push({ ms, beat, noteIds: [note.id], positions: [note.position], kinds: [note.type], source: [source] });
  }
  return onsets;
}

const ringSteps = (a: number, b: number) => Math.min(Math.abs(a - b), 8 - Math.abs(a - b));
export const inputPoint = (position: Note['position']) => typeof position === 'number' ? buttonPoint(position) : touchPoint(position);
export function inputDistance(a: Note['position'], b: Note['position']): number {
  if (typeof a === 'number' && typeof b === 'number') return ringSteps(a, b);
  const x = inputPoint(a), y = inputPoint(b);
  return Math.min(4, Math.hypot(x.x - y.x, x.y - y.y) / 2.4);
}
export function chordMovement(a: KeyboardRhythmOnset, b: KeyboardRhythmOnset): number {
  const before = [...new Set(a.positions)], after = [...new Set(b.positions)];
  return .5 * (mean(before.map(x => Math.min(...after.map(y => inputDistance(x, y))))) +
    mean(after.map(y => Math.min(...before.map(x => inputDistance(x, y))))));
}

function weightedQuantile(windows: readonly KeyboardRhythmWindow[], fraction: number): number {
  const ordered = [...windows].sort((a, b) => a.raw - b.raw);
  const total = sum(ordered.map(window => window.rhythm.iois.length));
  let cumulative = 0;
  for (const window of ordered) {
    cumulative += window.rhythm.iois.length;
    if (cumulative >= total * fraction) return window.raw;
  }
  return 0;
}

export function keyboardRhythmComplexity(chart: Chart): KeyboardRhythmResult {
  const onsets = inputOnsets(chart), windows: KeyboardRhythmWindow[] = [];
  const stride = RHYTHM_COMPLEXITY_PARAMETERS.keyboardWindowOnsets - 1;
  for (let index = 0; index < onsets.length - 1; index += stride) {
    const group = onsets.slice(index, index + stride + 1), first = group[0]!, last = group.at(-1)!;
    const rhythm = rhythmComplexity(group.map(onset => onset.beat));
    const movementSteps = group.slice(1).map((onset, i) => chordMovement(group[i]!, onset));
    const movementMean = mean(movementSteps), durationMs = last.ms - first.ms;
    if (durationMs <= 0) throw new Error('Non-increasing keyboard onset time');
    const onsetRate = (group.length - 1) * 1000 / durationMs;
    const recoveryWeights = rhythm.iois.slice(1).map((gap, i) =>
      2 * Math.min(gap, rhythm.iois[i]!) / (gap + rhythm.iois[i]!));
    const executableContrast = mean(rhythm.adjacentRatioLogs.map((contrast, i) => contrast * recoveryWeights[i]!));
    const executionRhythmRaw = executableContrast * (1 + .5 * (1 - rhythm.repeatedMotif.adaptation));
    const rhythmCost = executionRhythmRaw * onsetRate, movementCoupling = rhythmCost * movementMean / 4;
    windows.push({ startMs: first.ms, endMs: last.ms, startBeat: first.beat, endBeat: last.beat,
      raw: rhythmCost + movementCoupling, noteIds: group.flatMap(onset => onset.noteIds), rhythm,
      onsets: group, movementSteps, movementMean, onsetRate, recoveryWeights, executionRhythmRaw,
      components: { rhythm: rhythmCost, execution: onsetRate, movementCoupling } });
  }
  const iois = Math.max(1, onsets.length - 1);
  const average = sum(windows.map(window => window.raw * window.rhythm.iois.length)) / iois;
  const raw = RHYTHM_COMPLEXITY_PARAMETERS.chartMeanWeight * average +
    (1 - RHYTHM_COMPLEXITY_PARAMETERS.chartMeanWeight) * weightedQuantile(windows, RHYTHM_COMPLEXITY_PARAMETERS.chartPeakQuantile);
  if (!Number.isFinite(raw)) throw new Error('Non-finite keyboard rhythm result');
  return { raw, windows, onsetCount: onsets.length, parameters: RHYTHM_COMPLEXITY_PARAMETERS };
}
