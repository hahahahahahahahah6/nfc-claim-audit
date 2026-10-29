"""Command line interface."""
import argparse
import json
from . import __version__
from .audit import audit


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit documented tag capability against static source evidence.')
    parser.add_argument('root', nargs='?', default='.')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=['HIGH', 'MEDIUM'], default='HIGH')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore, args.fail_on)
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(1, str(exc) + '\n')
    if args.json:
        print(json.dumps(result))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{severity} {rule}: {message}'.format(**finding))
        if args.verbose:
            print('Files scanned:', result['files_scanned'])
    return 2 if result['verdict'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
