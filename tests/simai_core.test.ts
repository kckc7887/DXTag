import assert from 'node:assert/strict';
import test from 'node:test';
import {parseSimaiBody, parseSimaiChart, parseDuration} from '../src/simai/core/parser/SimaiParser';
import {TimingTimeline} from '../src/simai/core/timing/TimingTimeline';
import {buttonPoint, touchPoint, pathPose, prepareBranch} from '../src/simai/core/geometry/slidePath';
import type {SlideNote} from '../src/simai/types';

const close=(a:number,b:number,tolerance=1e-8)=>assert.ok(Math.abs(a-b)<=tolerance,`${a} != ${b}`);
const chart=(s:string)=>parseSimaiBody(s);
const slide=(code:string)=>chart(`(120){4}${code},E`).notes[0] as SlideNote;
const geometry=(code:string)=>prepareBranch(slide(`${code}[4:1]`).branches[0]!)[0]!.geometry;
const physical=(s:string)=>{
  const c=chart(s), t=TimingTimeline.fromChart(c);
  return c.notes.map(n=>({type:n.type,position:n.position,start:n.timingMs-t.msFromBeat(4),end:n.endTimeMs-t.msFromBeat(4)}));
};

test('comma clock, comments and whitespace preserve offsets into the original maidata',()=>{
  const text='&title=测试\n&first=-0.25\n&des_5=作者\n&inote_5=\n(120){ 8}1 x / 2h[4:1], || omitted 8,8,\n34`5, E';
  const c=parseSimaiChart(text,5),n=c.notes[0]!;
  assert.equal(c.title,'测试');assert.equal(c.designer,'作者');assert.equal(c.firstMs,-250);
  assert.equal(n.source.text,'1 x');assert.equal(n.source.line,5);assert.equal(n.source.column,10);
  assert.equal(text.slice(n.source.offset,n.source.offset+n.source.text.length),n.source.text);
  assert.deepEqual(c.notes.map(n=>n.position),[1,2,3,4,5]);
  assert.deepEqual(c.notes.map(n=>n.pseudoEachOffsetMs),[0,0,0,0,1]);
  assert.deepEqual(c.notes.map(n=>n.group),[0,0,1,1,2]);
  assert.equal(n.divisionSpec!.raw,'{ 8}');
  close(c.notes[4]!.timingMs-c.notes[2]!.timingMs,1);
});

test('ratio, specified BPM, physical seconds and explicit waits keep distinct declarations',()=>{
  const cases:[string,number,number][]=[['4:1',500,500],['240#4:1',250,250],['240#0.3',250,300],
    ['0.2##4:1',200,500],['0.2##240#4:1',200,250],['0.2##0.3',200,300],['#0.3',500,300]];
  for(const [notation,wait,duration]of cases){
    const n=slide(`1-5[${notation}]`),b=n.branches[0]!;
    close(b.delayMs,wait);close(b.durationMs,duration);
    assert.equal(b.segments[0]!.durationSpec!.raw,notation);
    assert.equal(b.segments[0]!.durationSpec!.declarationBpm,120);
  }
});

test('cross-BPM Slide duration resolves at its declaration; global end beat uses the whole tempo map',()=>{
  const c=chart('(120){4}1-5[2:1],(240)2,3,4,E'),n=c.notes[0] as SlideNote,t=TimingTimeline.fromChart(c);
  close(n.endTimeMs-n.timingMs,1500);
  close(t.scoreBeatFromChartMs(n.endTimeMs),5);
  close(t.chartMsFromScoreBeat(5),n.endTimeMs);
  for(const beat of [-2,0,1,1.5,3,10])close(t.scoreBeatFromAudioMs(t.audioMsFromScoreBeat(beat,-123),-123),beat);
});

