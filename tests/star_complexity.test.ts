import assert from 'node:assert/strict';
import test from 'node:test';
import {parseSimaiChart} from '../src/simai/core/parser/SimaiParser';
import {prepareBranch} from '../src/simai/core/geometry/slidePath';
import {TimingTimeline} from '../src/simai/core/timing/TimingTimeline';
import type {Chart} from '../src/simai/types';
import type {SlideEvent} from '../src/algorithm/types';
import {starComplexity} from '../src/algorithm/star-complexity';

const chart=(body:string)=>parseSimaiChart(`&first=0\n&inote_4=${body},E`,4);
// Only public source/timing/geometry: no invocation of previous rule analyzers.
function events(c:Chart):SlideEvent[]{
  const timeline=TimingTimeline.fromChart(c),beat=(ms:number)=>timeline.scoreBeatFromAudioMs(ms,c.firstMs),result:SlideEvent[]=[];
  for(const n of c.notes)if(n.type==='slide'&&!n.isMine)for(const [branchIndex,b] of n.branches.entries()){
    let pieces:ReturnType<typeof prepareBranch>;try{pieces=prepareBranch(b);}catch{continue;}
    const headMs=n.timingMs-timeline.msFromBeat(4)+c.firstMs,startMs=headMs+b.delayMs,endMs=startMs+b.durationMs;
    result.push({slideId:n.id,branchIndex,headMs,startMs,endMs,waitMs:b.delayMs,headBeat:beat(headMs),startBeat:beat(startMs),endBeat:beat(endMs),
      declaredWaitBeats:b.delayMs*n.bpm/60000,headPosition:n.position,headless:n.isHeadless,code:b.segments.map(s=>s.code).join('→'),speed:0,
      segments:pieces.map((p,i)=>({code:b.segments[i]!.code,startMs:headMs+p.startMs,endMs:headMs+p.startMs+p.durationMs,
        startBeat:beat(headMs+p.startMs),endBeat:beat(headMs+p.startMs+p.durationMs),length:p.geometry.length,speed:0})),turns:[],zones:[]});
  }return result;
}
const run=(body:string)=>{const c=chart(body);return starComplexity(c,events(c));};
const close=(a:number|null,b:number|null,tolerance=1e-7)=>assert.ok(a!==null&&b!==null&&Math.abs(a-b)<=tolerance*Math.max(1,Math.abs(a),Math.abs(b)),`${a} != ${b}`);

