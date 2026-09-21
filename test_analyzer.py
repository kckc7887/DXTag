#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run: python -m unittest -v test_analyzer. Synthetic assertions, not accuracy validation."""
import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from maimai_analyzer import *
from calibrate import fit, cross_validate


def src(body, **md):
    return ChartSource({"title": "unit test", **md}, {5: (body, 1)}, "utf-8-sig", "test_maidata.txt")


def parsed(body, **md):
    return parse_chart(src(body, **md), 5)


def report(body, **md):
    s = src(body, **md)
    return analyze(parse_chart(s, 5), s, 5)


class TimingTests(unittest.TestCase):
    def test_quarter_notes(self):
        self.assertEqual([n.time for n in parsed('(120){4}1,2,3,4,E').notes], [0,.5,1,1.5])
    def test_tempo_change(self):
        self.assertEqual([n.time for n in parsed('(120){4}1,(240)2,3,E').notes], [0,.5,.75])
    def test_subdivision_change(self):
        self.assertEqual([n.time for n in parsed('(120){4}1,{8}2,3,E').notes], [0,.5,.75])
    def test_first_override(self):
        self.assertAlmostEqual(parsed('(120){4}1,E', first='2', first_5='3.25').notes[0].time,3.25)
    def test_negative_first(self):
        self.assertEqual(parsed('(120){4}1,E',first='-1').notes[0].time,-1)
    def test_absolute_grid(self):
        self.assertEqual([n.time for n in parsed('(120){#0.125}1,2,(240)3,E').notes],[0,.125,.25])
    def test_fractional_grid(self):
        self.assertAlmostEqual(parsed('(120){7.5}1,2,E').notes[1].time,240/120/7.5)
    def test_pseudo_each(self):
        self.assertEqual([n.time for n in parsed('(120){4}1`2`3/4,5,E').notes],[0,.001,.002,.002,.5])
    def test_beat_ignores_first(self):
        a=parsed('(120){4}1,2,E',first='7.7');self.assertEqual([n.beat for n in a.notes],[0,1])
    def test_beat_follows_tempo(self):
        self.assertEqual([n.beat for n in parsed('(120){4}1,(240){8}2,3,E').notes],[0,1,1.5])
    def test_missing_bpm(self):
        with self.assertRaises(ParseError): parsed('{4}1,2,E')
    def test_wholebpm(self):
        self.assertEqual(parsed('{4}1,2,E',wholebpm='120').notes[1].time,.5)
    def test_missing_end_warning(self):
        self.assertTrue(parsed('(120){4}1,2,').warnings)
    def test_after_end(self):
        with self.assertRaises(ParseError): parsed('(120){4}1,E,2')
    def test_E_touch_not_end(self):
        self.assertEqual(parsed('(120){4}E1,E').notes[0].kind,'touch')
    def test_comments(self):
        self.assertEqual(len(parsed('(120){4}1, || comment\n2, // more\nE').notes),2)
    def test_negative_tempo(self):
        with self.assertRaises(ParseError): parsed('(-120){4}1,E')
    def test_zero_divider(self):
        with self.assertRaises(ParseError): parsed('(120){0}1,E')
    def test_unclosed_brackets(self):
        with self.assertRaises(ParseError): parsed('(120){4}1h[4:1,E')
    def test_nan(self):
        with self.assertRaises(ParseError): parsed('(nan){4}1,E')
    def test_no_hidden_default_bpm(self):
        s=src('{4}1,2,E');self.assertEqual(parse_chart(s,5,120).notes[1].time,.5)


