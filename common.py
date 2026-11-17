from pathlib import Path

import streamlit as st
from openai import AuthenticationError, NotFoundError, OpenAIError, RateLimitError

TEXT_MODEL = "gpt-6-luna"
IMAGE_MODEL = "gpt-image-2.6-flare"
DATA_DIR = Path(__file__).parent / "data"


def show_api_error(error):
    """민감한 API 응답을 제외한 오류 안내"""
    if isinstance(error, AuthenticationError):
        st.error("API Key를 확인해 주세요.")
    elif isinstance(error, RateLimitError):
        st.error("사용 한도나 잔액을 확인하고 잠시 후 다시 시도해 주세요.")
    else:
        st.error(
            "요청을 완료하지 못했습니다. 연결 상태와 모델 접근 권한을 확인해 주세요."
        )


def require_client():
    """현재 세션의 OpenAI client 반환"""
    client = st.session_state.get("openai_client")
    if client is None:
        st.info("사이드바에 OpenAI API Key를 입력해 주세요.")
        st.stop()
    return client


def clear_messages(key):
    """선택한 페이지의 대화 기록 초기화"""
    st.session_state[key] = []


def stream_text(events):
    """Responses 이벤트에서 텍스트 추출 및 완료 상태 확인"""
    completed = False
    for event in events:
        if event.type in {"response.output_text.delta", "response.refusal.delta"}:
            yield event.delta
        elif event.type == "response.completed":
            completed = True
        elif event.type in {"error", "response.failed", "response.incomplete"}:
            raise ValueError("응답 생성 중단")
    if not completed:
        raise ValueError("응답 완료 이벤트 누락")


def render_chat(key, instructions, *, vector_store_id=None):
    """페이지별 기록과 스트리밍 대화 처리"""
    client = require_client()
    messages = st.session_state.setdefault(key, [])
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("질문을 입력하세요", key=f"{key}_input")
    if not prompt or not prompt.strip():
        return
    user_message = {"role": "user", "content": prompt.strip()}
    with st.chat_message("user"):
        st.markdown(user_message["content"])

    options = {}
    if vector_store_id:
        options = {
            "tools": [{"type": "file_search", "vector_store_ids": [vector_store_id]}],
            "tool_choice": {"type": "file_search"},
        }
    try:
        with (
            st.chat_message("assistant"),
            client.responses.create(
                model=TEXT_MODEL,
                instructions=instructions,
                input=messages + [user_message],
                stream=True,
                store=False,
                **options,
            ) as events,
        ):
            response = st.write_stream(stream_text(events))
        if not response:
            raise ValueError("빈 응답")
    except (OpenAIError, ValueError) as error:
        show_api_error(error)
        st.caption(
            "완료되지 않은 응답은 대화 기록에 저장하지 않았습니다. 다시 질문해 주세요."
        )
        return
    messages.extend([user_message, {"role": "assistant", "content": response}])


def delete_pdf(client):
    """원격 PDF 자원 삭제 후 세션 상태 정리"""
    st.session_state.pop("pdf_ready", None)
    for key, resource in (
        ("pdf_store_id", client.vector_stores),
        ("pdf_file_id", client.files),
    ):
        resource_id = st.session_state.get(key)
        if resource_id:
            try:
                resource.delete(resource_id)
            except NotFoundError:
                pass
            del st.session_state[key]
    for key in ("pdf_ready", "pdf_name", "pdf_messages", "pdf_upload"):
        st.session_state.pop(key, None)


def prepare_pdf(client, name, content):
    """단일 PDF 업로드와 검색용 색인 생성"""
    if not name.lower().endswith(".pdf") or b"%PDF-" not in content[:1024]:
        raise ValueError("올바른 PDF 파일 필요")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("20MB 이하 PDF 필요")
    st.session_state["pdf_file_id"] = client.files.create(
        file=(name, content, "application/pdf"),
        purpose="assistants",
        expires_after={"anchor": "created_at", "seconds": 86400},
    ).id
    st.session_state["pdf_name"] = name
    st.session_state["pdf_store_id"] = client.vector_stores.create(
        name="streamlit_study ChatPDF",
        expires_after={"anchor": "last_active_at", "days": 1},
    ).id
    result = client.vector_stores.files.create_and_poll(
        vector_store_id=st.session_state.pdf_store_id,
        file_id=st.session_state.pdf_file_id,
    )
    if result.status != "completed":
        raise ValueError("PDF 색인 생성 실패")
    st.session_state["pdf_ready"] = True