test('equivalent tempos/divisions and fixed-second commas retain the same physical chart',()=>{
  assert.deepEqual(physical('(120){8}1,2h[#0.5],3-7[0.25##0.5],E'),
    physical('(240){4}1,2h[2:1],3-7[4:2],E'));
  const a=physical('(120){#0.25}1,(240)2,3,E'),b=physical('(120){8}1,(240){4}2,3,E');
  assert.deepEqual(a,b);
});

test('whole-path duration is length weighted; per-segment duration is additive without a second wait',()=>{
  const a=prepareBranch(slide('1-5-2[2:1]').branches[0]!);
  close(a.reduce((s,p)=>s+p.durationMs,0),1000);
  close(a[0]!.durationMs/a[1]!.durationMs,a[0]!.geometry.length/a[1]!.geometry.length);
  const b=prepareBranch(slide('1-5[240#4:1]-2[0.7##4:1]').branches[0]!);
  assert.deepEqual(b.map(p=>[p.startMs,p.durationMs]),[[250,250],[500,500]]);
  assert.throws(()=>slide('1-5[4:1]-2-6[4:1]'),/mixed/);
  assert.throws(()=>slide('1w5-1[4:1]'),/Fan/);
});

test('same-head branch decorators, EX, star TAP and headless suffixes stay separate',()=>{
  const c=chart('(120){4}1bxp5b[4:1]*xq5[4:1],2-6[4:1]?,3-7[4:1]!,4-8[4:1]@,5$$,Ch,E');
  const first=c.notes[0] as SlideNote;
  assert.equal(first.isStartBreak,true);assert.equal(first.isEx,true);assert.equal(first.isSlideEach,true);
  assert.deepEqual(first.branches.map(b=>b.isBreak),[true,false]);
  assert.equal((c.notes[1] as SlideNote).isHeadless,true);
  assert.equal((c.notes[2] as SlideNote).headlessMode,'pop');
  assert.equal((c.notes[3] as SlideNote).isTapHead,true);
  assert.equal(c.notes[4]!.type,'tap');assert.equal(c.notes[4]!.isFakeRotate,true);
  close(c.notes[5]!.endTimeMs-c.notes[5]!.timingMs,1.5625);
});

test('Tap and Touch Hold keep all positions, duration, firework, break and mine fields',()=>{
  const c=chart('(150){4}E5fh[2:1]/B2f,3bh[4:1],C1h[#0.5],C2,D1m,1m-5[4:1],E');
  assert.deepEqual(c.notes.map(n=>n.position),['E5','B2',3,'C','C','D1',1]);
  assert.equal(c.notes[0]!.type,'touch-hold-start');
  assert.equal(c.notes[2]!.isBreak,true);assert.equal(c.notes[5]!.isMine,true);assert.equal(c.notes[6]!.isMine,true);
  close(c.notes[0]!.endTimeMs-c.notes[0]!.timingMs,800);
});

test('invalid temporal input fails at source rather than yielding non-finite features',()=>{
  for(const body of ['(0){4}1,','(120){0}1,','(120){#0}1,','(NaN){4}1,','(120){4}1h[-4:1],',
    '(120){4}1-5[4:-1],','(120){4}1-5[1##4:1','(120){4}1-5,E'])assert.throws(()=>chart(body));
  assert.throws(()=>parseDuration('1##4:1',120,false,{offset:0,line:1,column:1,text:'1##4:1'}),/HOLD/);
});

test('tempo queries honour duplicate declarations, negative pre-roll and second-based division changes',()=>{
  const t=new TimingTimeline(120,[{timing:4,bpm:180},{timing:4,bpm:240},{timing:8,bpm:60}],
    [{timing:4,divisor:8,spec:{raw:'{#0.25}',mode:'seconds-compat',divisor:8,seconds:.25}}]);
  close(t.msFromBeat(-2),-1000);close(t.msFromBeat(4),2000);close(t.msFromBeat(8),3000);
  assert.equal(t.bpmAtBeat(4),240);assert.equal(t.divisorAtBeat(6),4);assert.equal(t.divisorAtBeat(9),16);
  for(let beat=-2;beat<=12;beat+=.125)close(t.beatFromMs(t.msFromBeat(beat)),beat);
});

