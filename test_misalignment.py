#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Regression for delayed-head structures. Not a benchmark of difficulty accuracy."""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
import maimai_analyzer as a
from calibrate import fit


def source(body: str, **metadata: str) -> a.ChartSource:
    return a.ChartSource({'title': 'generic structural test', **metadata}, {5: (body, 1)}, 'utf-8-sig', 'synthetic.txt')


def result(body: str, **metadata: str) -> dict:
    s = source(body, **metadata)
    return a.analyze(a.parse_chart(s, 5), s, 5)


# A generic pair of alternating origins; not matched by song name or ID.
MOTIF = '1/8-4[8:1],7,8/1-5[8:1],2,1/8-4[8:1],7,1/8,,'


class NegativeControlTests(unittest.TestCase):
    def test_plain_taps_not_misalignment(self):
        r = result('(120){8}1,2,3,4,5,6,7,8,E')
        self.assertEqual(r['misalignment']['score'], 0)
        self.assertEqual(r['misalignment']['summary']['matched_unique_heads'], 0)

    def test_plain_slide_not_misalignment(self):
        r = result('(120){8}1-5[8:1],,,,E')
        self.assertEqual(r['misalignment']['score'], 0)

    def test_different_key_at_launch_only_is_not_wait_interleave(self):
        r = result('(120){8}1-5[8:1],,3,,E')
        self.assertEqual(r['misalignment']['score'], 0)

    def test_simple_continuous_stars_not_misalignment(self):
        r = result('(120){4}1-5[8:1],2-6[8:1],3-7[8:1],4-8[8:1],,E')
        self.assertEqual(r['misalignment']['score'], 0)
        self.assertEqual(r['misalignment']['summary']['continuous_runs'], 0)

    def test_tracing_foreign_attacks_are_parallel_not_wait_interleave(self):
        r = result('(120){8}1-5[2:1],,,2,3,,,E')
        self.assertEqual(r['misalignment']['score'], 0)
        self.assertTrue(any(p['label'] == '滑行期间异键并行候选' for p in r['patterns']))

    def test_endpoint_attack_does_not_become_launch_attack(self):
        r = result('(120){8}1-5[8:1],,,1,E')
        self.assertEqual(r['misalignment']['score'], 0)

    def test_head_simultaneous_attack_is_not_waiting_attack(self):
        r = result('(120){8}1-5[8:1]/2,,,,E')
        self.assertEqual(r['misalignment']['summary']['waiting_foreign_slides'], 0)

    def test_same_key_hold_at_launch_is_not_tap_slide(self):
        r = result('(120){8}1-5[8:1],,1h[4:1],,E')
        self.assertEqual(r['misalignment']['summary']['same_origin_launch_slides'], 0)
        self.assertEqual(r['misalignment']['score'], 0)

    def test_headless_slide_does_not_invent_a_head(self):
        r = result('(120){8}1?-5[8:1],2,1,E')
        self.assertEqual(r['misalignment']['summary']['eligible_slides'], 0)
        self.assertEqual(r['misalignment']['score'], 0)

    def test_zero_wait_does_not_invent_waiting_interval(self):
        r = result('(120){8}1-5[0##1],2,1,E')
        self.assertEqual(r['misalignment']['summary']['eligible_slides'], 0)

    def test_zero_duration_route_excluded(self):
        r = result('(120){8}1-5[4:0],2,1,E')
        self.assertEqual(r['misalignment']['summary']['eligible_slides'], 0)

    def test_same_key_wait_is_not_foreign_wait(self):
        r = result('(120){8}1-5[8:1],1,,,E')
        m = r['misalignment']
        self.assertEqual(m['summary']['waiting_foreign_slides'], 0)
        self.assertEqual(m['summary']['same_origin_waiting_slides'], 1)
        self.assertEqual(m['summary']['umiyuri_structure_slides'], 0)
        self.assertTrue(any(p['label'] == '同位拍拍划' for p in r['patterns']))


