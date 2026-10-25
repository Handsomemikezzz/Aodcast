from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from typing import Iterator
from unittest.mock import patch
from urllib import error as urllib_error
from urllib import request as urllib_request

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.api.http_runtime import RuntimeContext, RuntimeHttpServer
from app.config import AppConfig
from app.domain.attachment import AttachmentKind
from app.domain.project import SessionProject
from app.domain.provider_config import LLMProviderConfig
from app.domain.session import SessionRecord
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.audio_rendering import AudioRenderingService
from app.orchestration.interview_service import InterviewOrchestrator, InterviewTurnResult
from app.orchestration.script_generation import ScriptGenerationService
from app.providers.llm.base import ImageInput, InterviewQuestionRequest
from app.providers.llm.openai_compatible import _user_message_content
from app.runtime.request_state_store import RequestStateStore
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore
from app.storage.speaker_reference_store import SpeakerReferenceStore

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "packages/shared-schemas"


def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 18 Tf 20 100 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n" % index + body + b"\nendobj\n"
    xref_offset = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        output += b"%010d 00000 n \n" % offset
    output += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_offset)
    return bytes(output)


class _CapturingProvider:
    def __init__(self) -> None:
        self.requests: list[InterviewQuestionRequest] = []

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        self.requests.append(request)
        yield "I can see the attachment."


class AttachmentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self.temp_dir.name))
        self.store.bootstrap()
        self.session = SessionRecord(topic="Attachments", creation_intent="Test uploads")
        self.store.save_project(SessionProject(session=self.session))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_image_is_stored_once_by_content_hash(self) -> None:
        first = self.store.save_attachment(
            self.session.session_id, filename="cat.png", declared_type="image/png", data=PNG_BYTES
        )
        second = self.store.save_attachment(
            self.session.session_id, filename="copy.png", declared_type="", data=PNG_BYTES
        )

        self.assertEqual(first.kind, AttachmentKind.IMAGE)
        self.assertNotEqual(first.attachment_id, second.attachment_id)
        self.assertEqual(first.sha256, second.sha256)
        blobs = list(self.store.attachments_dir(self.session.session_id).glob("*.png"))
        self.assertEqual(len(blobs), 1)
        loaded = self.store.load_attachment(self.session.session_id, first.attachment_id)
        self.assertEqual(self.store.read_attachment_bytes(loaded), PNG_BYTES)

    def test_tampered_blob_fails_hash_check(self) -> None:
        attachment = self.store.save_attachment(
            self.session.session_id, filename="cat.png", declared_type="image/png", data=PNG_BYTES
        )
        (self.store.attachments_dir(self.session.session_id) / attachment.blob_name).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "stored hash"):
            self.store.read_attachment_bytes(attachment)

    def test_rejects_unsupported_or_mislabeled_files(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported attachment type"):
            self.store.save_attachment(
                self.session.session_id, filename="tool.exe", declared_type="application/x-msdownload", data=b"MZ"
            )
        with self.assertRaisesRegex(ValueError, "not a valid image/png"):
            self.store.save_attachment(
                self.session.session_id, filename="fake.png", declared_type="image/png", data=b"plain text"
            )
        with self.assertRaisesRegex(ValueError, "not found"):
            self.store.load_attachment(self.session.session_id, "../session")

    def test_markdown_and_pdf_text_is_extracted_in_backend(self) -> None:
        markdown = self.store.save_attachment(
            self.session.session_id,
            filename="notes.md",
            declared_type="application/octet-stream",
            data="# 笔记\n\n第一条".encode("utf-8"),
        )
        pdf = self.store.save_attachment(
            self.session.session_id,
            filename="paper.pdf",
            declared_type="application/pdf",
            data=_minimal_pdf("Hello PDF attachment"),
        )

        self.assertEqual(markdown.mime_type, "text/markdown")
        self.assertEqual(self.store.read_attachment_text(markdown), "# 笔记\n\n第一条")
        self.assertIn("Hello PDF attachment", self.store.read_attachment_text(pdf))

    def test_transcript_with_attachments_matches_shared_schema(self) -> None:
        attachment = self.store.save_attachment(
            self.session.session_id, filename="cat.png", declared_type="image/png", data=PNG_BYTES
        )
        transcript = TranscriptRecord(session_id=self.session.session_id)
        transcript.append(Speaker.USER, "", attachments=[attachment])
        registry = Registry().with_resources(
            [
                (
                    "https://aodcast.dev/schemas/attachment.schema.json",
                    Resource.from_contents(json.loads((SCHEMAS_DIR / "attachment.schema.json").read_text())),
                )
            ]
        )
        schema = json.loads((SCHEMAS_DIR / "transcript.schema.json").read_text())
        Draft202012Validator(schema, registry=registry).validate(transcript.to_dict())

        with self.assertRaisesRegex(ValueError, "Only user turns"):
            transcript.append(Speaker.AGENT, "reply", attachments=[attachment])


class AttachmentInterviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.store = ProjectStore(root / "data")
        self.store.bootstrap()
        self.config_store = ConfigStore(root / "config")
        self.config_store.bootstrap()
        self.config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        self.session = SessionRecord(topic="Attachments", creation_intent="Test uploads")
        self.store.save_project(SessionProject(session=self.session))
        self.orchestrator = InterviewOrchestrator(self.store, self.config_store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _reply(self, content: str, attachment_ids: list[str], provider: _CapturingProvider) -> InterviewTurnResult:
        with patch("app.orchestration.interview_service.build_llm_provider", return_value=provider):
            items = list(
                self.orchestrator.submit_user_response_stream(
                    self.session.session_id, content, attachment_ids=attachment_ids
                )
            )
        result = items[-1]
        assert isinstance(result, InterviewTurnResult)
        return result

    def test_images_and_document_text_reach_the_provider(self) -> None:
        image = self.store.save_attachment(
            self.session.session_id, filename="cat.png", declared_type="image/png", data=PNG_BYTES
        )
        document = self.store.save_attachment(
            self.session.session_id, filename="notes.txt", declared_type="text/plain", data=b"Budget is 42 dollars."
        )
        provider = _CapturingProvider()

        result = self._reply("", [image.attachment_id, document.attachment_id], provider)

        request = provider.requests[0]
        self.assertEqual(request.images, (ImageInput(name="cat.png", mime_type="image/png", data=PNG_BYTES),))
        assert request.prompt_plan is not None
        self.assertIn("attachments", request.prompt_plan.metadata.section_ids)
        self.assertIn("Budget is 42 dollars.", request.prompt_plan.user)
        self.assertIn("[Attached: cat.png (image), notes.txt (document)]", request.prompt_plan.user)
        user_turn = result.project.transcript.turns[0]
        self.assertEqual(user_turn.content, "")
        self.assertEqual([item.attachment_id for item in user_turn.attachments], [image.attachment_id, document.attachment_id])
        reloaded = self.store.load_project(self.session.session_id)
        self.assertEqual(reloaded.transcript.turns[0].attachments[0].name, "cat.png")

    def test_earlier_images_are_resent_on_later_turns(self) -> None:
        image = self.store.save_attachment(
            self.session.session_id, filename="cat.png", declared_type="image/png", data=PNG_BYTES
        )
        self._reply("看这张图", [image.attachment_id], _CapturingProvider())
        provider = _CapturingProvider()

        self._reply("它是什么颜色？", [], provider)

        self.assertEqual([item.name for item in provider.requests[0].images], ["cat.png"])

    def test_reply_requires_text_or_attachment_and_known_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "message or at least one attachment"):
            self._reply("  ", [], _CapturingProvider())
        with self.assertRaisesRegex(ValueError, "not found"):
            self._reply("hi", ["att_" + "0" * 32], _CapturingProvider())


class OpenAICompatibleImagePartsTests(unittest.TestCase):
    def test_images_become_data_url_parts_after_text(self) -> None:
        content = _user_message_content(
            "Describe it", (ImageInput(name="cat.png", mime_type="image/png", data=b"\x89PNG"),)
        )
        self.assertEqual(
            content,
            [
                {"type": "text", "text": "Describe it"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw=="}},
            ],
        )
        self.assertEqual(_user_message_content("plain", ()), "plain")


class AttachmentHttpRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        cwd = Path(self.temp_dir.name)
        config = AppConfig.from_cwd(cwd)
        self.store = ProjectStore(config.data_dir)
        config_store = ConfigStore(config.config_dir)
        artifact_store = ArtifactStore(config.data_dir)
        request_state_store = RequestStateStore(config.data_dir)
        for item in (self.store, config_store, artifact_store, request_state_store):
            item.bootstrap()
        config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        context = RuntimeContext(
            cwd=cwd,
            config=config,
            store=self.store,
            config_store=config_store,
            artifact_store=artifact_store,
            speaker_reference_store=SpeakerReferenceStore(config.data_dir, artifact_store),
            request_state_store=request_state_store,
            orchestrator=InterviewOrchestrator(self.store, config_store),
            script_generation=ScriptGenerationService(self.store, config_store),
            audio_rendering=AudioRenderingService(self.store, config_store, artifact_store),
            runtime_token="runtime-token",
            bootstrap_nonce="bootstrap-nonce",
            bootstrap_created_at=time.time(),
            allowed_origins=frozenset({"http://localhost:1420"}),
        )
        self.server = RuntimeHttpServer(("127.0.0.1", 0), context)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.session = SessionRecord(topic="Attachments", creation_intent="Test uploads")
        self.store.save_project(SessionProject(session=self.session))

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        self.temp_dir.cleanup()

    def _upload(self, filename: str, content: bytes, content_type: str) -> dict[str, object]:
        boundary = f"aodcast-{uuid.uuid4().hex}"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        req = urllib_request.Request(
            f"{self.base_url}/api/v1/sessions/{self.session.session_id}/attachments",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=5) as response:
                return json.loads(response.read())
        except urllib_error.HTTPError as exc:
            with exc:
                return json.loads(exc.read())

    def test_upload_serve_and_reply_with_attachment(self) -> None:
        uploaded = self._upload("cat.png", PNG_BYTES, "image/png")
        self.assertTrue(uploaded["ok"])
        attachment = uploaded["data"]["attachment"]
        self.assertEqual(uploaded["data"]["request_state"]["operation"], "upload_attachment")

        with urllib_request.urlopen(
            f"{self.base_url}/api/v1/sessions/{self.session.session_id}/attachments/{attachment['attachment_id']}/content",
            timeout=5,
        ) as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertEqual(response.read(), PNG_BYTES)

        req = urllib_request.Request(
            f"{self.base_url}/api/v1/sessions/{self.session.session_id}/interview:reply-stream",
            data=json.dumps({"message": "", "attachment_ids": [attachment["attachment_id"]]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # The SSE connection stays open; read until the final event's data line.
        with urllib_request.urlopen(req, timeout=10) as response:
            in_final = False
            for raw_line in response:
                line = raw_line.decode("utf-8").rstrip("\n")
                if line == "event: final":
                    in_final = True
                elif in_final and line.startswith("data: "):
                    final = json.loads(line.removeprefix("data: "))
                    break
        self.assertTrue(final["ok"], final)
        user_turn = final["data"]["project"]["transcript"]["turns"][0]
        self.assertEqual(user_turn["attachments"][0]["attachment_id"], attachment["attachment_id"])
        # The mock provider reports that it cannot see images instead of pretending.
        self.assertIn("cannot view them: cat.png", final["data"]["next_question"])

    def test_upload_rejects_unsupported_type(self) -> None:
        payload = self._upload("tool.exe", b"MZ", "application/octet-stream")
        self.assertFalse(payload["ok"])
        self.assertIn("Unsupported attachment type", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
