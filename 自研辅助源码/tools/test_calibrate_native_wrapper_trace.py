#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
import tempfile
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name('calibrate_native_wrapper_trace.py')
spec = importlib.util.spec_from_file_location('calibrate_native_wrapper_trace', MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class CalibrateNativeWrapperTraceTest(unittest.TestCase):
    def test_summarizes_multiple_wrapper_captures_without_raw_values_by_default(self):
        text = '''
[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => KEY
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"aa","rawBody":"LXKEYaaLB"}
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"bb","rawBody":"LXKEYbbLB"}
'''
        report = mod.calibrate(text)
        self.assertEqual(report['summary']['captureCount'], 2)
        self.assertEqual(report['summary']['uniqueGameHexCount'], 2)
        self.assertTrue(report['summary']['prefixLength']['stable'])
        self.assertTrue(report['summary']['suffixLength']['stable'])
        self.assertTrue(report['summary']['nativeWrapperFieldAudit']['readyForDryRunWrapperPlan'])
        self.assertEqual('derivedNativeWrapperLx', report['summary']['nativeWrapperFieldAudit']['selectedLxSource'])
        self.assertEqual('recoveredNativeKey', report['summary']['nativeWrapperFieldAudit']['selectedKeySource'])
        self.assertFalse(report['summary']['networkSendAllowed'])
        self.assertFalse(report['summary']['actionSendReady'])
        self.assertEqual(report['summary']['readinessLevel'], 'dry_run_only')
        self.assertIn('prefix_ends_with_key', report['summary']['splitStatuses'])
        self.assertFalse(report['summary']['brushYellowWrapperCoverage']['complete'])
        self.assertEqual(['unknown_or_unmapped'], report['captures'][0]['opcodeMarkers'])
        self.assertNotIn('rawBody', report['captures'][0])
        self.assertIn('rawBodySha256', report['captures'][0])

    def test_tracks_brush_yellow_wrapper_opcode_coverage(self):
        text = '''
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"0000000000000000000a1520030010000000000000007","rawBody":"LXKEY0000000000000000000a1520030010000000000000007LB","lx":"LX","lb":"LB"}
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"000000000000000000151522030010000000000000007","rawBody":"LXKEY000000000000000000151522030010000000000000007LB","lx":"LX","lb":"LB"}
'''
        report = mod.calibrate(text)

        self.assertTrue(report['summary']['brushYellowWrapperCoverage']['complete'])
        self.assertEqual(1, report['summary']['brushYellowWrapperCoverage']['prepare1520030'])
        self.assertEqual(1, report['summary']['brushYellowWrapperCoverage']['dispatch1522030'])
        self.assertTrue(report['summary']['brushYellowWrapperDetails']['complete'])
        self.assertTrue(report['summary']['brushYellowWrapperDetails']['splitProvenForBothStages'])
        self.assertEqual(1, report['summary']['brushYellowWrapperDetails']['prepare1520030']['count'])
        self.assertEqual(1, report['summary']['brushYellowWrapperDetails']['dispatch1522030']['count'])
        self.assertTrue(report['summary']['brushYellowWrapperDetails']['prepare1520030']['splitProven'])
        self.assertTrue(report['summary']['brushYellowWrapperDetails']['dispatch1522030']['splitProven'])
        self.assertIn('brush_yellow_prepare_1520030', report['captures'][0]['opcodeMarkers'])
        self.assertIn('brush_yellow_dispatch_1522030', report['captures'][1]['opcodeMarkers'])
        self.assertEqual('brush_yellow_prepare_1520030', report['captures'][0]['primaryOpcodeMarker'])
        self.assertGreater(report['captures'][0]['gameHexLength'], 0)

    def test_tracks_resource_point_and_withdraw_wrapper_details_as_advisory_evidence(self):
        text = '''
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"000000000000000000121520010100000000000000070000000000000101","rawBody":"LXKEY000000000000000000121520010100000000000000070000000000000101LB","lx":"LX","lb":"LB"}
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"0000000000000000001d1522010100000000000000070000000000000101ffffffffffffffff000000","rawBody":"LXKEY0000000000000000001d1522010100000000000000070000000000000101ffffffffffffffff000000LB","lx":"LX","lb":"LB"}
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"0000000000000000000a152601010000000000000007","rawBody":"LXKEY0000000000000000000a152601010000000000000007LB","lx":"LX","lb":"LB"}
'''
        report = mod.calibrate(text)
        details = report['summary']['remainingActionWrapperDetails']

        self.assertTrue(details['resourcePoint']['complete'])
        self.assertTrue(details['resourcePoint']['splitProvenForBothStages'])
        self.assertEqual(1, details['resourcePoint']['prepare1520010']['count'])
        self.assertEqual(1, details['resourcePoint']['dispatch1522010']['count'])
        self.assertTrue(details['withdrawDefense']['complete'])
        self.assertTrue(details['withdrawDefense']['splitProven'])
        self.assertEqual(1, details['withdrawDefense']['withdraw0a15260101']['count'])
        self.assertFalse(details['networkSendAllowed'])
        self.assertIn('resource_point_prepare_1520010', report['captures'][0]['opcodeMarkers'])
        self.assertIn('withdraw_defense_0a15260101', report['captures'][2]['opcodeMarkers'])

    def test_can_include_values_for_isolated_calibration(self):
        text = '[native-wrapper-json] {"gameHex":"aa","rawBody":"LXKEYaaLB","lx":"LX","lb":"LB"}'
        report = mod.calibrate(text, include_values=True)
        self.assertEqual(report['captures'][0]['prefix'], 'LXKEY')
        self.assertEqual(report['captures'][0]['suffix'], 'LB')
        self.assertEqual(report['captures'][0]['derivedKey'], 'KEY')

    def test_markdown_report_and_cli_output(self):
        text = """
[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => KEY
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"aa","rawBody":"LXKEYaaLB","lx":"LX","lb":"LB"}
[native-wrapper-json] {"source":"body","threadId":"1","gameHex":"bb","rawBody":"LXKEYbbLB","lx":"LX","lb":"LB"}
"""
        report = mod.calibrate(text)
        markdown = mod.to_markdown(report)
        self.assertIn('Native Wrapper 校准报告', markdown)
        self.assertIn('actionSendReady: false', markdown)
        self.assertIn('Native Wrapper Field Audit', markdown)
        self.assertIn('Brush Yellow Wrapper Details', markdown)
        self.assertIn('Remaining Action Wrapper Details', markdown)
        self.assertIn('ChannelExtra Candidate', markdown)
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / 'native.log'
            out = pathlib.Path(td) / 'native.json'
            md = pathlib.Path(td) / 'native.md'
            src.write_text(text, encoding='utf-8')
            subprocess.check_call([sys.executable, str(MODULE_PATH), str(src), '--out', str(out), '--markdown-out', str(md)])
            data = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(data['summary']['captureCount'], 2)
            self.assertIn('readinessLevel: dry_run_only', md.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