class GrammarTests(unittest.TestCase):
    def test_compact_each(self):
        self.assertEqual(len(parsed('(120){4}1234,E').notes),4)
    def test_compact_decorated_each(self):
        ns=parsed('(120){4}1b5b,46x,33b,E').notes
        self.assertEqual([(n.position,n.is_break,n.ex) for n in ns],[('1',True,False),('5',True,False),('4',False,False),('6',False,True),('3',False,False),('3',True,False)])
    def test_implicit_hold_duration(self):
        n=parsed('(120){4}4x[4:1],E').notes[0]
        self.assertEqual(n.kind,'hold');self.assertTrue(n.ex);self.assertEqual(n.duration,.5)
    def test_star_still_not_implicit_hold(self):
        ns=parsed('(120){4}1-5[4:1],E').notes
        self.assertEqual([n.kind for n in ns],['tap','slide'])
    def test_star_route_break_after_star(self):
        ns=parsed('(120){4}4bpp4[4:1]*bqq4[4:1],E').notes
        slides=[n for n in ns if n.kind=='slide']
        self.assertEqual(len(slides),2)
        self.assertEqual([s.segments[0].shape for s in slides],['pp','qq'])
    def test_normal_hold(self):
        self.assertEqual(parsed('(120){4}1h[4:3],E').notes[0].duration,1.5)
    def test_absolute_hold(self):
        self.assertEqual(parsed('(120){4}1h[#1.25],E').notes[0].duration,1.25)
    def test_hold_local_bpm(self):
        self.assertEqual(parsed('(120){4}1h[240#4:3],E').notes[0].duration,.75)
    def test_short_hold(self):
        self.assertAlmostEqual(parsed('(120){4}1h,E').notes[0].duration,240/120/1280)
    def test_hold_modifier_permutations(self):
        for t in ('1bhx[4:1]','1hbx[4:1]','1xhb[4:1]'):
            n=parsed('(120){4}'+t+',E').notes[0];self.assertTrue(n.is_break and n.ex)
    def test_touch(self):
        self.assertEqual([n.kind for n in parsed('(120){4}B1,C,D3,E4,A5,E').notes],['touch']*5)
    def test_touch_center_alias(self):
        self.assertEqual([n.position for n in parsed('(120){4}C,C1,C2,E').notes],['C']*3)
    def test_touch_hold_firework(self):
        n=parsed('(120){4}Chf[4:3],E').notes[0];self.assertEqual((n.kind,n.duration),('touch_hold',1.5))
    def test_basic_slide(self):
        ns=parsed('(120){4}1-5[4:1],E').notes
        self.assertEqual(len(ns),2);self.assertEqual((ns[1].time,ns[1].duration),(.5,.5))
    def test_slide_local_bpm(self):
        n=parsed('(120){4}1-5[240#4:1],E').notes[-1];self.assertEqual((n.time,n.duration),(.25,.25))
    def test_slide_bpm_seconds(self):
        n=parsed('(120){4}1-5[240#1.2],E').notes[-1];self.assertEqual((n.time,n.duration),(.25,1.2))
    def test_slide_wait_seconds(self):
        n=parsed('(120){4}1-5[.2##1.2],E').notes[-1];self.assertEqual((n.time,n.duration),(.2,1.2))
    def test_slide_wait_beats(self):
        n=parsed('(120){4}1-5[.2##4:3],E').notes[-1];self.assertEqual((n.time,n.duration),(.2,1.5))
    def test_slide_all_timing(self):
        n=parsed('(120){4}1-5[.2##240#4:3],E').notes[-1];self.assertEqual((n.time,n.duration),(.2,.75))
    def test_headless(self):
        for mod in ('?','!'):
            ns=parsed('(120){4}1'+mod+'-5[4:1],E').notes;self.assertEqual(len(ns),1);self.assertTrue(ns[0].headless)
    def test_multiple_slide_one_head(self):
        ns=parsed('(120){4}1-5[4:1]*-6[4:2],E').notes
        self.assertEqual(len(ns),3);self.assertEqual(sum(n.kind=='tap' for n in ns),1)
    def test_chain_one_judged_slide(self):
        ns=parsed('(120){4}1-4q7-2[1:2],E').notes
        self.assertEqual(len(ns),2);self.assertEqual(len(ns[-1].segments),3)
        self.assertAlmostEqual(sum(s.duration for s in ns[-1].segments),4)
    def test_chain_per_segment(self):
        n=parsed('(120){4}1-4[4:1]q7[4:2]-2[4:1],E').notes[-1]
        self.assertEqual(n.time,.5);self.assertEqual(n.duration,2)
        self.assertEqual([s.duration for s in n.segments],[.5,1,.5])
    def test_incomplete_segment_timing(self):
        with self.assertRaises(ParseError):parsed('(120){4}1-4[4:1]q7-2[4:1],E')
    def test_v_shape(self):
        s=parsed('(120){4}1V35[4:1],E').notes[-1].segments[0]
        self.assertEqual((s.start,s.via,s.end),(1,3,5))
    def test_wifi_is_one_slide(self):
        self.assertEqual(len(parsed('(120){4}1w5[4:1],E').notes),2)
    def test_all_shapes(self):
        for shape in ('-','<','>','^','v','p','q','pp','qq','s','z','w'):
            self.assertEqual(parsed('(120){4}1'+shape+'5[4:1],E').notes[-1].segments[0].shape,shape)
    def test_break_head_and_tail_separate(self):
        a=parsed('(120){4}1b-5[4:1],E').notes;b=parsed('(120){4}1-5[4:1]b,E').notes
        self.assertEqual([n.is_break for n in a],[True,False]);self.assertEqual([n.is_break for n in b],[False,True])
    def test_shape_modifiers(self):
        self.assertFalse(parsed('(120){4}1@-5[4:1],E').notes[0].is_star)
        self.assertTrue(parsed('(120){4}1$$,E').notes[0].is_star)
    def test_unknown_token_fails(self):
        with self.assertRaises(ParseError):parsed('(120){4}1,garbage,E')
    def test_lenient_disables_prediction(self):
        s=src('(120){4}1,garbage,2,E');r=analyze(parse_chart(s,5,strict=False),s,5)
        self.assertIsNone(r['prediction']['estimated_level']);self.assertEqual(len(r['skipped_tokens']),1)
    def test_source_line(self):
        ns=parsed('(120){4}\n1,\n2,\nE').notes;self.assertEqual([n.line for n in ns],[2,3])
    def test_zero_or_negative_duration(self):
        self.assertEqual(duration_value('4:0',120),0)
        with self.assertRaises(ParseError):duration_value('4:-1',120)


