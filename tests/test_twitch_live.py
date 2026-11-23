import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from twitch_live import read_twitch_channels


class TwitchAllowlistTests(unittest.TestCase):
    def test_only_rights_confirmed_twitch_channels_are_loaded(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "channels.txt"
            path.write_text(
                "twitch|authorized_user|rights_confirmed=true\n"
                "twitch|not_authorized|rights_confirmed=false\n"
                "twitch|invalid login!|rights_confirmed=true\n"
                "https://www.youtube.com/@channel|approved=true|rights_confirmed=true\n",
                encoding="utf-8",
            )
            self.assertEqual([item.login for item in read_twitch_channels(path)], ["authorized_user"])


if __name__ == "__main__":
    unittest.main()