test('keyboard-only / star-shaped TAP produces no star value or windows',()=>{
  for(const body of ['(180){16}1,2,3/7,4,3,2,1,','(120){4}1$,2h[2:1],B1,C1h[2:1]']){
    const r=run(body);assert.equal(r.raw,0);assert.equal(r.techniqueRaw,0);assert.equal(r.burstRaw,0);assert.deepEqual(r.profile,[]);
    assert.deepEqual(r.windows,[]);assert.equal(r.coverage.expectedBranches,0);assert.equal(r.coverage.complete,true);
  }
});
test('one real ordinary Slide has positive continuous workload and exact 16/4 beat windows',()=>{
  const r=run('(120){4}1-5[4:1]');assert.ok(r.raw!>0);assert.equal(r.coverage.complete,true);
  assert.equal(r.windows.length,1);assert.equal(r.windows[0]!.startBeat,0);assert.equal(r.windows[0]!.endBeat,16);
  assert.equal(r.windows[0]!.endMs-r.windows[0]!.startMs,8000);assert.deepEqual(r.windows[0]!.slideIds,[0]);
});
test('missing, duplicated, extra, stale or invalid cache is unknown rather than zero workload',()=>{
  const c=chart('(120){4}1-5[4:1]'),e=events(c);
  const stale=structuredClone(e);stale[0]!.endMs+=100;
  const wrongSegment=structuredClone(e);wrongSegment[0]!.segments[0]!.length+=1;
  for(const input of [[],[...e,...e],[...e,{...e[0]!,slideId:999}],stale,wrongSegment]){
    const r=starComplexity(c,input);assert.equal(r.raw,null);assert.equal(r.techniqueRaw,null);assert.equal(r.burstRaw,null);
    assert.deepEqual(r.profile,[]);assert.equal(r.components,null);assert.equal(r.coverage.complete,false);
  }
  const invalid=run('(120){4}1^5[4:1]');assert.equal(invalid.raw,null);assert.equal(invalid.coverage.expectedBranches,1);
});
test('complete coincident paths deduplicate both same-head branches and separate authored sources',()=>{
  const solo=run('(120){4}1-5[4:1]'),same=run('(120){4}1-5[4:1]*-5[4:1]'),separate=run('(120){4}1-5[4:1]/1-5[4:1]');
  close(same.raw,solo.raw);close(separate.raw,solo.raw);
  assert.equal(same.coverage.expectedBranches,2);assert.equal(separate.windows[0]!.branchCount,2);
  assert.deepEqual(separate.windows[0]!.slideIds,[0,1]);
});
test('independent simultaneous paths and same-head divergent branches increase coordination',()=>{
  const solo=run('(120){4}1-5[4:1]'),dual=run('(120){4}1-5[4:1]/3-7[4:1]'),fork=run('(120){4}1-3[4:1]*-7[4:1]');
  assert.ok(dual.raw!>solo.raw!);assert.ok(dual.components!.coordination>0);assert.ok(fork.components!.coordination>0);
});
test('fan increases nominal span workload but policy explicitly excludes exact three-hand trajectory claims',()=>{
  const solo=run('(120){4}1-5[4:1]'),fan=run('(120){4}1w5[4:1]');
  assert.equal(fan.coverage.complete,true);assert.ok(fan.raw!>solo.raw!);assert.match(fan.policy.fan,/not three human hands/);
});
test('connected turns increase continuous motion; representational arc splitting does not add a segment-count bonus',()=>{
  const simple=run('(120){4}1-5[2:1]'),turn=run('(120){4}1-5[4:1]-3[4:1]');assert.ok(turn.components!.motion>simple.components!.motion);
  // Below the midline '<' continues the same clockwise path; '>' would take
  // the long way round. Generated whole/split tables differ in length ~0.03%.
  const whole=run('(120){4}1>5[2:1]'),split=run('(120){4}1>3[4:1]<5[4:1]');close(whole.raw,split.raw,1e-3);
});
test('whole-score speedup preserves Slide structure while increasing physical motion and actual waiting-contact rate',()=>{
  const body='{4}1-5[4:1],2,3-7[4:1],4,5-1[4:1]',slow=run('(120)'+body),fast=run('(240)'+body);
  assert.ok(fast.components!.motion>slow.components!.motion);
  close(fast.components!.rhythm,slow.components!.rhythm);close(fast.components!.coordination,slow.components!.coordination);
  // Faster waiting contacts cost more, whereas a slower motion must be
  // followed for longer. Check these independent quantities, not an assumed
  // monotonic direction for their combined context component.
  assert.ok(fast.windows[0]!.waiting.raw>slow.windows[0]!.waiting.raw);
  assert.ok(slow.occupancy!.trackingRaw>fast.occupancy!.trackingRaw);
  assert.ok(fast.raw!>slow.raw!);
  assert.ok(fast.windows[0]!.waiting.rate>slow.windows[0]!.waiting.rate);
  assert.ok(fast.burstRaw!>slow.burstRaw!);
});
test('equivalent actual BPM/subdivision and specified duration retain every whole-chart component',()=>{
  const a=run('(120){8}1-5[4:1],1,2,3,5,6'),b=run('(240){4}1-5[120#4:1],1,2,3,5,6');
  close(a.raw,b.raw);for(const k of Object.keys(a.components!) as (keyof typeof a.components)[])close(a.components![k],b.components![k]);
});
test('Slide-relative before/after keyboard and locking TouchHold context increases only coupled workload',()=>{
  const bare=run('(120){4},1-5[4:1],,,,'),context=run('(120){4}2,1-5[4:1],,3,,'),held=run('(120){4}C1h[1:2],1-5[4:1],,,,');
  assert.ok(context.components!.context>bare.components!.context);assert.ok(held.components!.context>bare.components!.context);
  assert.ok(context.windows[0]!.contextNoteIds.length>=2);assert.ok(held.windows[0]!.contextNoteIds.includes(0));
  const far=run('(120){4},1-5[4:1],'+','.repeat(30)+'2/6');close(far.raw,bare.raw);
});
test('different motion rates add continuous dual-rhythm complexity, without a class threshold',()=>{
  const equalSpeed=run('(120){4}1-5[2:1]/3-7[2:1]'),unequal=run('(120){4}1-5[2:1]/3-7[4:1]');
  assert.ok(unequal.components!.rhythm>equalSpeed.components!.rhythm);
});
test('source metadata and old thresholded turns/speeds/zone caches do not affect complexity',()=>{
  const c=chart('(120){4}1-5[4:1],2'),e=events(c),before=JSON.stringify(c),a=starComplexity(c,e),b=structuredClone(c),other=structuredClone(e);
  b.title='15 label';b.level={'4':'15'};b.difficulty=6;b.designer='irrelevant';
  other[0]!.turns=[{atMs:1,atBeat:1,position:7,angleDeg:999,kind:'V'}];other[0]!.speed=999;
  assert.deepEqual(starComplexity(b,other),a);assert.equal(JSON.stringify(c),before);
});
test('pseudo-EACH retains actual physical head/motion time while structural beat ordering stays source based',()=>{
  const c=chart('(120){8}1/3-7[4:1],,,1'),shifted=structuredClone(c),e=events(c);
  const n=shifted.notes.find(n=>n.type==='slide')!;n.pseudoEachOffsetMs=100;n.timingMs+=100;n.endTimeMs+=100;
  const se=events(shifted),result=starComplexity(shifted,se);
  assert.equal(result.coverage.complete,true);assert.ok(result.raw!>0);assert.notEqual(result.components!.context,starComplexity(c,e).components!.context);
  assert.equal(result.windows[0]!.startBeat,0);
});
test('cross-BPM window boundaries come from integrated Timeline, not fixed millisecond bins',()=>{
  const c=chart('(120){4}1-5[2:1],(240)2,3'),r=starComplexity(c,events(c)),timeline=TimingTimeline.fromChart(c);
  assert.equal(r.windows[0]!.endMs,timeline.audioMsFromScoreBeat(16,c.firstMs));assert.notEqual(r.windows[0]!.endMs,8000);
  for(const p of r.profile){assert.equal(p.startMs,timeline.audioMsFromScoreBeat(p.startBeat,c.firstMs));
    assert.equal(p.endMs,timeline.audioMsFromScoreBeat(p.endBeat,c.firstMs));assert.equal(p.endBeat-p.startBeat,4);}
  assert.notEqual(r.profile[0]!.endMs-r.profile[0]!.startMs,2000);
});
test('a long Slide does not leak a late keyboard context into an earlier core plus two-beat context',()=>{
  const bare=run('(120){4}1-5[1:6]'+','.repeat(21)),late=run('(120){4}1-5[1:6]'+','.repeat(20)+'3');
  const first=late.windows.find(w=>w.startBeat===0)!;
  assert.ok(first.components.context>0);assert.deepEqual(first.contextNoteIds,[]);
  assert.equal(first.occupancy.headReturnCount,0);assert.ok(first.occupancy.trackingRaw>0);
  close(first.raw,bare.windows.find(w=>w.startBeat===0)!.raw);
  assert.ok(late.windows.some(w=>w.startBeat>=4&&w.contextNoteIds.includes(1)&&w.components.context>0));
});
test('waiting true-contact count and actual onset rate continuously increase source planning workload',()=>{
  const slow=run('(120){4}1-5[2##1],2,3,4'),fast=run('(240){4}1-5[1##1],2,3,4'),
    more=run('(120){8}1-5[2##1],2,3,4,5,6,7,8'),s=slow.windows[0]!.waiting,f=fast.windows[0]!.waiting,m=more.windows[0]!.waiting;
  assert.equal(s.noteCount,3);assert.equal(s.onsetCount,3);assert.equal(f.noteCount,s.noteCount);
  close(s.durationMs,2000);close(f.durationMs,1000);close(s.rate,1.5);close(f.rate,3);
  assert.ok(f.raw>s.raw);assert.ok(fast.techniqueRaw!>slow.techniqueRaw!);
  assert.equal(m.noteCount,7);assert.ok(m.rate>s.rate);assert.ok(more.techniqueRaw!>slow.techniqueRaw!);
});
test('the same waiting-note count and rate has more difficulty for dotted/uneven beat IOIs than regular onsets',()=>{
  const regular=run('(120){4}1-5[2##1],2,3,4'),uneven=run('(120){16}1-5[2##1],,,2,,,3,,,,,,4'),
    a=regular.windows[0]!.waiting,b=uneven.windows[0]!.waiting;
  assert.equal(a.noteCount,b.noteCount);assert.equal(a.onsetCount,b.onsetCount);close(a.rate,b.rate);
  close(a.irregularity,0);assert.ok(b.irregularity>a.irregularity);assert.ok(b.raw>a.raw);
  assert.ok(uneven.components!.rhythm>regular.components!.rhythm);assert.ok(uneven.techniqueRaw!>regular.techniqueRaw!);
});
test('waiting counts true source contacts once when several same-head branches share the stage',()=>{
  const a=run('(120){4}1-5[2##1],2-6[1##1],3'),b=run('(120){4}1-5[2##1],2-6[1##1]*-6[1##1],3');
  assert.deepEqual(b.windows[0]!.waiting,a.windows[0]!.waiting);close(a.raw,b.raw);
});
test('closer-in-time tail handover and before-head planning increase generic context',()=>{
  const immediate=run('(120){4}1-5[4:1],,5'),later=run('(120){4}1-5[4:1],,,,5');
  assert.ok(immediate.components!.context>later.components!.context);assert.ok(immediate.techniqueRaw!>later.techniqueRaw!);
  const bare=run('(120){4},1-5[4:1]'),before=run('(120){4}5,1-5[4:1]');assert.ok(before.techniqueRaw!>bare.techniqueRaw!);
});
test('four-beat profile retains recovery blocks and continuous positive rise supports a complex spike',()=>{
  const ordinary=run('(120){4}1-5[4:1]'),complex=run('(120){16}1-5[4:1]'+','.repeat(32)+'1-5[16:1]/3-7[16:1]/5-1[16:1]/7-3[16:1],2/6,4/8');
  assert.ok(complex.profile.some(p=>p.raw===0&&p.slideIds.length===0));
  for(const [i,p]of complex.profile.entries()){
    assert.equal(p.endBeat-p.startBeat,4);close(p.riseRaw,Math.max(0,p.raw-(complex.profile[i-1]?.raw??0)));
    if(i)assert.equal(p.startBeat,complex.profile[i-1]!.endBeat);
  }
  close(complex.burstRaw,Math.max(...complex.profile.map(p=>p.riseRaw)));
  assert.ok(complex.burstRaw!>ordinary.burstRaw!);assert.ok(complex.techniqueRaw!>ordinary.techniqueRaw!);
});
test('profile technique is local, preserving a low ordinary Slide block beside a later complex waiting block',()=>{
  const r=run('(120){4}1-5[4:1]'+','.repeat(16)+'3-7[2##1],1,2,8'),
    ordinary=r.profile.find(p=>p.startBeat===0)!,complex=r.profile.find(p=>p.startBeat===16)!;
  assert.ok(Number.isFinite(ordinary.techniqueRaw)&&ordinary.techniqueRaw>=0);
  assert.ok(complex.techniqueRaw>ordinary.techniqueRaw);
  assert.deepEqual(ordinary.contextNoteIds,[]);assert.ok(complex.contextNoteIds.length>0);
  for(const empty of r.profile.filter(p=>!p.slideIds.length))assert.equal(empty.techniqueRaw,0);
});

