import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from openai import NotFoundError, OpenAIError
from streamlit.testing.v1 import AppTest

import common

ROOT = Path(__file__).resolve().parents[1]
PDF = b"%PDF-1.7\nexample document"


class SessionState(dict):
    def __getattr__(self, name):
        return self[name]


def make_client():
    client = MagicMock()
    client.files.create.return_value.id = "file-test"
    client.vector_stores.create.return_value.id = "store-test"
    client.vector_stores.files.create_and_poll.return_value.status = "completed"
    return client


class PreparePDFTests(unittest.TestCase):
    def setUp(self):
        self.state = SessionState()
        self.client = make_client()
        self.patcher = patch.object(common.st, "session_state", self.state)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_invalid_uploads_rejected_before_api(self):
        for name, content in (
            ("document.txt", PDF),
            ("document.pdf", b"not a PDF"),
            ("document.pdf", b"x" * 1024 + PDF),
            ("document.pdf", b""),
        ):
            with self.subTest(name=name, content_length=len(content)):
                with self.assertRaises(ValueError):
                    common.prepare_pdf(self.client, name, content)
                self.assertEqual(self.state, {})
        self.assertEqual(self.client.mock_calls, [])

    def test_oversized_upload_rejected_before_api(self):
        oversized = PDF + b"x" * (20 * 1024 * 1024)
        with self.assertRaises(ValueError):
            common.prepare_pdf(self.client, "large.pdf", oversized)
        self.assertEqual(self.client.mock_calls, [])
        self.assertEqual(self.state, {})

    def test_success_creates_one_file_and_store_and_marks_ready(self):
        common.prepare_pdf(self.client, "document.PDF", PDF)
        self.client.files.create.assert_called_once_with(
            file=("document.PDF", PDF, "application/pdf"),
            purpose="assistants",
            expires_after={"anchor": "created_at", "seconds": 86400},
        )
        self.client.vector_stores.create.assert_called_once_with(
            name="streamlit_study ChatPDF",
            expires_after={"anchor": "last_active_at", "days": 1},
        )
        self.client.vector_stores.files.create_and_poll.assert_called_once_with(
            vector_store_id="store-test", file_id="file-test"
        )
        self.assertEqual(self.state.pdf_file_id, "file-test")
        self.assertEqual(self.state.pdf_store_id, "store-test")
        self.assertEqual(self.state.pdf_name, "document.PDF")
        self.assertIs(self.state.pdf_ready, True)

    def test_file_creation_failure_has_no_saved_ids(self):
        self.client.files.create.side_effect = OpenAIError("업로드 실패")
        with self.assertRaises(OpenAIError):
            common.prepare_pdf(self.client, "document.pdf", PDF)
        self.assertEqual(self.state, {})
        self.client.vector_stores.create.assert_not_called()

    def test_store_creation_failure_preserves_file_for_cleanup(self):
        self.client.vector_stores.create.side_effect = OpenAIError("저장소 실패")
        with self.assertRaises(OpenAIError):
            common.prepare_pdf(self.client, "document.pdf", PDF)
        self.assertEqual(self.state.pdf_file_id, "file-test")
        self.assertNotIn("pdf_store_id", self.state)
        self.assertNotIn("pdf_ready", self.state)

    def test_index_request_failure_preserves_both_ids(self):
        self.client.vector_stores.files.create_and_poll.side_effect = OpenAIError(
            "색인 요청 실패"
        )
        with self.assertRaises(OpenAIError):
            common.prepare_pdf(self.client, "document.pdf", PDF)
        self.assertEqual(self.state.pdf_file_id, "file-test")
        self.assertEqual(self.state.pdf_store_id, "store-test")
        self.assertNotIn("pdf_ready", self.state)

    def test_uncompleted_index_preserves_ids_without_ready(self):
        for status in ("failed", "cancelled", "in_progress"):
            with self.subTest(status=status):
                self.state.clear()
                self.client.vector_stores.files.create_and_poll.return_value.status = (
                    status
                )
                with self.assertRaises(ValueError):
                    common.prepare_pdf(self.client, "document.pdf", PDF)
                self.assertEqual(self.state.pdf_file_id, "file-test")
                self.assertEqual(self.state.pdf_store_id, "store-test")
                self.assertNotIn("pdf_ready", self.state)