class AnalysisTests(unittest.TestCase):
    def test_peak_half_open_window(self):
        self.assertEqual(peak_window([0,.5,1,1.5],[1]*4,1)[0],2)
    def test_simultaneous_peak(self):
        self.assertEqual(peak_window([0,0,0],[1]*3,1)[0],3)
    def test_long_hold_duration(self):
        r=report('(120){4}1h[#10],E');self.assertEqual(r['statistics']['effective_seconds'],10)
    def test_raw_counts(self):
        r=report('(120){4}1-5[4:1]*-6[4:1],Ch[4:2],E');self.assertEqual(r['statistics']['judged_objects'],4)
    def test_trill(self):
        r=report('(180){16}1,5,1,5,1,5,1,5,E');self.assertTrue(any(p['label']=='交互' for p in r['patterns']))
        self.assertEqual(sum(p['label']=='交互' for p in r['patterns']),1)
    def test_jack(self):
        self.assertTrue(any(p['label']=='纵连' for p in report('(180){16}1,1,1,1,E')['patterns']))
    def test_sweep_spin(self):
        r=report('(180){16}1,2,3,4,5,6,7,8,1,E');self.assertTrue(any(p['label']=='转圈' for p in r['patterns']))
    def test_no_slow_jack(self):
        self.assertFalse(any(p['label']=='纵连' for p in report('(60){4}1,1,1,1,E')['patterns']))
    def test_no_movement_for_two_stationary_hands(self):
        r=report('(180){16}1,5,1,5,1,5,1,5,E');self.assertEqual(r['model_features']['travel_pressure'],0)
    def test_each_order_invariant(self):
        a=report('(180){8}1/5,2/6,3/7,4/8,E');b=report('(180){8}5/1,6/2,7/3,8/4,E')
        self.assertEqual(a['radar'],b['radar']);self.assertEqual(a['prediction'],b['prediction'])
    def test_offset_invariant(self):
        body='(180){8}1,5,2,6,3,7,4,8,E';self.assertEqual(report(body,first='0')['radar'],report(body,first='12.25')['radar'])
    def test_declared_not_feature(self):
        body='(180){8}1,5,2,6,3,7,4,8,E'
        a=report(body,lv_5='2.0');b=report(body,lv_5='14.9')
        self.assertEqual(a['prediction'],b['prediction'])
    def test_display_plus_not_constant(self):
        self.assertIsNone(report('(120){4}1,E',lv_5='13+')['declared_constant'])
    def test_integer_not_constant(self):
        self.assertIsNone(report('(120){4}1,E',lv_5='13')['declared_constant'])
    def test_prediction_range(self):
        r=report('(1000){64}'+','.join(['1']*120)+',E');self.assertTrue(1<=r['prediction']['estimated_level']<=15.5)
    def test_radar_bounds(self):
        for axis in report('(180){8}1,5,2,6,3,7,4,8,E')['radar']:self.assertTrue(0<=axis['score']<=100)
    def test_multi_press_disables_prediction(self):
        self.assertIsNone(report('(120){4}123,E')['prediction']['estimated_level'])
    def test_empty_chart(self):
        with self.assertRaises(ValueError):report('(120){4},,,E')
    def test_json_has_no_nan(self):
        json.dumps(report('(120){4}1,E'),allow_nan=False)
    def test_contributions_sum(self):
        r=report('(180){8}1,5,2,6,3,7,4,8,E');p=r['prediction']
        self.assertAlmostEqual(sum(c['contribution'] for c in p['contributions']),p['unclipped_level'],places=4)
    def test_fingerprint_ignores_title_offset_level(self):
        body='(120){4}1,2,E';self.assertEqual(parsed(body,first='1',lv_5='1').fingerprint,parsed(body,first='8',lv_5='15').fingerprint)
    def test_ex_preserves_physical_count(self):
        a=report('(120){8}1,2,3,4,E');b=report('(120){8}1x,2x,3x,4x,E')
        self.assertEqual(a['statistics']['mean_onset_nps'],b['statistics']['mean_onset_nps'])
    def test_concurrency_end_before_start(self):
        ns=parsed('(120){4}1-5[0##0.5],2-6[0##0.5],E').notes
        _,overlap,peak=interval_metrics([n for n in ns if n.kind=='slide']);self.assertEqual(overlap,0);self.assertEqual(peak,1)
    def test_faster_increases_prediction(self):
        seq='{16}'+','.join(['1','5','2','6','3','7','4','8']*20)+',E'
        self.assertGreater(report('(240)'+seq)['prediction']['estimated_level'],report('(120)'+seq)['prediction']['estimated_level'])