test('slower isolated paths retain bounded continuous following without inventing original-head contacts',()=>{
  const fast=run('(120){4}1-5[0##.5]'),slow=run('(120){4}1-5[0##4]');
  assert.ok(slow.occupancy!.trackingRaw>fast.occupancy!.trackingRaw);
  assert.ok(fast.components!.motion>slow.components!.motion);
  assert.equal(slow.occupancy!.headReturnCount,0);assert.equal(slow.occupancy!.headReturnRaw,0);
  close(slow.components!.context,Math.log1p(4)*Math.sqrt(2));
  assert.ok(slow.raw!<fast.raw!*2); // No inverse-speed divergence or hand-lock assumption.
});

test('foreign TAP and HOLD at the departed star head add more complexity than adjacent-button contacts',()=>{
  const origin=run('(120){8}1-5[2:1],,,,1,1h[4:1]'),near=run('(120){8}1-5[2:1],,,,2,2h[4:1]');
  assert.equal(origin.occupancy!.headReturnCount,2);assert.equal(near.occupancy!.headReturnCount,0);
  assert.ok(origin.components!.context>near.components!.context);assert.ok(origin.techniqueRaw!>near.techniqueRaw!);
  const evidence=origin.windows[0]!.occupancy.events;
  assert.deepEqual(evidence.map(e=>e.kind),['tap','hold-start']);
  assert.deepEqual(evidence.map(e=>e.source.text),['1','1h[4:1]']);
  assert.ok(evidence.every(e=>e.slideIds.includes(0)&&e.noteId!==0&&e.remainingMs>0&&e.pathDistance>0));
  close(evidence[1]!.holdOverlapMs,250);assert.equal(evidence[0]!.atBeat,2);
});

