import base64
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.clients = []
        self.constructor = patch("openai.OpenAI", side_effect=self.make_client).start()
        self.addCleanup(patch.stopall)

    def make_client(self, *, api_key):
        client = MagicMock(api_key=api_key)
        client.responses.create.side_effect = self.respond
        self.clients.append(client)
        return client

    @staticmethod
    def respond(**options):
        if not options.get("stream"):
            return SimpleNamespace(status="completed", output_text="가짜 답변")
        context = MagicMock()
        context.__enter__.return_value = iter(
            [
                SimpleNamespace(type="response.output_text.delta", delta="가짜 "),
                SimpleNamespace(type="response.output_text.delta", delta="답변"),
                SimpleNamespace(type="response.completed"),
            ]
        )
        return context

    def app(self, key="fake-test-key"):
        app = AppTest.from_file(ROOT / "streamlit_app.py").run()
        app.text_input(key="api_key").set_value(key).run()
        self.assertFalse(app.exception)
        return app

    def test_pages_keep_key_and_client(self):
        app = self.app()
        client = self.clients[-1]
        for page, title in (
            ("Home", "텍스트와 이미지 생성"),
            ("Chat", "일반 대화"),
            ("Chatbot", "국립부경대학교 도서관 챗봇"),
            ("ChatPDF", "PDF 대화"),
            ("Home", "텍스트와 이미지 생성"),
        ):
            with self.subTest(page=page):
                app.switch_page(f"app_pages/{page}.py").run()
                self.assertFalse(app.exception)
                self.assertIn(title, [element.value for element in app.title])
                self.assertEqual(app.text_input(key="api_key").value, "fake-test-key")
                self.assertIs(app.session_state.openai_client, client)
        self.constructor.assert_called_once_with(api_key="fake-test-key")
        client.responses.create.assert_not_called()

    def test_home_cache_reuses_only_current_session(self):
        first = self.app()
        first_client = self.clients[-1]
        for _ in range(2):
            first.text_area[0].set_value("같은 질문")
            first.button[0].click().run()
            self.assertFalse(first.exception)
            self.assertEqual(first.session_state.home_answer, "가짜 답변")
        self.assertEqual(first_client.responses.create.call_count, 1)

        # AppTest의 고정 session_id 대신 별도 세션 식별자 지정
        with patch(
            "streamlit.runtime.caching.cache_data_api.get_session_id_or_throw",
            return_value="second-test-session",
        ):
            second = self.app()
            second_client = self.clients[-1]
            second.text_area[0].set_value("같은 질문")
            second.button[0].click().run()
        self.assertFalse(second.exception)
        self.assertEqual(second_client.responses.create.call_count, 1)
        self.assertEqual(first_client.responses.create.call_count, 1)

    def test_home_image_generation_and_rerun(self):
        app = self.app()
        client = self.clients[-1]
        encoded = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
            "/x8AAwMCAO+aL1sAAAAASUVORK5CYII="
        )
        client.images.generate.return_value = SimpleNamespace(
            data=[SimpleNamespace(b64_json=encoded)]
        )
        app.text_area[1].set_value("책을 읽는 고양이")
        app.button[1].click().run()
        self.assertFalse(app.exception)
        client.images.generate.assert_called_once_with(
            model="gpt-image-2.6-flare", prompt="책을 읽는 고양이"
        )
        self.assertEqual(app.session_state.home_image, base64.b64decode(encoded))
        self.assertEqual(len(app.image), 1)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.image), 1)
        self.assertEqual(client.images.generate.call_count, 1)

    def test_chat_history_and_clear(self):
        app = self.app()
        client = self.clients[-1]
        app.switch_page("app_pages/Chat.py").run()
        app.chat_input[0].set_value("첫 질문").run()
        app.chat_input[0].set_value("다음 질문").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.chat_messages), 4)
        self.assertEqual(
            client.responses.create.call_args.kwargs["input"],
            [
                {"role": "user", "content": "첫 질문"},
                {"role": "assistant", "content": "가짜 답변"},
                {"role": "user", "content": "다음 질문"},
            ],
        )
        app.switch_page("app_pages/Home.py").run()
        app.switch_page("app_pages/Chat.py").run()
        self.assertEqual(len(app.session_state.chat_messages), 4)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.chat_messages, [])
        self.assertEqual(len(app.chat_message), 0)

    def test_library_uses_rules_and_separate_history(self):
        app = self.app()
        client = self.clients[-1]
        app.session_state.chat_messages = [{"role": "user", "content": "일반 질문"}]
        app.switch_page("app_pages/Chatbot.py").run()
        app.chat_input[0].set_value("휴관일은 언제인가요?").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.library_messages), 2)
        self.assertEqual(len(app.session_state.chat_messages), 1)
        self.assertIn(
            (ROOT / "data/library_rules.txt").read_text(encoding="utf-8"),
            client.responses.create.call_args.kwargs["instructions"],
        )
        app.button[0].click().run()
        self.assertEqual(app.session_state.library_messages, [])
        self.assertEqual(len(app.session_state.chat_messages), 1)

    def test_failed_stream_does_not_change_history(self):
        for failure in ("error", "response.failed", "response.incomplete", None):
            with self.subTest(failure=failure):
                app = self.app()
                client = self.clients[-1]
                events = [
                    SimpleNamespace(
                        type="response.output_text.delta", delta="부분 답변"
                    )
                ]
                if failure:
                    events.append(SimpleNamespace(type=failure))
                context = MagicMock()
                context.__enter__.return_value = iter(events)
                client.responses.create.side_effect = None
                client.responses.create.return_value = context
                original = [{"role": "user", "content": "기존 질문"}]
                app.session_state.chat_messages = original.copy()
                app.switch_page("app_pages/Chat.py").run()
                app.chat_input[0].set_value("실패할 질문").run()
                self.assertFalse(app.exception)
                self.assertTrue(app.error)
                self.assertEqual(app.session_state.chat_messages, original)

    def test_key_change_clears_state_and_invalidates_cache(self):
        app = self.app()
        old_client = self.clients[-1]
        app.text_area[0].set_value("같은 질문")
        app.button[0].click().run()
        version = app.session_state.credential_version
        for key in ("chat_messages", "library_messages", "pdf_messages"):
            app.session_state[key] = [{"role": "user", "content": "이전 대화"}]
        app.session_state.home_image = b"old-image"
        app.session_state.pdf_ready = True
        app.session_state.pdf_name = "old.pdf"
        app.session_state.pdf_store_id = "store-old"
        app.session_state.pdf_file_id = "file-old"

        app.text_input(key="api_key").set_value("fake-new-key").run()
        self.assertFalse(app.exception)
        new_client = self.clients[-1]
        self.assertIsNot(old_client, new_client)
        self.assertEqual(app.session_state.credential_version, version + 1)
        old_client.close.assert_called_once()
        old_client.vector_stores.delete.assert_called_once_with("store-old")
        old_client.files.delete.assert_called_once_with("file-old")
        for key in (
            "chat_messages",
            "library_messages",
            "home_answer",
            "home_image",
            "pdf_messages",
            "pdf_ready",
            "pdf_name",
            "pdf_store_id",
            "pdf_file_id",
        ):
            self.assertNotIn(key, app.session_state)
        app.text_area[0].set_value("같은 질문")
        app.button[0].click().run()
        self.assertFalse(app.exception)
        new_client.responses.create.assert_called_once()
        old_client.responses.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
