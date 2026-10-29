# nfc-claim-audit

Version 0.1.0. An offline static checker comparing documented tap-to-tag
capability with Python AST evidence. Audited source is never executed.
Requires Python 3.9 or later; no runtime dependencies.

```sh
python3 -m pip install .
nfc-claim-audit . --json
python3 -m nfc_claim_audit . --verbose
python3 -m unittest discover
python3 -m build
```

The positional directory defaults to the current directory. Repeat `--ignore`
with root-relative globs to omit files. `--version` prints the version.
JSON output contains verdict, findings (rule, severity, message), and a scanned
file count. Human output prints the same verdict and findings.

The following rules report contradictions between prose and source.

```text
documented-nfc-claim-false
documented-no-nfc-claim-false
```

 Production absence yields HIGH;
evidence confined to test files yields MEDIUM for a positive assertion.
The default HIGH threshold reports MEDIUM findings with exit 0;
`--fail-on MEDIUM` makes them exit 2. HIGH findings exit 2. Invalid or
unreadable paths exit 1. No detected assertion yields PASS and exit 0.
A positive assertion without any source yields HIGH; an absence assertion
without source passes. There is at most one finding per family.

Documentation includes root README.md and Markdown files beneath any docs
path component. Fenced blocks are excluded; inline code counts. Matching
lowercases, expands contracted negation, replaces hyphens with spaces, and
joins whitespace within blank-line-separated paragraphs. Absence spans are
removed before positive matching. Exact templates and word boundaries are
used; the complete templates are in `nfc_claim_audit/phrases.py`.

Source includes .py files except tests, test-prefixed or test-suffixed files,
fixtures, docs, examples, and symlinks. Test evidence is considered separately.
Alias-resolved nfcpy ContactlessFrontend instantiation is sufficient evidence;
opening the device counts without a subsequent connect. Bound, self-attribute,
with-target, and chained connection patterns therefore count as well. Local
class or function definitions shadow imported names.

## Limitations

Only exact templates are recognized. A bare NFC word, user instructions to hold
or tap a card, Bluetooth or USB reach, printing, and file exports do not make
an assertion for this checker. Imports, identifiers, NDEF objects, decorators,
and logging-only functions do not demonstrate a frontend operation.
System tag helpers invoked through subprocesses are not counted: shell command
strings are not AST evidence. Other NFC stacks, including Android NFC and
PC/SC smartcard readers, are out of scope; only nfcpy frontends are counted.
Static evidence cannot establish hardware availability or successful runtime
behavior. This is module-level import resolution, not control-flow analysis;
unparseable source provides no evidence. Environment files are never opened.
