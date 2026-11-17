import streamlit as st
from openai import OpenAI, OpenAIError

from common import IMAGE_MODEL, TEXT_MODEL, delete_pdf, show_api_error

st.set_page_config(page_title="Streamlit Study", page_icon="📚")

with st.sidebar:
    st.title("📚 Streamlit Study")
    api_key = st.text_input("OpenAI API Key", type="password", key="api_key").strip()
    st.caption("API Key는 현재 세션에서만 사용합니다.")
    st.caption(f"텍스트: {TEXT_MODEL}\n\n이미지: {IMAGE_MODEL}")

client = st.session_state.get("openai_client")
if api_key != (client.api_key if client else ""):
    if client:
        try:
            delete_pdf(client)
        except OpenAIError as error:
            show_api_error(error)
            st.warning(
                "이전 PDF 자원 삭제 후 API Key를 변경합니다. 잠시 후 다시 시도해 주세요."
            )
            st.stop()
        client.close()
    for key in ("chat_messages", "library_messages", "home_answer", "home_image"):
        st.session_state.pop(key, None)
    st.session_state["credential_version"] = (
        st.session_state.get("credential_version", 0) + 1
    )
    if api_key:
        st.session_state["openai_client"] = OpenAI(api_key=api_key)
    else:
        st.session_state.pop("openai_client", None)

page = st.navigation(
    [
        st.Page("app_pages/Home.py", title="홈", icon=":material/home:", default=True),
        st.Page("app_pages/Chat.py", title="일반 대화", icon=":material/chat:"),
        st.Page(
            "app_pages/Chatbot.py", title="도서관 챗봇", icon=":material/local_library:"
        ),
        st.Page(
            "app_pages/ChatPDF.py", title="PDF 대화", icon=":material/picture_as_pdf:"
        ),
    ]
)
page.run()
