import streamlit as st

from common import clear_messages, render_chat

st.title("일반 대화")
st.caption("이 페이지의 대화 내용을 기억하며 답변합니다.")
st.button("Clear", on_click=clear_messages, args=("chat_messages",))
render_chat("chat_messages", "사용자의 질문에 한국어로 친절하고 정확하게 답하세요.")
