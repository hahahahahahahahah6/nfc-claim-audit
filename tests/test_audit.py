import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from nfc_claim_audit.audit import audit, claims, evidence
from nfc_claim_audit.__main__ import main
from nfc_claim_audit.phrases import NFC, NONFC
from .cases import GOOD

ROOT = Path(__file__).resolve().parents[1]

class AuditTests(unittest.TestCase):
    def scenario(self, doc, source=None, filename='app.py', **options):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'README.md').write_text(doc)
            if source is not None:
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            return audit(root, **options)

    def high(self, result, rule='documented-nfc-claim-false'):
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertEqual(result['findings'][0]['rule'], rule)

    def test_testonly(self):
        for filename in ['tests/device.py', 'test_device.py', 'device_test.py']:
            with self.subTest(filename=filename):
                result = self.scenario('reads nfc tags', GOOD, filename)
                self.assertEqual(result['verdict'], 'PASS')
                self.assertEqual(len(result['findings']), 1)
                self.assertEqual(result['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(result['findings'][0]['rule'], 'documented-nfc-claim-false')
                self.assertEqual(self.scenario('reads nfc tags', GOOD, filename, fail_on='MEDIUM')['verdict'], 'FAIL')

    def test_negative_with_evidence(self):
        self.high(self.scenario('no nfc', GOOD), 'documented-no-nfc-claim-false')

    def test_no_source_positive(self):
        self.high(self.scenario('reads nfc tags'))

    def test_no_source_negative(self):
        self.assertEqual(self.scenario('no nfc')['findings'], [])

    def test_self_audit(self):
        self.assertEqual(claims((ROOT / 'README.md').read_text()), (False, False))
        self.assertEqual(audit(ROOT)['verdict'], 'PASS')

    def test_normalization(self):
        self.assertEqual(claims("It doesn't read NFC tags."), (False, True))
        self.assertEqual(claims('READS-data\nfrom NFC tags'), (True, False))
        self.assertEqual(claims('reads\n\nnfc tags'), (False, False))
        self.assertEqual(claims('prereads nfc tagsuffix'), (False, False))

    def test_two_families(self):
        result = self.scenario('reads nfc tags. no nfc', GOOD)
        self.high(result, 'documented-no-nfc-claim-false')

    def test_doc_paths_ignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'nested/docs').mkdir(parents=True)
            (root / 'nested/docs/a.md').write_text('reads nfc tags')
            self.high(audit(root))
            self.assertEqual(audit(root, ['nested/docs/*'])['findings'], [])

    def test_excluded_sources(self):
        for filename in ['fixtures/app.py', 'docs/app.py', 'examples/app.py']:
            self.high(self.scenario('reads nfc tags', GOOD, filename))

    def test_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'README.md').write_text('reads nfc tags')
            (root / 'fixtures').mkdir()
            (root / 'fixtures/source.py').write_text(GOOD)
            (root / 'linked.py').symlink_to(root / 'fixtures/source.py')
            self.high(audit(root))

    def test_env_never_read(self):
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, '.env')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded):
            self.assertEqual(audit(ROOT / 'tests/fixtures/good')['verdict'], 'PASS')
            audit(ROOT / 'tests/fixtures')

    def test_cli(self):
        for name, code in [('good', 0), ('bad', 2), ('testonly', 0), ('no-nfc', 2)]:
            with self.subTest(name=name), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main([str(ROOT / 'tests/fixtures' / name), '--json', '--verbose']), code)
                self.assertIn(json.loads(out.getvalue())['verdict'], ['PASS', 'FAIL'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(ROOT / 'tests/fixtures/testonly'), '--fail-on', 'MEDIUM']), 2)
            self.assertEqual(main([str(ROOT / 'tests/fixtures/bad'), '--ignore', 'README.md']), 0)
            self.assertEqual(main([str(ROOT), '--verbose']), 0)
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as cm:
            main(['--version'])
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), '0.1.0')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main(['/does/not/exist'])
        self.assertEqual(cm.exception.code, 1)

    def test_packaging(self):
        project = (ROOT / 'pyproject.toml').read_text()
        self.assertIn('nfc-claim-audit = "nfc_claim_audit.__main__:main"', project)
        self.assertIn('MIT License', (ROOT / 'LICENSE').read_text())
        self.assertIn('recursive-include tests *.py *.md .env', (ROOT / 'MANIFEST.in').read_text())
        for folder in ['nfc_claim_audit', 'tests']:
            for path in (ROOT / folder).rglob('*.py'):
                text = path.read_text()
                self.assertIsNone(re.search(r'\bpython\s+(?:-m|-c|\w+\.py)', text))
                self.assertIsNone(re.search(r'(?:AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36}|' + '-----BEGIN ' + r'PRIVATE KEY-----)', text))


