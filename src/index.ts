import {getAvailableDifficulties, parseSimaiChart, validateDifficulty} from './simai/core/parser/SimaiParser';
import {baseBurden} from './algorithm/base-burden';
import {starComplexity} from './algorithm/star-complexity';
import {keyboardRhythmComplexity} from './algorithm/rhythm-complexity';
import {inputComplexity} from './algorithm/input-complexity';
import {complexityRadar, baselineRadar} from './algorithm/five-axis-complexity';
import scale from './scale.json';

declare const __DXTAG_VERSION__: string;
export const ALGORITHM_VERSION = __DXTAG_VERSION__;
export const SCALE_VERSION = ALGORITHM_VERSION;
export const AXES = ['键盘', '星星', '技巧', '体力', '爆发'] as const;
export const DIFFICULTIES = {1:'EASY',2:'BASIC',3:'ADVANCED',4:'EXPERT',5:'MASTER',6:'Re:MASTER',7:'UTAGE'} as const;
export type Difficulty = number;
export type DifficultySelection = Difficulty | readonly Difficulty[] | 'all';
export type FiveAxisScores = Record<typeof AXES[number], number>;
export type ChartScores = {title: string; slot: Difficulty; difficulty: string; scores: FiveAxisScores};
export type ScoreResult = ChartScores[];
export type ScoreError = {slot: Difficulty; difficulty: string; message: string};
const support = (raw: number, anchor: number) => Math.round(Math.max(0,Math.min(100,raw/anchor*100))*10)/10;
const difficultyName = (slot: Difficulty): string =>
  DIFFICULTIES[slot as keyof typeof DIFFICULTIES] ?? `inote_${slot}`;

export function listDifficulties(text: string): Difficulty[] {
  return Object.keys(getAvailableDifficulties(text)).map(Number).sort((a,b)=>a-b);
}

export function scoreChart(text: string, difficulty: Difficulty): ChartScores {
  const chart = parseSimaiChart(text, difficulty);
  const base = baseBurden(chart), star = starComplexity(chart, base.slideEvents);
  if (!star.coverage.complete || star.raw === null || star.techniqueRaw === null || star.burstRaw === null) {
    const known = new Set(base.slideEvents.map(e=>`${e.slideId}:${e.branchIndex}`));
    const missing = chart.notes.flatMap(n=>n.type==='slide'&&!n.isMine?n.branches.flatMap((b,i)=>
      known.has(`${n.id}:${i}`)?[]:[`第 ${n.source.line} 行 ${b.segments.map(s=>s.code).join('→')}`]):[]);
    throw new Error(`Slide 路径不完整（${star.coverage.observedBranches}/${star.coverage.expectedBranches}）；${missing.join('；') || '时值或几何无法完整解算'}。`);
  }
  const rhythm = keyboardRhythmComplexity(chart), input = inputComplexity(chart);
  const result = complexityRadar(baselineRadar(base.features, scale.baseline), support(star.raw,scale.star),{
    star_technique:support(star.techniqueRaw,scale.starTechnique),star_burst:support(star.burstRaw,scale.starBurst),
    keyboard_rhythm:support(rhythm.raw,scale.rhythm),touch_input:support(input.touchRaw,scale.touch),hold_lock:support(input.raw,scale.holdLock)});
  return {title:chart.title,slot:difficulty,difficulty:difficultyName(difficulty),
    scores:Object.fromEntries(AXES.map(axis=>[axis,Math.round(result[axis])/10])) as FiveAxisScores};
}

export function scoreMaidata(text: string, selection?: DifficultySelection, onError?: (error: ScoreError) => void): ScoreResult {
  const available = listDifficulties(text);
  const selected = selection === undefined || selection === 'all'
    ? available : typeof selection === 'number' ? [selection] : selection;
  if (!Array.isArray(selected)) throw new Error('难度选择须为正安全整数、编号数组或 all。');
  if (!selected.length) throw new Error('难度选择为空；需要至少一个正文非空的 inote_N 槽位。');
  for (const slot of selected) {
    validateDifficulty(slot);
    if (!available.includes(slot)) throw new Error(`inote_${slot} 缺失或正文为空。`);
  }
  const slots = [...new Set<number>(selected)].sort((a,b)=>a-b);
  const charts:ChartScores[]=[];
  for (const inote of slots) {
    try {charts.push(scoreChart(text,inote));}
    catch(error) {
      if (!onError) throw error;
      onError({slot:inote,difficulty:difficultyName(inote),message:error instanceof Error?error.message:String(error)});
    }
  }
  return charts;
}