class PositiveStructureTests(unittest.TestCase):
    def test_single_waiting_foreign_attack_is_enough(self):
        r = result('(120){8}1-5[8:1],2,,,E')
        self.assertEqual(r['misalignment']['summary']['waiting_foreign_slides'], 1)
        self.assertGreater(r['misalignment']['score'], 0)

    def test_same_origin_tap_at_launch_detected(self):
        r = result('(120){8}1-5[8:1],,1,,E')
        self.assertEqual(r['misalignment']['summary']['same_origin_launch_slides'], 1)

    def test_classic_chord_wait_chord_motif(self):
        r = result('(120){8}1/8-4[8:1],7,8/1,,E')
        m = r['misalignment']
        self.assertEqual(m['summary']['umiyuri_structure_slides'], 1)
        u = m['slides'][0]
        self.assertEqual((u['head_time'], u['slide_start'], u['slide_end']), (0, .5, .75))
        self.assertEqual(u['waiting_counts_by_position'], {'7': 1})
        self.assertEqual(u['launch_positions'], ['1', '8'])

    def test_umiyuri_subset_requires_chords(self):
        r = result('(120){8}8-4[8:1],7,8,,E')
        self.assertEqual(r['misalignment']['summary']['umiyuri_structure_slides'], 0)
        self.assertEqual(r['misalignment']['summary']['waiting_foreign_slides'], 1)

    def test_foreign_hold_onset_during_wait_is_evidence(self):
        r = result('(120){8}1-5[8:1],2h[8:1],,,E')
        self.assertEqual(r['misalignment']['summary']['waiting_foreign_slides'], 1)

    def test_three_head_steps_make_run(self):
        r = result('(120){8}' + MOTIF + 'E')
        m = r['misalignment']
        self.assertEqual(m['summary']['continuous_runs'], 1)
        self.assertEqual(m['summary']['longest_run_head_steps'], 3)
        self.assertTrue(m['runs'][0]['alternating_two_origins'])

    def test_two_head_steps_not_run(self):
        r = result('(120){8}1/8-4[8:1],7,8/1-5[8:1],2,1/8,,E')
        self.assertEqual(r['misalignment']['summary']['continuous_runs'], 0)

    def test_rest_splits_runs(self):
        r = result('(120){8}' + MOTIF + ',,,,' + MOTIF + 'E')
        self.assertEqual(r['misalignment']['summary']['continuous_runs'], 2)

    def test_noninterleaved_head_breaks_run(self):
        # All heads one beat apart; the third has no waiting foreign attack.
        r = result('(120){8}1-5[8:1],2,3-7[8:1],4,5-1[8:1],,6-2[8:1],7,8-4[8:1],1,,,E')
        self.assertEqual(r['misalignment']['summary']['continuous_runs'], 0)

    def test_multiple_routes_one_head_do_not_inflate_score(self):
        s1 = source('(120){8}1-5[8:1],2,,,E')
        s2 = source('(120){8}1-5[8:1]*-6[8:1]*-7[8:1],2,,,E')
        p1, p2 = a.parse_chart(s1, 5), a.parse_chart(s2, 5)
        get = lambda p: a.detect_misalignment([n for n in p.notes if n.kind == 'slide'], [n for n in p.notes if n.outer], 10)
        x, y = get(p1), get(p2)
        self.assertEqual(x['score'], y['score'])
        self.assertEqual(y['summary']['waiting_foreign_slides'], 3)
        self.assertEqual(y['summary']['unique_heads'], 1)
        self.assertEqual(y['summary']['continuous_runs'], 0)

    def test_simultaneous_multiple_heads_not_three_steps(self):
        r = result('(120){8}1-5[8:1]/2-6[8:1],3,,,E')
        self.assertEqual(r['misalignment']['summary']['continuous_runs'], 0)
        self.assertEqual(r['misalignment']['summary']['waiting_foreign_slides'], 2)


