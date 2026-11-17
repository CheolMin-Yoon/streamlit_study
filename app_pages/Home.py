import base64

import streamlit as st
from openai import OpenAIError

from common import IMAGE_MODEL, TEXT_MODEL, require_client, show_api_error

st.title("텍스트와 이미지 생성")
st.caption("질문에 답을 받고, 프롬프트로 이미지를 만들어 보세요.")
client = require_client()


@st.cache_data(scope="session", show_spinner=False, max_entries=32)
def ask(question, credential_version, _client):
    """세션과 API Key별 동일 질문의 결과 재사용"""
    response = _client.responses.create(
        model=TEXT_MODEL,
        input=question,
        store=False,
    )
    if response.status != "completed" or not response.output_text:
        raise ValueError("텍스트 응답 미완료")
    return response.output_text


st.subheader("질문하기")
with st.form("question_form"):
    question = st.text_area("질문", placeholder="Streamlit의 Session State를 설명해 줘")
    ask_submitted = st.form_submit_button("답변 생성")

if ask_submitted:
    if question.strip():
        try:
            with st.spinner("답변을 생성하고 있습니다..."):
                st.session_state["home_answer"] = ask(
                    question.strip(), st.session_state.credential_version, client
                )
        except (OpenAIError, ValueError) as error:
            show_api_error(error)
    else:
        st.warning("질문을 입력해 주세요.")
if "home_answer" in st.session_state:
    st.markdown(st.session_state.home_answer)

st.divider()
st.subheader("이미지 만들기")
with st.form("image_form"):
    prompt = st.text_area(
        "이미지 프롬프트", placeholder="도서관에서 책을 읽는 고양이 수채화"
    )
    image_submitted = st.form_submit_button("이미지 생성")

if image_submitted:
    if prompt.strip():
        try:
            with st.spinner(
                "이미지를 생성하고 있습니다. 수십 초 정도 걸릴 수 있습니다..."
            ):
                result = client.images.generate(
                    model=IMAGE_MODEL, prompt=prompt.strip()
                )
                if not result.data or not result.data[0].b64_json:
                    raise ValueError("이미지 응답 누락")
                st.session_state["home_image"] = base64.b64decode(
                    result.data[0].b64_json, validate=True
                )
        except (OpenAIError, ValueError) as error:
            show_api_error(error)
    else:
        st.warning("이미지 프롬프트를 입력해 주세요.")
if "home_image" in st.session_state:
    st.image(st.session_state.home_image, caption="생성한 이미지")
