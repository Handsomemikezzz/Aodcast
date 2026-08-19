from __future__ import annotations

import unittest

from app.domain.episode_source import (
    EpisodeSource,
    SourceConversionMode,
    SourceImportKind,
    SourceTargetLength,
)


class EpisodeSourceTests(unittest.TestCase):
    def test_markdown_import_extracts_title_content_and_warnings(self) -> None:
        source = EpisodeSource.from_markdown(
            session_id="session-1",
            name="post.md",
            import_kind=SourceImportKind.FILE,
            conversion_mode=SourceConversionMode.ADAPT,
            target_length=SourceTargetLength.STANDARD,
            focus_instructions="Keep the practical takeaway.",
            raw_markdown=(
                "---\ntitle: Local-first writing\n---\n\n"
                "# Ignored fallback title\n\nA paragraph with **emphasis** and [a link](https://example.com).\n\n"
                "```python\nprint('not spoken')\n```\n\n![diagram](diagram.png)"
            ),
        )

        self.assertEqual(source.title, "Local-first writing")
        self.assertIn("A paragraph with emphasis and a link", source.normalized_text)
        self.assertNotIn("print", source.normalized_text)
        self.assertEqual(source.version, 1)
        self.assertEqual(len(source.content_hash), 64)
        self.assertTrue(any("code block" in warning for warning in source.warnings))
        self.assertTrue(any("image" in warning for warning in source.warnings))

    def test_replacing_source_preserves_identity_and_increments_version(self) -> None:
        first = EpisodeSource.from_markdown(
            session_id="session-1",
            name="first.md",
            import_kind=SourceImportKind.FILE,
            raw_markdown="# First\n\nThis is the first sufficiently long article body.",
        )
        second = EpisodeSource.from_markdown(
            session_id="session-1",
            name="second.md",
            import_kind=SourceImportKind.FILE,
            raw_markdown="# Second\n\nThis is a replacement article with different material.",
            previous=first,
        )

        self.assertEqual(second.source_id, first.source_id)
        self.assertEqual(second.created_at, first.created_at)
        self.assertEqual(second.version, 2)
        self.assertNotEqual(second.content_hash, first.content_hash)

    def test_markdown_import_rejects_non_readable_content(self) -> None:
        with self.assertRaisesRegex(ValueError, "20 readable characters"):
            EpisodeSource.from_markdown(
                session_id="session-1",
                name="empty.md",
                import_kind=SourceImportKind.FILE,
                raw_markdown="```\nonly code\n```",
            )

    def test_api_style_path_name_falls_back_to_safe_display_name(self) -> None:
        source = EpisodeSource.from_markdown(
            session_id="session-1",
            name="/",
            import_kind=SourceImportKind.PASTE,
            raw_markdown="# Safe title\n\nThis article has enough readable content for import.",
        )

        self.assertEqual(source.name, "Pasted Markdown")


if __name__ == "__main__":
    unittest.main()
