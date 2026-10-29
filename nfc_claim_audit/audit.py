"""Read documentation and parse source without executing it."""
import ast
import fnmatch
import os
from pathlib import Path
import re
from .phrases import NFC, NONFC


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence):
                fence = None
            lines.append("")
        elif match:
            fence = match[1]
            lines.append("")
        else:
            lines.append(line)
    positive = negative = False
    for paragraph in re.split(r"\n\s*\n", "\n".join(lines)):
        paragraph = re.sub(r"\s+", " ", paragraph.lower().replace("n't", " not").replace("-", " "))
        for phrase in NONFC:
            paragraph, count = re.subn(r"\b" + re.escape(phrase) + r"\b", " ", paragraph)
            negative |= bool(count)
        positive |= any(re.search(r"\b" + re.escape(p) + r"\b", paragraph) for p in NFC)
    return bool(positive), bool(negative)


def evidence(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    imports = {}
    shadows = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadows.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports[alias.asname or alias.name] = ((node.module or '') + '.' + alias.name) if not node.level else ''
    def resolve(node):
        if isinstance(node, ast.Name):
            return '' if node.id in shadows else imports.get(node.id, '')
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else ''
        return ''
    return any(isinstance(n, ast.Call) and resolve(n.func).startswith('nfc.')
               and resolve(n.func).split('.')[-1] == 'ContactlessFrontend'
               for n in ast.walk(tree))


def audit(root, ignore=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('root must be a readable directory')
    if not os.access(root, os.R_OK | os.X_OK):
        raise ValueError('root must be a readable directory')
    positive = negative = prod = test = False
    scanned = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            rel = path.relative_to(root)
            if path.is_symlink() or any(fnmatch.fnmatchcase(rel.as_posix(), g) for g in ignore):
                continue
            is_doc = path.suffix.lower() == '.md' and (rel.as_posix() == 'README.md' or 'docs' in rel.parts[:-1])
            is_source = path.suffix == '.py' and not any(p in ('fixtures', 'docs', 'examples') for p in rel.parts[:-1])
            if not (is_doc or is_source):
                continue
            text = path.read_text(encoding='utf-8')
            scanned += 1
            if is_doc:
                p, n = claims(text)
                positive |= p
                negative |= n
            if is_source and evidence(text):
                if 'tests' in rel.parts[:-1] or name.startswith('test_') or name.endswith('_test.py'):
                    test = True
                else:
                    prod = True
    findings = []
    if positive and not prod:
        findings.append(dict(rule='documented-nfc-claim-false', severity='MEDIUM' if test else 'HIGH', message='Documented tag capability lacks production frontend evidence.'))
    if negative and prod:
        findings.append(dict(rule='documented-no-nfc-claim-false', severity='HIGH', message='Documented absence conflicts with production frontend evidence.'))
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return dict(verdict='FAIL' if failed else 'PASS', findings=findings, files_scanned=scanned)