def add_case(name, doc, source, expected):
    def test(self):
        result = self.scenario(doc, source)
        if expected == 'HIGH':
            self.high(result)
        else:
            self.assertEqual(result['verdict'], 'PASS')
            self.assertEqual(result['findings'], [])
    setattr(AuditTests, 'test_' + name, test)

for index, phrase in enumerate(NFC):
    add_case('phrase_positive_%02d' % index, phrase, None, 'HIGH')
for index, phrase in enumerate(NONFC):
    add_case('phrase_negative_%02d' % index, phrase, None, 'PASS')

sources = {
    'frontend': GOOD,
    'attribute': 'import nfc\nnfc.ContactlessFrontend("usb")',
    'alias': 'import nfc as nf\nnf.ContactlessFrontend("usb")',
    'bound': GOOD + 'clf.connect(rdwr={})',
    'with': 'import nfc\nwith nfc.ContactlessFrontend("usb") as clf:\n clf.connect(rdwr={})',
    'chain': 'import nfc\nnfc.ContactlessFrontend("usb").connect(rdwr={})',
    'self': 'import nfc\nself.clf = nfc.ContactlessFrontend("usb")\nself.clf.connect()',
    'from_alias': 'from nfc import ContactlessFrontend as CF\nCF("usb")',
    'dotted_import': 'import nfc.tag\nnfc.ContactlessFrontend("usb")',
    'submodule': 'from nfc.clf import ContactlessFrontend\nContactlessFrontend("usb")',
}
for name, source in sources.items():
    add_case('good_' + name, 'reads nfc tags', source, 'PASS')
bad = {
    'none': 'print("hello")',
    'bare_import': 'import nfc',
    'unbound': 'clf.connect()',
    'string': 'tag = "04:11:22:33:44:55:66"',
    'ndef': 'import ndef\nndef.TextRecord("hello")',
    'subprocess': 'import subprocess\nsubprocess.run(["nfc-poll"])',
    'bluetooth': 'import bluetooth\nbluetooth.BluetoothSocket().connect(("x", 1))',
    'usb': 'import usb.core\nusb.core.find()',
    'serial': 'import serial\nserial.Serial("port")',
    'local': 'class ContactlessFrontend: pass\nContactlessFrontend()',
    'shadow': 'from nfc import ContactlessFrontend\nclass ContactlessFrontend: pass\nContactlessFrontend()',
    'function_shadow': 'from nfc import ContactlessFrontend\ndef ContactlessFrontend(): pass\nContactlessFrontend()',
    'other_import': 'import local as nfc\nnfc.ContactlessFrontend()',
    'smartcard': 'from smartcard import ContactlessFrontend\nContactlessFrontend()',
    'logging': 'def connect_tag():\n print("tag")\nconnect_tag()',
    'decorator': '@app.get("/tag")\ndef tag(): return "ok"',
    'docstring': '\"\"\"import nfc; nfc.ContactlessFrontend()\"\"\"',
    'syntax': 'import nfc\n!invalid',
}
for name, source in bad.items():
    add_case('bad_' + name, 'reads nfc tags', source, 'HIGH')
for name, doc in {
    'no_claim': 'A utility for cards.',
    'user_instruction': 'Hold the tag near the reader first. Tap the card before starting.',
    'bare_word': '# NFC',
    'fenced': '```text\nreads nfc tags\n```',
    'tilde_fenced': '~~~~\nno nfc\nreads nfc tags\n~~~~',
    'adjacent': 'Connects via Bluetooth. Supports USB. Prints files.',
}.items():
    add_case(name, doc, None, 'PASS')
add_case('no_claim_with_evidence', 'Card utility', GOOD, 'PASS')
add_case('inline', 'It `reads nfc tags`.', None, 'HIGH')
