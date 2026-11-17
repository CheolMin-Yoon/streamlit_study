# Streamlit Study

`21_Lab.pdf`의 실습 3~7을 구현한 Streamlit 앱입니다. 실습 8을 위한 배포 절차도 포함합니다.

## 실행

```bash
cd /home/frlab/streamlit_study
source .venv/bin/activate
streamlit run streamlit_app.py
```

처음 설치하는 컴퓨터에서는 다음 명령으로 가상환경과 패키지를 준비합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

브라우저에서 `http://localhost:8501`을 열고 사이드바에 본인의 OpenAI API Key를 입력합니다.
Codespaces에서는 터미널의 연결 링크 또는 포트 8501의 전달된 주소를 엽니다.
API 사용에 따른 비용은 입력한 Key의 계정에 청구됩니다.

## 페이지

| 페이지 파일 | 기능 |
| --- | --- |
| `app_pages/Home.py` | Responses API 질문 응답, 세션별 `st.cache_data`, 이미지 생성 |
| `app_pages/Chat.py` | 대화 기록 유지, 스트리밍 응답, Clear 콜백 |
| `app_pages/Chatbot.py` | 공식 도서관 규정을 `instructions`로 전달하는 챗봇 |
| `app_pages/ChatPDF.py` | PDF 한 개 업로드, File Search, Clear와 Leave |

진입 파일은 `streamlit_app.py`이며 `st.navigation`으로 페이지를 구성합니다.
텍스트 모델은 `gpt-6-luna`, 이미지 모델은 `gpt-image-2.6-flare`입니다.
API Key와 client는 세션에만 유지하며 파일이나 저장소에 기록하지 않습니다.
Key를 바꾸거나 비우면 이전 PDF 자원을 먼저 삭제하고 대화와 생성 결과를 초기화합니다.
질문 결과 캐시는 세션별로 분리하며 Key 변경 전의 캐시를 재사용하지 않습니다.

PDF는 준비 버튼을 누를 때 한 번 업로드·색인하고 이후 대화에서는 저장된 ID를 재사용합니다.
Clear는 해당 페이지의 대화만 지우고, Leave는 원격 검색용 저장소와 업로드 파일까지 삭제합니다.
삭제 실패 시 ID를 남겨 Leave로 다시 시도할 수 있습니다.
파일은 업로드 24시간 후 만료되므로 하루가 지나면 Leave 후 다시 업로드합니다.
검색용 저장소도 마지막 사용 1일 후 만료됩니다. 브라우저를 닫기 전에 Leave를 눌러 주세요.

## 동작 확인

1. 홈에서 동일한 질문을 두 번 제출하여 답변이 유지되는지 확인합니다.
2. 이미지 프롬프트를 제출하여 생성된 이미지가 표시되는지 확인합니다.
3. 일반 대화에서 자기소개 후 이름을 물어보고, Clear 후 새 대화가 시작되는지 확인합니다.
4. 도서관 챗봇에 휴관일과 학부생 대출 권수를 질문합니다.
   자료실은 공휴일·개교기념일, 일반열람실은 설날·추석이 기본 휴관일이며 관장이 조정할 수 있습니다.
   학부생 단행본은 제22조에 따라 10책 이내, 14일입니다.
5. PDF 대화에서 [Attention Is All You Need](https://arxiv.org/pdf/1706.03762)를 업로드하고 내용을 질문합니다.
   Clear 후에도 문서는 유지되고, Leave 후에는 다시 업로드 화면이 보여야 합니다.

외부 API를 호출하지 않는 검증은 다음과 같이 실행합니다.

```bash
python -m unittest discover -s tests -v
```

## GitHub와 Streamlit Community Cloud 배포

1. GitHub에 `streamlit_study` 공개 저장소를 만들고 README 옵션을 켭니다.
2. 해당 저장소를 clone한 뒤 이 폴더의 앱 파일을 복사합니다.
   `.venv`, API Key, `.env`, `secrets.toml`은 복사하거나 올리지 않습니다.
3. GitHub 저장소의 `main`에서 파일 경로를 명시해 stage하고 commit한 뒤 push합니다.
4. [Streamlit Community Cloud](https://share.streamlit.io)에서 Create app을 선택합니다.
5. 저장소, `main` 브랜치, 진입 파일 `streamlit_app.py`를 지정합니다.
6. Python은 3.13 이상을 선택하고 Secrets는 비워 둡니다.
7. 배포된 주소에서 위 동작을 확인하고 해당 주소를 제출합니다.

현재 폴더 생성만으로 GitHub 업로드나 Cloud 배포가 이루어지지는 않습니다.

## 출처

- [OpenAI 공식 문서: Responses 스트리밍](https://developers.openai.com/api/docs/guides/streaming-responses)
- [OpenAI 공식 문서: File Search](https://developers.openai.com/api/docs/guides/tools-file-search)
- [OpenAI 공식 문서: 이미지 생성](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI 공식 문서: 업로드 파일과 만료 정책](https://developers.openai.com/api/reference/resources/files/methods/create)
- [Streamlit 공식 문서: 페이지 구성](https://docs.streamlit.io/develop/concepts/multipage-apps/page-and-navigation)
- [Streamlit 공식 문서: 세션별 캐시](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data)
- [국립부경대학교 공식 규정집 검색결과](https://www.pknu.ac.kr/rule/searchSchRegAndRule.do?keywordArr=&pageIndex=6&query1=&query2=&search=1)
- [국립부경대학교 도서관 대출안내](https://libweb.pknu.ac.kr/service/holdings/circulation/)

`data/library_rules.txt`는 규정집의 2023. 12. 27. 제1316호 본문 제1조~제35조를
공백과 줄바꿈만 정리해 저장한 자료입니다. 실시간 규정 조회 기능은 포함하지 않습니다.
