import json
import unittest
from migrate_internal_profile import sanitize_accounts, config_keys, reject_secrets, merge_missing
import xml.etree.ElementTree as ET

class PortableMigrationTest(unittest.TestCase):
    def test_only_identity_and_config_survive(self):
        raw = {"schemaVersion": 1, "accounts": [{"id": 42, "accountRef": "42", "username": "test",
            "enabled": True, "password": "never-copy", "gameAuthSignEvidence": "never-copy",
            "session": {"tokenCiphertext": "never-copy", "sourceMode": 1, "publicState": {
                "residentAutomationConfigJson": '{"brush":{"enabled":true}}',
                "savedTasksStarted": "true", "residentAutomationStateJson": "do-not-copy"}}}]}
        result = sanitize_accounts(json.dumps(raw))
        a = result["accounts"][0]
        self.assertFalse(a["enabled"])
        self.assertEqual(a["session"]["sourceMode"], 0)
        self.assertEqual(a["session"]["publicState"], {"residentAutomationConfigJson": '{"brush":{"enabled":true}}'})
        self.assertNotIn("never-copy", json.dumps(result))
        self.assertNotIn("savedTasksStarted", json.dumps(result))

    def test_secret_in_nested_settings_is_rejected(self):
        for key in ("password", "access_token", "sessionSecret", "cookie", "dm"):
            with self.assertRaises(ValueError): reject_secrets({"nested": json.dumps({key: "sensitive"})})

    def test_xml_only_accepts_feature_settings(self):
        self.assertEqual(config_keys('<map><string name="42::brush">{"levels":[1,2]}</string></map>'), ["42::brush"])
        with self.assertRaises(ValueError): config_keys('<map><string name="sessionToken">abc</string></map>')
        with self.assertRaises(ValueError): config_keys('<map><string name="42::brush">{"password":"x"}</string></map>')

    def test_restore_only_missing_preserves_new_session_and_existing_settings(self):
        old = sanitize_accounts(json.dumps({"schemaVersion": 1, "accounts": [{"accountRef":"42","id":42,"username":"test","platformKey":"sglm","serverName":"1区",
            "session":{"publicState":{"residentAutomationConfigJson":'{"brush":true}'}}}]}))
        snapshot={"format":"dwpm-portable-internal-v1","targetPackage":"com.example.dwpmclone.internal","accounts":old,
            "configXml":'<map><string name="42::brush">{"level":8}</string><string name="42::mine">{"level":1}</string></map>',"configKeys":["42::brush","42::mine"]}
        current=json.loads(json.dumps(old)); current["accounts"][0].update(enabled=True,loginState="REAL_PROTOCOL_CHECKING")
        current["accounts"][0]["session"]={"sourceMode":1,"publicState":{"roleId":"123","savedTasksStarted":"false"}}
        result, xml, added, restored = merge_missing(snapshot,current,'<map><string name="42::mine">{"level":9}</string></map>',"42")
        self.assertEqual(added,["42::brush"]); self.assertTrue(restored)
        self.assertEqual(result["accounts"][0]["session"]["sourceMode"],1)
        self.assertEqual(result["accounts"][0]["session"]["publicState"]["roleId"],"123")
        self.assertTrue(result["accounts"][0]["enabled"])
        self.assertIn('{"level":9}',[x.text for x in ET.fromstring(xml)])
        _, _, again, restored_again = merge_missing(snapshot,result,xml,"42")
        self.assertEqual(again,[]);self.assertFalse(restored_again)

if __name__ == "__main__": unittest.main()
