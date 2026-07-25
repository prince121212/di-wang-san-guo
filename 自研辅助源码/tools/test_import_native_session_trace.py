#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name('import_native_session_trace.py')
spec = importlib.util.spec_from_file_location('import_native_session_trace', MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ImportNativeSessionTraceTest(unittest.TestCase):
    def test_imports_java_native_returns_and_explicit_wrapper_fields(self):
        text = '''
[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getSession => sess123
[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => key123
[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getPassCode => pass123
[manual] lx=lxVALUE lb=lbVALUE
'''
        out = mod.parse(text)
        self.assertEqual(out['recoveredNativeSession'], 'sess123')
        self.assertEqual(out['recoveredNativeKey'], 'key123')
        self.assertEqual(out['recoveredNativePassCode'], 'pass123')
        self.assertEqual(out['nativeWrapperLx'], 'lxVALUE')
        self.assertEqual(out['nativeWrapperLb'], 'lbVALUE')

    def test_imports_structured_native_wrapper_json_with_raw_body_when_enabled(self):
        text = '[native-wrapper-json] {"gameHex":"000000000000000000006200","rawBody":"LXKEY000000000000000000006200LB","lx":"LX","key":"KEY","lb":"LB"}'
        out = mod.parse(text, include_raw_body=True)
        self.assertEqual(out['nativeWrapperGameHex'], '000000000000000000006200')
        self.assertEqual(out['nativeWrapperLx'], 'LX')
        self.assertEqual(out['nativeWrapperKey'], 'KEY')
        self.assertEqual(out['nativeWrapperLb'], 'LB')
        self.assertEqual(out['nativeWrapperPrefixBeforeGameHex'], 'LXKEY')
        self.assertEqual(out['nativeWrapperSuffixAfterGameHex'], 'LB')
        self.assertIn('nativeWrapperRawBodySha256', out)
        audit = json.loads(out['nativeWrapperFieldAuditJson'])
        self.assertTrue(audit['readyForDryRunWrapperPlan'])
        self.assertEqual('nativeWrapperLx', audit['selectedLxSource'])
        self.assertEqual('nativeWrapperKey', audit['selectedKeySource'])
        self.assertEqual('nativeWrapperLb', audit['selectedLbSource'])
        self.assertFalse(audit['networkSendAllowed'])

    def test_raw_body_is_not_persisted_by_default(self):
        text = '[native-wrapper-json] {"gameHex":"aa","rawBody":"prefixaasuffix"}'
        out = mod.parse(text)
        self.assertNotIn('nativeWrapperRawBody', out)
        self.assertEqual(out['nativeWrapperRawBodyLength'], '14')
        self.assertIn('nativeWrapperRawBodySha256', out)

    def test_imports_request_body_json_metadata(self):
        text = '[native-wrapper-json] {"source":"android.o.ۥۘۡۜ.ۦۖ۫","threadId":"12","gameHex":"000000000000000000006200","rawBody":"LXKEY000000000000000000006200LB","byteCount":"31","offset":"0"}'
        out = mod.parse(text)
        self.assertEqual(out['nativeWrapperSource'], 'android.o.ۥۘۡۜ.ۦۖ۫')
        self.assertEqual(out['nativeWrapperThreadId'], '12')
        self.assertEqual(out['nativeWrapperByteCount'], '31')
        self.assertEqual(out['nativeWrapperOffset'], '0')
        self.assertEqual(out['nativeWrapperPrefixBeforeGameHexLength'], '5')
        self.assertEqual(out['nativeWrapperSuffixAfterGameHexLength'], '2')

    def test_derives_lx_and_lb_from_raw_body_when_key_is_known(self):
        text = '''
[java-native-ret] com.ifengwoo.dwpm.tuoji.DWSG.HelpClass.getKey => KEY
[native-wrapper-json] {"gameHex":"000000000000000000006200","rawBody":"LXKEY000000000000000000006200LB"}
'''
        out = mod.parse(text)
        self.assertEqual(out['derivedNativeWrapperLx'], 'LX')
        self.assertEqual(out['derivedNativeWrapperKey'], 'KEY')
        self.assertEqual(out['derivedNativeWrapperLb'], 'LB')
        self.assertIn('prefix_ends_with_key', out['nativeWrapperSplitStatus'])
        self.assertIn('suffix_assumed_lb', out['nativeWrapperSplitStatus'])
        audit = json.loads(out['nativeWrapperFieldAuditJson'])
        self.assertTrue(audit['readyForDryRunWrapperPlan'])
        self.assertEqual('derivedNativeWrapperLx', audit['selectedLxSource'])
        self.assertEqual('recoveredNativeKey', audit['selectedKeySource'])
        self.assertEqual('derivedNativeWrapperLb', audit['selectedLbSource'])

    def test_derives_key_from_known_lx_prefix(self):
        text = '[native-wrapper-json] {"gameHex":"aa","rawBody":"LXKEYaaLB","lx":"LX","lb":"LB"}'
        out = mod.parse(text)
        self.assertEqual(out['derivedNativeWrapperLx'], 'LX')
        self.assertEqual(out['derivedNativeWrapperKey'], 'KEY')
        self.assertEqual(out['derivedNativeWrapperLb'], 'LB')
        self.assertIn('prefix_starts_with_lx', out['nativeWrapperSplitStatus'])

if __name__ == '__main__':
    unittest.main()
