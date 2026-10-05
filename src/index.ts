import {getAvailableDifficulties, parseSimaiChart} from './simai/core/parser/SimaiParser';
import {baseBurden} from './algorithm/base-burden';
import {starComplexity} from './algorithm/star-complexity';
import {keyboardRhythmComplexity} from './algorithm/rhythm-complexity';
import {inputComplexity} from './algorithm/input-complexity';
import {normalizeLegacyRadar, projectLibraryRadar, type RadarScores} from './algorithm/five-axis-complexity';
import scale from './scale.json';

export const ALGORITHM_VERSION = 'dxtag-five-axis-v1.5';
export {chartRelativeRadar, normalizeLegacyRadar, projectLibraryRadar, CHART_RELATIVE_VERSION, CHART_RELATIVE_POLICY} from './algorithm/five-axis-complexity';
export type {RadarProjection} from './algorithm/five-axis-complexity';
export const SCALE_VERSION = scale.sourceProjection;
export const AXES = ['键盘', '星星', '技巧', '体力', '爆发'] as const;
export const DIFFICULTIES = {2:'BASIC',3:'ADVANCED',4:'EXPERT',5:'MASTER',6:'Re:MASTER'} as const;
export type Difficulty = keyof typeof DIFFICULTIES;
export type FiveAxisScores = RadarScores;
export type ChartScores = {title: string; difficulty: string; scores: FiveAxisScores; chartRelativeScores: FiveAxisScores};
export type ScoreResult = ChartScores[];
export type ScoreError = {difficulty: string; message: string};

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
  const result = projectLibraryRadar(normalizeLegacyRadar(base.features, scale.baseline), star.raw/scale.star*100,{
    star_technique:star.techniqueRaw/scale.starTechnique*100,star_burst:star.burstRaw/scale.starBurst*100,
    keyboard_rhythm:rhythm.raw/scale.rhythm*100,touch_input:input.touchRaw/scale.touch*100,hold_lock:input.raw/scale.holdLock*100});
  return {title:chart.title,difficulty:DIFFICULTIES[difficulty],
    scores:Object.fromEntries(AXES.map(axis=>[axis,Math.round(result.fused[axis])/10])) as FiveAxisScores,
    chartRelativeScores:result.chartRelativeScores};
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
