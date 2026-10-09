#!/usr/bin/env python3
"""Notify IndexNow only after a changed, owned page has been deployed.

snapshot: save the currently live manifest before deployment.
notify: compare with the new build; dry run unless --submit is supplied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT/'.indexnow-before.json'


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent':'ResearchWebsiteDeployment/1.0','Cache-Control':'no-cache'}), timeout=15) as response:
        if response.url != url:
            raise ValueError('Unexpected redirect: confirm the canonical website address before notifying.')
        return response.read(2_000_000)


def validate_manifest(manifest, base):
    if manifest.get('base_url') != base or not isinstance(manifest.get('pages'), dict):
        raise ValueError('Manifest belongs to a different website or is malformed.')
    for path, digest in manifest['pages'].items():
        if path and not re.fullmatch(r'(?:[a-z0-9]+(?:-[a-z0-9]+)*/)+', path):
            raise ValueError('Manifest contains an invalid path.')
        if not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('Manifest contains an invalid content hash.')
    return manifest['pages']


def changed_paths(before, after):
    return sorted(path for path in set(before)|set(after) if before.get(path) != after.get(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot','notify'])
    parser.add_argument('--base-url', default=os.environ.get('SITE_URL'))
    parser.add_argument('--submit', action='store_true')
    args = parser.parse_args()
    if not args.base_url:
        parser.error('SITE_URL or --base-url is required.')
    base = args.base_url.rstrip('/')+'/'
    parsed = urlparse(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        parser.error('A public HTTPS base URL is required.')
    if args.command == 'snapshot':
        try:
            previous = validate_manifest(json.loads(fetch(base+'indexnow-manifest.json')),base)
            state = {'status':'ok','base_url':base,'pages':previous}
        except HTTPError as exc:
            state = {'status':'first_deployment' if exc.code == 404 else 'unavailable','base_url':base,'pages':{}}
        except (OSError, ValueError, URLError):
            state = {'status':'unavailable','base_url':base,'pages':{}}
        STATE.write_text(json.dumps(state))
        print('Previous website state:', state['status'])
        return
    if not STATE.exists():
        raise ValueError('Run snapshot before deployment. No notification sent.')
    state = json.loads(STATE.read_text())
    if state['base_url'] != base or state['status'] == 'unavailable':
        print('::warning::Previous website state could not be established. Skipped IndexNow; website deployment is unaffected.')
        return
    new_manifest = json.loads((ROOT/'dist/indexnow-manifest.json').read_text())
    after = validate_manifest(new_manifest,base)
    changed = changed_paths(state['pages'],after)
    if not changed:
        print('No changed research pages. No IndexNow request sent.')
        return
    print(f'{len(changed)} new, changed or removed pages.')
    if not args.submit:
        print('Dry run: no request sent. URLs:', ', '.join(base+path for path in changed))
        return
    site = json.loads((ROOT/'data/site.json').read_text())
    key = site.get('indexnow_key','')
    if not re.fullmatch(r'[a-f0-9]{32}',key):
        raise ValueError('Configure a valid ownership key before submission.')
    # Deployment completion can precede CDN visibility. Never notify stale content.
    for attempt in range(4):
        try:
            if fetch(base+key+'.txt').decode().strip() != key:
                raise ValueError('The hosted ownership key does not match.')
            if validate_manifest(json.loads(fetch(base+'indexnow-manifest.json')),base) != after:
                raise ValueError('The deployed manifest is not current yet.')
            for path in changed:
                if path in after:
                    if hashlib.sha256(fetch(base+path)).hexdigest() != after[path]:
                        raise ValueError('A changed page is not current yet.')
                else:
                    try:
                        fetch(base+path)
                    except HTTPError as exc:
                        if exc.code not in (404,410):
                            raise
                    else:
                        raise ValueError('A removed page is still live.')
            break
        except (OSError, ValueError, URLError) as exc:
            if attempt == 3:
                raise ValueError('Live deployment checks failed; no IndexNow request sent.') from exc
            time.sleep(3)
    payload = {'host':parsed.netloc,'key':key,'keyLocation':base+key+'.txt','urlList':[base+path for path in changed]}
    request = Request('https://api.indexnow.org/indexnow',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json; charset=utf-8'},method='POST')
    with urlopen(request,timeout=30) as response:
        status = response.status
    if status not in (200,202):
        raise ValueError(f'Unexpected IndexNow response: {status}')
    print(f'IndexNow HTTP {status}: '+('received' if status == 200 else 'ownership validation pending')+'. This is not confirmation of indexing or ranking.')


if __name__ == '__main__':
    main()