test('own star, before launch, exact launch and exact tail contacts do not become moving-head returns',()=>{
  for(const body of ['(120){4}1-5[4:1]','(120){8}1-5[4:1],1',
    '(120){4}1-5[4:1],1','(120){4}1-5[4:1],,1']){
    const r=run(body);assert.equal(r.occupancy!.headReturnCount,0);assert.equal(r.occupancy!.headReturnRaw,0);
  }
  // A round-trip coordinate conversion cannot turn an exact tail into a
  // preceding overlap. This tolerance is numerical identity, not judgement.
  const c=chart('(86){8}8-4[2:1],,,,8'),n=c.notes[1]!,slide=c.notes[0]!;
  n.timingMs=slide.endTimeMs-1e-9;n.endTimeMs=n.timingMs;
  assert.equal(starComplexity(c,events(c)).occupancy!.headReturnCount,0);
});

test('a HOLD already active at launch couples its sustained origin occupancy; a headless path has no original star head',()=>{
  const held=run('(120){4}1h[1:1]/1-5[2:1]');assert.equal(held.occupancy!.headReturnCount,1);
  assert.ok(held.occupancy!.headReturnRaw>0);assert.ok(held.windows[0]!.occupancy.events[0]!.holdOverlapMs>0);
  const c=chart('(120){8}1-5[2:1],,,,1');const n=c.notes.find(n=>n.type==='slide')!;
  n.isHeadless=true;const r=starComplexity(c,events(c));
  assert.equal(r.occupancy!.headReturnCount,0);assert.ok(r.occupancy!.trackingRaw>0);
});

