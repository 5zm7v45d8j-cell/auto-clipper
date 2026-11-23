import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from clip_pipeline import approved_channels


class ApprovedChannelsTests(unittest.TestCase):
    def test_only_explicitly_approved_urls_are_returned(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "channels.txt"
            path.write_text(
                "https://www.youtube.com/@allowed|approved=true\n"
                "https://www.youtube.com/@unknown\n"
                "# comment\n",
                encoding="utf-8",
            )
            self.assertEqual(approved_channels(path), ["https://www.youtube.com/@allowed"])


if __name__ == "__main__":
    unittest.main()
