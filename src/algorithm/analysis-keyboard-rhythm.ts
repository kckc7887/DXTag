import type { Note } from '../simai/types';

export function dottedBeatGapFlags(gaps: readonly number[]): boolean[] {
  return gaps.map((gap, i) => gap > 1e-6 && [gaps[i - 1], gaps[i + 1]].some(other =>
    other !== undefined && other > 1e-6 && [3, 1.5, .75].some(ratio =>
      Math.abs(gap / other - ratio) <= ratio * .025)));
}

export function isRapidSameKeyRun(notes: readonly Note[], minimumRate = 3): boolean {
  if (notes.length < 4 || typeof notes[0]!.position !== 'number') return false;
  return notes.every(note => note.position === notes[0]!.position) && notes.slice(1).every((note, i) => {
    const gap = note.timingMs - notes[i]!.timingMs;
    return gap > 1e-6 && 1000 / gap >= minimumRate - 1e-6;
  });
}