class DeletePDFTests(unittest.TestCase):
    def setUp(self):
        self.state = SessionState(
            pdf_store_id="store-test",
            pdf_file_id="file-test",
            pdf_ready=True,
            pdf_name="document.pdf",
            pdf_messages=[{"role": "user", "content": "질문"}],
            pdf_upload=object(),
            other_messages=["유지"],
        )
        self.client = make_client()
        self.patcher = patch.object(common.st, "session_state", self.state)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_success_deletes_remote_resources_and_only_pdf_state(self):
        common.delete_pdf(self.client)
        self.client.vector_stores.delete.assert_called_once_with("store-test")
        self.client.files.delete.assert_called_once_with("file-test")
        self.assertEqual(self.state, {"other_messages": ["유지"]})

    def test_store_failure_preserves_ids_for_retry(self):
        self.client.vector_stores.delete.side_effect = OpenAIError("삭제 실패")
        before = self.state.copy()
        before.pop("pdf_ready")
        with self.assertRaises(OpenAIError):
            common.delete_pdf(self.client)
        self.assertEqual(self.state, before)
        self.client.files.delete.assert_not_called()
        self.client.vector_stores.delete.side_effect = None
        common.delete_pdf(self.client)
        self.assertEqual(self.state, {"other_messages": ["유지"]})

    def test_file_failure_retries_only_remaining_remote_resource(self):
        self.client.files.delete.side_effect = OpenAIError("삭제 실패")
        with self.assertRaises(OpenAIError):
            common.delete_pdf(self.client)
        self.assertNotIn("pdf_store_id", self.state)
        self.assertNotIn("pdf_ready", self.state)
        self.assertEqual(self.state.pdf_file_id, "file-test")
        self.client.files.delete.side_effect = None
        common.delete_pdf(self.client)
        self.client.vector_stores.delete.assert_called_once_with("store-test")
        self.assertEqual(self.client.files.delete.call_count, 2)
        self.assertEqual(self.state, {"other_messages": ["유지"]})

    def test_not_found_resources_are_treated_as_already_deleted(self):
        response = SimpleNamespace(status_code=404, request=None, headers={})
        self.client.vector_stores.delete.side_effect = NotFoundError(
            "없음", response=response, body=None
        )
        self.client.files.delete.side_effect = NotFoundError(
            "없음", response=response, body=None
        )
        common.delete_pdf(self.client)
        self.assertEqual(self.state, {"other_messages": ["유지"]})

    def test_cleanup_without_ids_never_calls_remote_delete(self):
        self.state.pop("pdf_store_id")
        self.state.pop("pdf_file_id")
        common.delete_pdf(self.client)
        self.client.vector_stores.delete.assert_not_called()
        self.client.files.delete.assert_not_called()
        self.assertEqual(self.state, {"other_messages": ["유지"]})


class StreamTextTests(unittest.TestCase):
    def test_extracts_text_and_refusal_deltas_only(self):
        events = [
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.output_text.delta", delta="안녕"),
            SimpleNamespace(type="response.refusal.delta", delta="거절"),
            SimpleNamespace(type="response.output_text.done", text="중복 제외"),
            SimpleNamespace(type="response.completed"),
        ]
        self.assertEqual(list(common.stream_text(events)), ["안녕", "거절"])

    def test_failure_events_raise(self):
        for event_type in ("error", "response.failed", "response.incomplete"):
            with self.subTest(event_type=event_type):
                self.assertRaises(
                    ValueError,
                    list,
                    common.stream_text([SimpleNamespace(type=event_type)]),
                )

    def test_missing_completion_raises_after_partial_delta(self):
        events = common.stream_text(
            [SimpleNamespace(type="response.output_text.delta", delta="일부")]
        )
        self.assertEqual(next(events), "일부")
        with self.assertRaises(ValueError):
            next(events)

    def test_empty_stream_is_incomplete(self):
        with self.assertRaises(ValueError):
            list(common.stream_text([]))


class ChatPDFPageTests(unittest.TestCase):
    def page_with_ready_pdf(self):
        client = make_client()
        app = AppTest.from_file(str(ROOT / "app_pages" / "ChatPDF.py"))
        for key, value in {
            "openai_client": client,
            "pdf_store_id": "store-test",
            "pdf_file_id": "file-test",
            "pdf_ready": True,
            "pdf_name": "document.pdf",
            "pdf_messages": [{"role": "user", "content": "기존 질문"}],
        }.items():
            app.session_state[key] = value
        app.run()
        self.assertEqual(len(app.exception), 0)
        return app, client

    def test_clear_removes_messages_but_keeps_remote_pdf(self):
        app, client = self.page_with_ready_pdf()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["pdf_messages"], [])
        self.assertTrue(app.session_state["pdf_ready"])
        self.assertEqual(app.session_state["pdf_store_id"], "store-test")
        self.assertEqual(app.session_state["pdf_file_id"], "file-test")
        client.vector_stores.delete.assert_not_called()
        client.files.delete.assert_not_called()

    def test_leave_deletes_resources_and_returns_to_upload(self):
        app, client = self.page_with_ready_pdf()
        app.button[1].click().run()
        self.assertEqual(len(app.exception), 0)
        client.vector_stores.delete.assert_called_once_with("store-test")
        client.files.delete.assert_called_once_with("file-test")
        self.assertNotIn("pdf_ready", app.session_state)
        self.assertEqual(len(app.get("file_uploader")), 1)
        self.assertEqual(len(app.chat_input), 0)

    def test_partial_leave_failure_keeps_retry_ui_without_ready_store(self):
        app, client = self.page_with_ready_pdf()
        client.files.delete.side_effect = OpenAIError("삭제 실패")
        app.button[1].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("pdf_ready", app.session_state)
        self.assertNotIn("pdf_store_id", app.session_state)
        self.assertEqual(app.session_state["pdf_file_id"], "file-test")
        self.assertEqual(len(app.chat_input), 0)
        self.assertEqual(len(app.get("file_uploader")), 0)
        client.files.delete.side_effect = None
        app.button[1].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.get("file_uploader")), 1)
        client.vector_stores.delete.assert_called_once_with("store-test")
        self.assertEqual(client.files.delete.call_count, 2)


if __name__ == "__main__":
    unittest.main()