test('standard straight, v, V, zigzag, fan and circle paths follow mathematical lengths',()=>{
  close(geometry('1-5').length,9.6);close(geometry('1-3').length,4.8*Math.sqrt(2));
  close(geometry('1v3').length,9.6);close(geometry('1v1').length,9.6);
  close(geometry('1V35').length,9.6*Math.sqrt(2));close(geometry('1w5').length,9.6);
  close(geometry('1s5').length,geometry('1z5').length);
  close(geometry('1>3').length,4.8*(Math.PI/2+.001));
  close(geometry('1p5').length,9.6*Math.cos(Math.PI/8)+4.8*Math.cos(3*Math.PI/8)*Math.PI/4);
  close(geometry('1p5').length,geometry('1q5').length);
});

test('all supported paths stay finite and end within the 0.001-radian arc endpoint tolerance',()=>{
  let valid=0;
  for(let a=1;a<=8;a++)for(let b=1;b<=8;b++)for(const op of ['-','<','>','^','v','p','q','pp','qq','s','z','w']){
    let g;try{g=geometry(`${a}${op}${b}`);}catch{continue;}
    valid++;
    const first=pathPose(g,0),last=pathPose(g,1),head=buttonPoint(a),tail=buttonPoint(b);
    assert.ok(Math.hypot(first.x-head.x,first.y-head.y)<1e-8);
    assert.ok(Math.hypot(last.x-tail.x,last.y-tail.y)<.00481);
    for(let i=0;i<=32;i++)assert.ok(Object.values(pathPose(g,i/32)).every(Number.isFinite));
    assert.ok(g.areas.length>0);
  }
  // 40 chords + 48 short arcs + 128 directed arcs + 64 v paths + 256 orbit paths + 24 zigzags/fans.
  assert.equal(valid,560);
});

test('invalid endpoints and reversal vertices never become a guessed path',()=>{
  for(const code of ['1-1','1-2','1-8','1^1','1^5','1s4','1z6','1w4','1V24','2V64','3V28'])
    assert.throws(()=>geometry(code),/Unsupported/);
  for(const code of ['1V35','1V38','1V72','1V74'])assert.ok(geometry(code).length>0);
});

test('rotation preserves path length, trajectory and Touch radii',()=>{
  const a=geometry('1p5'),b=geometry('2p6'),angle=-Math.PI/4;
  close(a.length,b.length);
  for(let i=0;i<=32;i++){
    const x=pathPose(a,i/32),y=pathPose(b,i/32);
    close(x.x*Math.cos(angle)-x.y*Math.sin(angle),y.x);
    close(x.x*Math.sin(angle)+x.y*Math.cos(angle),y.y);
  }
  assert.deepEqual(touchPoint('C1'),{x:0,y:0});assert.deepEqual(touchPoint('C2'),{x:0,y:0});
  close(Math.hypot(touchPoint('B3').x,touchPoint('B3').y),2.2);
  close(Math.hypot(touchPoint('E5').x,touchPoint('E5').y),3.1);
});

test('custom point/orbit paths share the same mathematical primitives and retain repeated revolutions',()=>{
  close(geometry('1A3K5').length,geometry('1V35').length);
  close(geometry('1CK5').length,geometry('1-5').length);
  close(geometry('1P0K5').length,geometry('1p5').length);
  close(geometry('1Q0K5').length,geometry('1q5').length);
  close(geometry('1P0P0K5').length-geometry('1P0K5').length,2*Math.PI*4.8*Math.cos(3*Math.PI/8));
  assert.ok(geometry('1P0P3K5').length>geometry('1P0K5').length);
  assert.throws(()=>geometry('1P1Q5K5'),/direction/);
});