class InvarianceAndTimingTests(unittest.TestCase):
    def test_title_artist_and_level_are_not_detection_inputs(self):
        body = '(120){8}' + MOTIF + 'E'
        x = result(body, title='ウミユリ海底譚', artist='n-buna', lv_5='13')
        y = result(body, title='unrelated', artist='unrelated', lv_5='2.0')
        self.assertEqual(x['misalignment'], y['misalignment'])
        self.assertEqual(x['prediction'], y['prediction'])

    def test_first_offset_does_not_change_score_or_counts(self):
        body = '(120){8}' + MOTIF + 'E'
        x, y = result(body)['misalignment'], result(body, first='123.456')['misalignment']
        self.assertEqual(x['summary'], y['summary'])
        self.assertEqual(x['score'], y['score'])
        self.assertAlmostEqual(y['slides'][0]['head_time'] - x['slides'][0]['head_time'], 123.456)

    def test_absolute_beat_phase_not_a_feature(self):
        x = result('(120){8}' + MOTIF + 'E')['misalignment']
        y = result('(120){8},' + MOTIF + 'E')['misalignment']
        self.assertEqual(x['summary'], y['summary'])
        self.assertEqual(x['score'], y['score'])

    def test_bpm_change_preserves_structure(self):
        summaries = [result(f'({bpm}){{8}}' + MOTIF + 'E')['misalignment']['summary'] for bpm in (60, 120, 240, 360)]
        self.assertTrue(all(x == summaries[0] for x in summaries))

    def test_explicit_wait_uses_real_timing(self):
        r = result('(120){#0.2}1/8-4[.4##.2],7,8/1,,E')
        u = r['misalignment']['slides'][0]
        self.assertEqual((u['head_time'], u['slide_start'], u['slide_end']), (0, .4, .6))
        self.assertTrue(u['umiyuri_structure'])

    def test_local_slide_bpm_uses_real_timing(self):
        r = result('(120){16}1/8-4[240#8:1],7,8/1,,E')
        u = r['misalignment']['slides'][0]
        self.assertEqual((u['head_time'], u['slide_start'], u['slide_end']), (0, .25, .375))
        self.assertTrue(u['umiyuri_structure'])

    def test_tempo_change_after_head_does_not_recompute_wait(self):
        r = result('(120){8}1/8-4[8:1],(240){4}7,8/1,,E')
        self.assertEqual(r['misalignment']['slides'][0]['slide_start'], .5)
        self.assertTrue(r['misalignment']['slides'][0]['umiyuri_structure'])

    def test_launch_near_miss_not_matched(self):
        r = result('(120){#0.25}1-5[8:1],2,{#0.03},1,E')
        self.assertFalse(r['misalignment']['slides'][0]['same_origin_launch'])

    def test_pseudo_each_one_millisecond_is_same_launch(self):
        r = result('(120){8}1/8-4[8:1],7,1`8,,E')
        self.assertTrue(r['misalignment']['slides'][0]['same_origin_launch'])

    def test_order_of_each_tokens_irrelevant(self):
        x = result('(120){8}1/8-4[8:1],7,1/8,,E')['misalignment']
        y = result('(120){8}8-4[8:1]/1,7,8/1,,E')['misalignment']
        self.assertEqual(x['summary'], y['summary'])
        self.assertEqual(x['score'], y['score'])

    def test_rotation_and_mirror_preserve_misalignment(self):
        s = source('(120){8}' + MOTIF + 'E')
        p = a.parse_chart(s, 5)
        baseline = a.analyze(p, s, 5)['misalignment']
        for transform in (lambda i: (i + 2) % 8 + 1, lambda i: 9 - i):
            q = copy.deepcopy(p)
            for n in q.notes:
                if n.position.isdigit(): n.position = str(transform(int(n.position)))
                for seg in n.segments:
                    seg.start, seg.end = transform(seg.start), transform(seg.end)
                    if seg.via is not None: seg.via = transform(seg.via)
            m = a.analyze(q, s, 5)['misalignment']
            self.assertEqual(m['summary'], baseline['summary'])
            self.assertEqual(m['score'], baseline['score'])

    def test_tap_shaped_slide_head_still_has_delayed_structure(self):
        r = result('(120){8}1/8@-4[8:1],7,8/1,,E')
        self.assertTrue(r['misalignment']['slides'][0]['umiyuri_structure'])

    def test_score_head_dedup_does_not_hide_raw_route_evidence(self):
        r = result('(120){8}1-5[8:1]*-6[8:1],2,,,E')
        self.assertEqual(len(r['misalignment']['slides']), 2)
        self.assertEqual(r['misalignment']['summary']['matched_unique_heads'], 1)

    def test_feature_vector_contains_corrected_detection(self):
        r = result('(120){8}' + MOTIF + 'E')
        for key in ('waiting_interleave_fraction', 'same_origin_launch_fraction', 'misalign_run_fraction'):
            self.assertIn(key, a.MODEL_FEATURES)
            self.assertGreater(r['model_features'][key], 0)

    def test_old_model_is_rejected_not_silently_used(self):
        sample = {'features': dict.fromkeys(a.MODEL_FEATURES, 0), 'level': 5}
        model = fit([sample] * 5, 10)
        model['analyzer_version'] = '1.0.0'
        with self.assertRaises(ValueError): a.predict_model(model, sample['features'])


class UserChartRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = a.load_source(Path(__file__).parent / 'regression' / 'umiyuri_user_maidata.txt')
        cls.p = a.parse_chart(cls.s, 5)
        cls.r = a.analyze(cls.p, cls.s, 5)

    def test_759_objects_76_slides_unchanged(self):
        self.assertEqual(self.r['statistics']['judged_objects'], 759)
        self.assertEqual(self.r['statistics']['types']['slide'], 76)
        self.assertFalse(self.p.skipped)

    def test_all_five_difficulties_parse(self):
        expected = {1: 76, 2: 180, 3: 380, 4: 463, 5: 759}
        for difficulty, count in expected.items():
            p = a.parse_chart(self.s, difficulty)
            self.assertEqual(len(p.notes), count)
            self.assertFalse(p.skipped)

    def test_known_305_line_semantics(self):
        u = next(x for x in self.r['misalignment']['slides'] if x['head_time'] == 62.25)
        self.assertEqual(u['line'], 305)
        self.assertEqual(u['token'], '8-4[8:1]')
        self.assertEqual((u['slide_start'], u['slide_end']), (62.75, 63.0))
        self.assertEqual(u['waiting_note_samples'][0]['time'], 62.5)
        self.assertEqual(u['waiting_counts_by_position'], {'7': 1})
        self.assertEqual(u['launch_positions'], ['1', '8'])
        self.assertTrue(u['umiyuri_structure'])

    def test_later_chorus_blocks_are_detected(self):
        for line in (305, 309, 327, 329, 331, 335, 336, 337):
            units = [u for u in self.r['misalignment']['slides'] if u['line'] == line]
            self.assertTrue(units, line)
            self.assertTrue(all(u['umiyuri_structure'] for u in units), line)

    def test_counts_are_reproducible(self):
        m = self.r['misalignment']['summary']
        self.assertEqual(m['waiting_foreign_slides'], 53)
        self.assertEqual(m['same_origin_launch_slides'], 46)
        self.assertEqual(m['umiyuri_structure_slides'], 46)
        self.assertEqual(m['continuous_runs'], 6)
        self.assertEqual(m['longest_run_head_steps'], 12)

    def test_fixed_axis_and_untrained_prediction(self):
        self.assertEqual(self.r['radar'][8]['score'], 71.3)
        self.assertFalse(self.r['prediction']['calibrated'])
        self.assertIsNone(self.r['prediction']['error_estimate'])
        self.assertEqual(self.r['prediction']['estimated_level'], 13.1)
        self.assertIsNone(self.r['declared_constant'])

    def test_change_title_and_level_does_not_change_real_chart_result(self):
        s = copy.deepcopy(self.s)
        s.metadata.update(title='some other song', artist='unknown', lv_5='4.1')
        r = a.analyze(a.parse_chart(s, 5), s, 5)
        self.assertEqual(r['radar'], self.r['radar'])
        self.assertEqual(r['prediction'], self.r['prediction'])

    def test_old_wrong_label_removed(self):
        self.assertFalse(any('滑条期间异键 / 错位' in p['label'] for p in self.r['patterns']))

    def test_all_evidence_is_before_launch_or_at_launch(self):
        for u in self.r['misalignment']['slides']:
            for n in u['waiting_note_samples']:
                self.assertLess(u['head_time'], n['time'])
                self.assertLess(n['time'], u['slide_start'])
            for n in u['launch_note_samples']:
                self.assertLessEqual(abs(n['time'] - u['slide_start']), u['tolerance_seconds'] + 1e-6)

    def test_pattern_csv_contains_real_source_line(self):
        with tempfile.TemporaryDirectory() as d:
            a.write_report(self.r, Path(d), [])
            csv = (Path(d) / 'patterns.csv').read_text(encoding='utf-8-sig')
            self.assertIn('海底捞型错位', csv)
            self.assertIn('62.25', csv)
            self.assertIn('305', csv)
            json.dumps(self.r, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