class IOTests(unittest.TestCase):
    def test_load_metadata_multi_difficulty(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'maidata.txt';p.write_text('&title=曲名\n&inote_4=(120){4}1,E\n&inote_5=(120){4}2,E',encoding='utf-8-sig')
            s=load_source(p);self.assertEqual(set(s.charts),{4,5});self.assertEqual(s.metadata['title'],'曲名')
    def test_utf16(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.txt';p.write_text('(120){4}1,E',encoding='utf-16');self.assertEqual(load_source(p).encoding,'utf-16')
    def test_duplicate_slot(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.txt';p.write_text('&inote_5=(120){4}1,E\n&inote_5=(120){4}2,E',encoding='utf-8')
            with self.assertRaises(ParseError):load_source(p)
    def test_svg_wellformed(self):
        r=report('(120){4}1,2,E');ET.fromstring(radar_svg(r));ET.fromstring(density_svg(r))
    def test_html_escaping(self):
        r=report('(120){4}1,2,E');r['title']='<script>alert(1)</script>';h=report_html(r,[])
        self.assertNotIn('<script>alert',h);self.assertIn('&lt;script&gt;',h)
    def test_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            write_report(report('(120){4}1,2,E'),Path(d),[])
            self.assertTrue(all((Path(d)/p).is_file() for p in ['report.html','report.json','radar.svg','density.svg','patterns.csv']))
    def test_empty_slot_skipped_by_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'maidata.txt';p.write_text('&inote_4=(120){4}E\n&inote_5=(120){4}1,2,E',encoding='utf-8')
            self.assertEqual(main([str(p),'--out',str(Path(d)/'out')]),0)
            self.assertTrue((Path(d)/'out/difficulty_5/report.html').is_file())
    def test_explicit_empty_slot_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'maidata.txt';p.write_text('&inote_5=(120){4}E',encoding='utf-8')
            self.assertEqual(main([str(p),'--difficulty','5','--out',str(Path(d)/'out')]),2)
    def test_demo_all_difficulties(self):
        s=load_source(Path(__file__).parent/'examples'/'maidata.txt')
        for d in s.charts:
            p=parse_chart(s,d);r=analyze(p,s,d)
            self.assertFalse(p.skipped);self.assertIsNotNone(r['prediction']['estimated_level'])


class ModelTests(unittest.TestCase):
    def test_ridge_synthetic_linear(self):
        samples=[{'features':{key:(i/10 if j==0 else 0) for j,key in enumerate(MODEL_FEATURES)},'level':5+i/10} for i in range(40)]
        model=fit(samples,.001);pred,_=predict_model(model,samples[20]['features']);self.assertAlmostEqual(pred,7,places=3)
    def test_bad_model(self):
        with self.assertRaises(ValueError):predict_model({'format':'not valid'},{})
    def test_nonobject_model_rejected(self):
        with self.assertRaises(ValueError):predict_model([],{})
    def test_zero_scale_rejected(self):
        sample={'features':dict.fromkeys(MODEL_FEATURES,0),'level':5};m=fit([sample]*5,10);m['scales'][0]=0
        with self.assertRaises(ValueError):predict_model(m,sample['features'])
    def test_group_cv_integrity(self):
        samples=[]
        for i in range(40):samples.append({'features':{key:(i/10 if j==0 else 0) for j,key in enumerate(MODEL_FEATURES)},'level':5+i/10,'group':str(i//2),'path':str(i),'difficulty':5,'heuristic':6})
        metrics,rows=cross_validate(samples,10)
        self.assertEqual(len(rows),40);self.assertTrue(math.isfinite(metrics['mae']))
        for group in set(r['group'] for r in rows):self.assertEqual(len({r['fold'] for r in rows if r['group']==group}),1)


if __name__=='__main__': unittest.main()
