import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('refresh_media_lab', Path(__file__).resolve().parents[1] / 'scripts/refresh_media_lab.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

OLD = b'<rss><channel><item><guid>old</guid><pubDate>Thu, 22 Oct 2026 15:00:00 +0000</pubDate></item></channel></rss>'
NEW = OLD.replace(b'</channel>', b'<item><guid>new</guid><pubDate>Tue, 27 Oct 2026 15:00:00 +0000</pubDate></item></channel>')


class PublishHookTests(unittest.TestCase):
    def test_waits_for_new_episode_instead_of_importing_stale_pages_feed(self):
        expected = hook.episodes(NEW)[0][1]
        responses = iter([OLD, NEW])
        waits = []
        hook.wait_for_public_feed(expected, lambda: next(responses), waits.append)
        self.assertEqual(waits, [20])

    def test_stale_feed_fails_instead_of_reporting_success(self):
        with self.assertRaisesRegex(RuntimeError, 'not visible'):
            hook.wait_for_public_feed(hook.episodes(NEW)[0][1], lambda: OLD, lambda _: None)

    def test_successful_refresh_must_include_the_new_episode(self):
        result = {'ok': True, 'sources': {'podcast': {'ok': True}}, 'podcast_ids': [hook.episodes(OLD)[0][1]]}
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
            hook.verify_import(result, hook.episodes(NEW)[0][1])
        result['podcast_ids'].append(hook.episodes(NEW)[0][1])
        hook.verify_import(result, hook.episodes(NEW)[0][1])

    def test_signing_never_sends_secret_and_binds_payload(self):
        secret = 'a' * 64
        headers = hook.request_headers(secret, b'{}', 1792980000)
        self.assertNotIn(secret, headers.values())
        self.assertNotEqual(headers['X-AML-Signature'], hook.request_headers(secret, b'{"changed":true}', 1792980000)['X-AML-Signature'])


if __name__ == '__main__':
    unittest.main()
