import type { SlideEvent } from './types';

const EPSILON_MS = 1e-6;
const NEIGHBOR_DURATION_RATIO = 4;
const LATTICE_TOLERANCE = .025;

export type LocalRhythmOnset = {
  slideId: number; branchIndex: number; kind: 'launch' | 'head'; timeMs: number; beat: number;
};
export type LocalRhythmInterval = {
  from: LocalRhythmOnset; to: LocalRhythmOnset; gapMs: number; gapBeats: number;
};
export type LocalMotionRhythm = {
  slideId: number; branchIndex: number; pulseMs: number;
  source: 'declared-wait' | 'nearby-launches' | 'nearby-heads' | 'motion-duration';
  evidence: {
    headMs: number; headBeat: number; launchMs: number; launchBeat: number;
    waitMs: number; declaredWaitBeats: number; actualWaitBeatSpan: number;
    motionMs: number; motionBeatSpan: number; neighborDurationRatio: number;
    onsets: LocalRhythmOnset[]; intervals: LocalRhythmInterval[]; inferredDivisor: number;
  };
};

export const motionRhythmKey = (slideId: number, branchIndex: number) => `${slideId}:${branchIndex}`;

function intervalPulse(intervals: readonly LocalRhythmInterval[]): { pulseMs: number; divisor: number } {
  const gaps = intervals.map(interval => interval.gapMs).filter(gap => gap > EPSILON_MS);
  const shortest = Math.min(...gaps);
  for (const divisor of [1, 2, 3, 4]) {
    const pulseMs = shortest / divisor;
    if (gaps.every(gap => Math.abs(gap / pulseMs - Math.round(gap / pulseMs)) <= LATTICE_TOLERANCE)) {
      return { pulseMs, divisor };
    }
  }
  return { pulseMs: shortest, divisor: 1 };
}

function localOnsets(event: SlideEvent, events: readonly SlideEvent[], kind: 'launch' | 'head'): LocalRhythmOnset[] {
  const radius = Math.max(EPSILON_MS, event.endMs - event.startMs) * NEIGHBOR_DURATION_RATIO;
  const current: LocalRhythmOnset = { slideId: event.slideId, branchIndex: event.branchIndex,
    kind: 'launch', timeMs: event.startMs, beat: event.startBeat };
  const candidates = events.filter(other => other.slideId !== event.slideId && (kind !== 'head' || !other.headless))
    .map(other => ({ slideId: other.slideId, branchIndex: other.branchIndex, kind,
      timeMs: kind === 'launch' ? other.startMs : other.headMs, beat: kind === 'launch' ? other.startBeat : other.headBeat }))
    .filter(onset => Math.abs(onset.timeMs - current.timeMs) <= radius + EPSILON_MS);
  const independent = new Map<number, LocalRhythmOnset>();
  for (const onset of candidates) {
    const prior = independent.get(onset.slideId);
    if (!prior || Math.abs(onset.timeMs - current.timeMs) < Math.abs(prior.timeMs - current.timeMs)) independent.set(onset.slideId, onset);
  }
  const ordered = [current, ...independent.values()].sort((a,b)=>a.timeMs-b.timeMs ||
    Number(b===current)-Number(a===current) || a.slideId-b.slideId || a.branchIndex-b.branchIndex);
  const unique: LocalRhythmOnset[] = [];
  for (const onset of ordered) if (!unique.length || onset.timeMs - unique.at(-1)!.timeMs > EPSILON_MS) unique.push(onset);
  return unique;
}

export function localMotionRhythm(events: readonly SlideEvent[]): Map<string, LocalMotionRhythm> {
  const result = new Map<string, LocalMotionRhythm>();
  for (const event of events) {
    const evidence: LocalMotionRhythm['evidence'] = {
      headMs:event.headMs,headBeat:event.headBeat,launchMs:event.startMs,launchBeat:event.startBeat,
      waitMs:event.waitMs,declaredWaitBeats:event.declaredWaitBeats,actualWaitBeatSpan:event.startBeat-event.headBeat,
      motionMs:Math.max(0,event.endMs-event.startMs),motionBeatSpan:event.endBeat-event.startBeat,
      neighborDurationRatio:NEIGHBOR_DURATION_RATIO,onsets:[],intervals:[],inferredDivisor:1,
    };
    let pulseMs: number, source: LocalMotionRhythm['source'];
    if (event.waitMs > 0) {
      pulseMs=event.waitMs;source='declared-wait';
    } else {
      let onsets=localOnsets(event,events,'launch');
      source='nearby-launches';
      if(onsets.length<2){onsets=localOnsets(event,events,'head');source='nearby-heads';}
      if(onsets.length>=2){
        evidence.onsets=onsets;
        evidence.intervals=onsets.slice(1).map((to,index)=>({from:onsets[index]!,to,gapMs:to.timeMs-onsets[index]!.timeMs,gapBeats:to.beat-onsets[index]!.beat}));
        const inferred=intervalPulse(evidence.intervals);pulseMs=inferred.pulseMs;evidence.inferredDivisor=inferred.divisor;
      }else{
        pulseMs=Math.max(EPSILON_MS,event.endMs-event.startMs);source='motion-duration';
        evidence.onsets=onsets;
      }
    }
    result.set(motionRhythmKey(event.slideId,event.branchIndex),{slideId:event.slideId,branchIndex:event.branchIndex,pulseMs,source,evidence});
  }
  return result;
}