test('coincident branches do not double tracking or foreign-origin evidence, while an A Touch can occupy that region',()=>{
  const solo=run('(120){8}1-5[2:1],,,,1'),duplicate=run('(120){8}1-5[2:1]*-5[2:1],,,,1'),touch=run('(120){8}1-5[2:1],,,,A1');
  assert.deepEqual(duplicate.occupancy,solo.occupancy);close(duplicate.raw,solo.raw);
  assert.equal(duplicate.windows[0]!.occupancy.events.length,1);assert.deepEqual(duplicate.windows[0]!.occupancy.events[0]!.branchKeys,['0:0','0:1']);
  assert.equal(touch.occupancy!.headReturnCount,1);assert.ok(touch.occupancy!.headReturnRaw<solo.occupancy!.headReturnRaw);
});

test('tracking and moving origin occupancy retain actual-timing equivalence and do not read display/source labels',()=>{
  const a=run('(120){8}1-5[2:1],,,,1,1h[4:1]'),b=run('(240){4}1-5[120#2:1],,,,1,1h[120#4:1]');
  close(a.raw,b.raw);for(const key of ['trackingRaw','movingDurationMs','headReturnRaw','headReturnCount'] as const)close(a.occupancy![key],b.occupancy![key]);
  const noSlide=run('(120){16}1,1h[4:1],1$,C1');assert.deepEqual(noSlide.occupancy,{movingDurationMs:0,trackingRaw:0,headReturnRaw:0,headReturnCount:0});
  const bad=chart('(120){4}1-5[4:1]');assert.equal(starComplexity(bad,[]).occupancy,null);
});

test('window occupancy clips a long original-head HOLD and excludes later return contacts from earlier cores',()=>{
  const r=run('(120){4}1-5[1:6],1h[1:6]'+','.repeat(19)+'1');
  const early=r.windows.find(w=>w.startBeat===0)!,later=r.windows.find(w=>w.startBeat===4)!;
  assert.deepEqual(early.occupancy.events.map(e=>e.noteId),[1]);
  assert.ok(early.occupancy.events[0]!.endBeat<=18);assert.ok(later.occupancy.events.some(e=>e.noteId===2));
  assert.ok(early.occupancy.movingDurationMs<r.occupancy!.movingDurationMs);
});
