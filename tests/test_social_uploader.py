import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import social_uploader


class SocialUploaderTests(unittest.TestCase):
    def test_load_queue_rejects_invalid_shape(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            path.write_text('{"clips": "wrong"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                social_uploader.load_queue(path)

    def test_save_queue_merges_without_replacing_clip_status(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            path.write_text('{"clips":[{"clip_id":"a","approval_status":"approved","uploaded_targets":[]}]}', encoding="utf-8")
            social_uploader.save_queue_merged(path, {
                "a": {
                    "_live_approved": True,
                    "uploaded_targets": ["youtube"],
                    "requested_platforms": ["youtube"],
                }
            })
            data = social_uploader.load_queue(path)
            clip = data["clips"][0]
            self.assertEqual(clip["approval_status"], "uploaded")
            self.assertEqual(clip["uploaded_targets"], ["youtube"])


if __name__ == "__main__":
    unittest.main()
