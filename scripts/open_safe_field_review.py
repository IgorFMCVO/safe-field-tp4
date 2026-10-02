#!/usr/bin/env python3
"""Open occurrence review using an existing local Core credential.

Run on the Raspberry (or trusted host with credential + CA). Only a short-lived,
one-use browser URL is emitted; the operational bearer is never printed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-url', required=True)
    parser.add_argument('--occurrence-id', required=True)
    parser.add_argument('--token-file', type=Path, default=Path.home()/'.config/safe-field-runtime/api.token')
    parser.add_argument('--ca-file', type=Path)
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    url=urllib.parse.urlsplit(args.core_url)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
        or url.query or url.fragment or url.path not in ('','/')):
        parser.error('core-url must be an HTTPS origin without credentials or query')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',args.occurrence_id):
        parser.error('Invalid occurrence ID')
    origin=args.core_url.rstrip('/')
    try:
        token=args.token_file.read_text(encoding='utf-8').strip()
        if not token or any(c.isspace() for c in token):
            raise ValueError('Existing token file empty or invalid')
        context=ssl.create_default_context(cafile=str(args.ca_file) if args.ca_file else None)
        data=json.dumps({'occurrence_id':args.occurrence_id}).encode()
        request=urllib.request.Request(origin+'/api/v1/review/ticket',data=data,
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(request,context=context,timeout=8) as response:
            result=json.loads(response.read(8192))
        path=result.get('path','')
        if not result.get('ok') or not path.startswith('/review/bootstrap?ticket='):
            raise ValueError('Unexpected review ticket response')
        target=origin+path
        if args.open_browser:webbrowser.open(target)
        else: print(target)
        return 0
    except urllib.error.HTTPError as exc:
        print(f'REVIEW_BOOTSTRAP_FAILED HTTP {exc.code}; no credential changed.',file=sys.stderr)
    except (OSError,ValueError,urllib.error.URLError) as exc:
        # Exception type only: avoid printing headers or a credential-bearing request.
        print(f'REVIEW_BOOTSTRAP_FAILED {type(exc).__name__}; check the existing CA/runtime paths.',file=sys.stderr)
    return 1

if __name__=='__main__': raise SystemExit(main())
