import {getAvailableDifficulties, parseSimaiChart} from './simai/core/parser/SimaiParser';
import {baseBurden} from './algorithm/base-burden';
import {starComplexity} from './algorithm/star-complexity';
import {keyboardRhythmComplexity} from './algorithm/rhythm-complexity';
import {inputComplexity} from './algorithm/input-complexity';
import {complexityRadar, legacyRadar, type RadarScores} from './algorithm/five-axis-complexity';
import scale from './scale.json';

export const ALGORITHM_VERSION = 'dxtag-five-axis-v1.1';
export const SCALE_VERSION = scale.sourceProjection;
export const AXES = ['键盘', '星星', '技巧', '体力', '爆发'] as const;
export const DIFFICULTIES = {2:'BASIC',3:'ADVANCED',4:'EXPERT',5:'MASTER',6:'Re:MASTER'} as const;
export type Difficulty = keyof typeof DIFFICULTIES;
export type FiveAxisScores = RadarScores;
export type ChartScores = {title: string; difficulty: string; scores: FiveAxisScores};
export type ScoreResult = ChartScores[];
export type ScoreError = {difficulty: string; message: string};
const support = (raw: number, anchor: number) => Math.round(Math.max(0,Math.min(100,raw/anchor*100))*10)/10;

/** Calculate one normal chart from source text. Metadata only selects a slot;
 * displayed level, title, version and external reference labels are never used. */
export function scoreChart(text: string, difficulty: Difficulty): ChartScores {
  if (!Object.hasOwn(DIFFICULTIES, difficulty)) throw new Error('只支持普通谱 inote_2 至 inote_6。');
  const chart = parseSimaiChart(text, difficulty);
  const base = baseBurden(chart), star = starComplexity(chart, base.slideEvents);
  if (!star.coverage.complete || star.raw === null || star.techniqueRaw === null || star.burstRaw === null) {
    const known = new Set(base.slideEvents.map(e=>`${e.slideId}:${e.branchIndex}`));
    const missing = chart.notes.flatMap(n=>n.type==='slide'&&!n.isMine?n.branches.flatMap((b,i)=>
      known.has(`${n.id}:${i}`)?[]:[`第 ${n.source.line} 行 ${b.segments.map(s=>s.code).join('→')}`]):[]);
    throw new Error(`Slide 路径不完整（${star.coverage.observedBranches}/${star.coverage.expectedBranches}）；${missing.join('；') || '时值或几何无法完整解算'}。`);
  }
  const rhythm = keyboardRhythmComplexity(chart), input = inputComplexity(chart);
  const result = complexityRadar(legacyRadar(base.features, scale.baseline), support(star.raw,scale.star),{
    star_technique:support(star.techniqueRaw,scale.starTechnique),star_burst:support(star.burstRaw,scale.starBurst),
    keyboard_rhythm:support(rhythm.raw,scale.rhythm),touch_input:support(input.touchRaw,scale.touch),hold_lock:support(input.raw,scale.holdLock)});
  return {title:chart.title,difficulty:DIFFICULTIES[difficulty],
    scores:Object.fromEntries(AXES.map(axis=>[axis,Math.round(result[axis])/10])) as FiveAxisScores};
}

/** Score the selected slots. An error handler can collect failures and continue. */
export function scoreMaidata(text: string, difficulty?: Difficulty, onError?: (error: ScoreError) => void): ScoreResult {
  if (difficulty !== undefined && !Object.hasOwn(DIFFICULTIES,difficulty)) throw new Error('只支持普通谱 inote_2 至 inote_6。');
  const available=getAvailableDifficulties(text);
  const slots=difficulty===undefined?Object.keys(DIFFICULTIES).map(Number).filter(n=>available[n as Difficulty]) as Difficulty[]:[difficulty];
  if (!slots.length) throw new Error('文件中没有普通谱：需要 &inote_2 至 &inote_6。');
  const charts:ChartScores[]=[];
  for (const inote of slots) {
    try {charts.push(scoreChart(text,inote));}
    catch(error) {
      if (!onError) throw error;
      onError({difficulty:DIFFICULTIES[inote],message:error instanceof Error?error.message:String(error)});
    }
  }
  return charts;
}
