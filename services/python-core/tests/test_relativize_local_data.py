from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "maintenance" / "relativize-local-data.py"


class RelativizeLocalDataTests(unittest.TestCase):
    def run_script(self, data_dir: Path, *extra: str) -> str:
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--data-dir", str(data_dir), *extra],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def build_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        data_dir = root / ".local-data"
        (data_dir / "exports" / "s1").mkdir(parents=True)
        (data_dir / "exports" / "s1" / "podcast.wav").write_bytes(b"RIFF")
        artifact = data_dir / "sessions" / "s1" / "artifact.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(
            json.dumps(
                {
                    "audio_path": "/old/place/Aodcast/.local-data/exports/s1/podcast.wav",
                    "transcript_path": "sessions/s1/transcript.json",
                    "gone_path": "/old/place/Aodcast/.local-data/exports/s1/missing.wav",
                    "builtin": "/old/place/Aodcast/services/python-core/app/assets/speaker-references/a.wav",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        ignored = data_dir / "speech-verification" / "x.json"
        ignored.parent.mkdir(parents=True)
        ignored.write_text('{"p": "/old/.local-data/exports/x.wav"}\n', encoding="utf-8")
        return data_dir, artifact, ignored

    def test_dry_run_changes_nothing_and_apply_rewrites_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, artifact, ignored = self.build_fixture(Path(tmp))
            original = artifact.read_text(encoding="utf-8")

            dry = self.run_script(data_dir)
            self.assertIn("Files changed: 1", dry)
            self.assertIn("Paths rewritten: 3", dry)
            self.assertIn("missing: exports/s1/missing.wav", dry)
            self.assertEqual(artifact.read_text(encoding="utf-8"), original)
            self.assertFalse(list(data_dir.glob("relativize-backup-*")))

            self.run_script(data_dir, "--apply")
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(payload["audio_path"], "exports/s1/podcast.wav")
            self.assertEqual(payload["builtin"], "builtin:a.wav")
            self.assertEqual(payload["transcript_path"], "sessions/s1/transcript.json")
            backups = list(data_dir.glob("relativize-backup-*/sessions/s1/artifact.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
            self.assertIn("/old/.local-data/", ignored.read_text(encoding="utf-8"))
            self.assertIn("Files changed: 0", self.run_script(data_dir))


if __name__ == "__main__":
    unittest.main()
