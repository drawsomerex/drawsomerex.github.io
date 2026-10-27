"""Refresh the lab after the newly published podcast feed is publicly available."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

FEED = 'https://drawsomerex.github.io/podcasts/most-fascinating-stories/feed.xml'
TARGET = 'https://autonomousmedialab.com/internal/import/'
SOURCE = Path('src/site/podcasts/most-fascinating-stories/feed.xml')


def episodes(xml):
    rows = []
    for item in ET.fromstring(xml).findall('./channel/item'):
        identity = item.findtext('guid') or item.findtext('link') or item.findtext('title')
        if not identity:
            raise ValueError('Podcast item has no identity.')
        rows.append((parsedate_to_datetime(item.findtext('pubDate')).timestamp(),
                     'podcast-' + hashlib.sha256(identity.encode()).hexdigest()[:16]))
    if not rows:
        raise ValueError('The expected published feed contains no episodes.')
    return sorted(rows, reverse=True)


def public_feed():
    request = urllib.request.Request(FEED, headers={
        'User-Agent': 'AutonomousMediaLab-Publisher/1.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read(12000000)


def wait_for_public_feed(expected, fetch=public_feed, pause=time.sleep):
    for attempt in range(10):
        try:
            if expected in {identity for _, identity in episodes(fetch())}:
                return
        except (ValueError, ET.ParseError, urllib.error.URLError, TimeoutError):
            pass
        if attempt < 9:
            pause(20)
    raise RuntimeError('The newly published episode is not visible in the public RSS feed yet.')


def request_headers(secret, body, now=None):
    stamp = str(int(time.time() if now is None else now))
    canonical = 'v1\n' + stamp + '\nPOST\n/internal/import/\n' + hashlib.sha256(body).hexdigest()
    return {'Content-Type': 'application/json', 'User-Agent': 'AutonomousMediaLab-Publisher/1.0',
            'X-AML-Timestamp': stamp,
            'X-AML-Signature': hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()}


def verify_import(result, expected):
    if not result.get('ok') or not result.get('sources', {}).get('podcast', {}).get('ok'):
        raise RuntimeError('The website reported an import failure; inspect the studio source status.')
    if expected not in result.get('podcast_ids', []):
        raise RuntimeError('The latest published episode was not confirmed in the website catalogue.')


def main():
    secret = os.environ.get('AML_UPDATE_SECRET', '')
    if len(secret) < 48:
        raise RuntimeError('The dedicated AML_UPDATE_SECRET repository secret is missing.')
    expected = episodes(SOURCE.read_bytes())[0][1]
    wait_for_public_feed(expected)
    repo = os.environ.get('GITHUB_REPOSITORY', 'drawsomerex/drawsomerex.github.io')
    run = os.environ.get('GITHUB_RUN_ID', '')
    body = json.dumps({'run_url': f'https://github.com/{repo}/actions/runs/{run}',
                       'trigger': os.environ.get('GITHUB_EVENT_NAME', 'workflow_dispatch')},
                      separators=(',', ':')).encode()
    for attempt in range(3):
        request = urllib.request.Request(TARGET, data=body, method='POST',
                                         headers=request_headers(secret, body))
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read(64000))
        except urllib.error.HTTPError as error:
            if error.code == 409 and attempt < 2:
                time.sleep(65)
                continue
            raise RuntimeError(f'The website import returned HTTP {error.code}.') from None
        if result.get('skipped') and attempt < 2:
            time.sleep(65)
            continue
        verify_import(result, expected)
        print('Confirmed the latest published podcast episode in Autonomous Media Lab:', expected)
        for name, status in result.get('sources', {}).items():
            print(f"{name}: {'OK' if status.get('ok') else 'FAILED'}; {status.get('count', 0)} items")
        return


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, ET.ParseError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
