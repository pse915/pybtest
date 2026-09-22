import json
import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

# Google Sheets libraries are loaded lazily so the worksheet itself can still
# be previewed before credentials are configured.

st.set_page_config(
    page_title="활동지 - 데이터의 구조화",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------------------------------------------
# Google Sheets configuration
# ------------------------------------------------------------
SHEET_HEADERS = [
    "저장시각",
    "제출ID",
    "학년",
    "반",
    "번호",
    "이름",
    "총점",
    "만점",
    "점수율",
]

for i in range(1, 12):
    SHEET_HEADERS.extend([f"빈칸_{i:02d}_입력", f"빈칸_{i:02d}_점수"])

SHEET_HEADERS.extend(
    [
        "활동1_항목2",
        "활동1_담당2",
        "활동1_완료2",
        "활동1_항목3",
        "활동1_담당3",
        "활동1_완료3",
        "활동2_이름2",
        "활동2_생일2",
        "활동2_취미2",
        "활동2_역할2",
        "활동2_이름3",
        "활동2_생일3",
        "활동2_취미3",
        "활동2_역할3",
        "활동4_자유기록",
        "자기점검1",
        "자기점검2",
        "자기점검3",
    ]
)

if "attempt_id" not in st.session_state:
    st.session_state.attempt_id = str(uuid.uuid4())


def _secret_section(name: str):
    try:
        value = st.secrets[name]
        return dict(value)
    except Exception:
        return None


def get_google_service_account_info():
    """Read a service-account JSON-shaped secret from Streamlit Secrets.

    Preferred format:
      [google_service_account]
      type = "service_account"
      project_id = "..."
      private_key = "..."
      client_email = "..."
      ...

    A legacy-compatible [gcp_service_account] section is also accepted.
    """
    info = _secret_section("google_service_account")
    if info:
        return info
    info = _secret_section("gcp_service_account")
    if info:
        return info
    return None


def get_sheet_settings():
    # Preferred grouped secrets format.
    grouped = _secret_section("google_sheets")
    if grouped:
        url = str(grouped.get("spreadsheet_url", "")).strip()
        worksheet = str(grouped.get("worksheet_name", "활동지_응답")).strip() or "활동지_응답"
        return url, worksheet

    # Also accept flat keys to make migration easier.
    try:
        url = str(st.secrets.get("GOOGLE_SHEETS_URL", "")).strip()
    except Exception:
        url = ""
    try:
        worksheet = str(st.secrets.get("GOOGLE_SHEETS_WORKSHEET", "활동지_응답")).strip()
    except Exception:
        worksheet = "활동지_응답"
    return url, worksheet or "활동지_응답"


@st.cache_resource(show_spinner=False)
def get_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    credentials_info = get_google_service_account_info()
    spreadsheet_url, worksheet_name = get_sheet_settings()

    if not credentials_info:
        raise RuntimeError(
            "Streamlit Secrets에 [google_service_account] 또는 [gcp_service_account]가 없습니다."
        )
    if not spreadsheet_url:
        raise RuntimeError(
            "Streamlit Secrets에 Google Sheets 주소(spreadsheet_url)가 없습니다."
        )

    # Service account needs write permission to the spreadsheet.
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_url(spreadsheet_url)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=max(1000, 2),
            cols=len(SHEET_HEADERS),
        )
        worksheet.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")
        return worksheet

    # Create a header when the dedicated worksheet is empty.
    current_header = worksheet.row_values(1)
    if not current_header:
        worksheet.update("A1", [SHEET_HEADERS], value_input_option="USER_ENTERED")

    return worksheet


def _bool_text(value):
    return "TRUE" if bool(value) else "FALSE"


def build_sheet_row(payload):
    now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    blanks = payload.get("blanks", [])
    scores = payload.get("scores", [])

    while len(blanks) < 11:
        blanks.append("")
    while len(scores) < 11:
        scores.append(0)

    student = payload.get("student", {})
    list_rows = payload.get("activity1", {})
    profiles = payload.get("activity2", {})
    self_check = payload.get("selfCheck", [False, False, False])
    while len(self_check) < 3:
        self_check.append(False)

    row = [
        now,
        st.session_state.attempt_id,
        "1학년",
        student.get("class", ""),
        student.get("number", ""),
        student.get("name", ""),
        int(payload.get("score", 0)),
        int(payload.get("maxScore", 11)),
        f"{float(payload.get('scoreRate', 0)):.1f}%",
    ]

    for answer, score in zip(blanks, scores):
        row.extend([answer, int(score)])

    row.extend(
        [
            list_rows.get("item2", ""),
            list_rows.get("person2", ""),
            _bool_text(list_rows.get("done2", False)),
            list_rows.get("item3", ""),
            list_rows.get("person3", ""),
            _bool_text(list_rows.get("done3", False)),
            profiles.get("name2", ""),
            profiles.get("birthday2", ""),
            profiles.get("hobby2", ""),
            profiles.get("role2", ""),
            profiles.get("name3", ""),
            profiles.get("birthday3", ""),
            profiles.get("hobby3", ""),
            profiles.get("role3", ""),
            payload.get("reflection", ""),
            _bool_text(self_check[0]),
            _bool_text(self_check[1]),
            _bool_text(self_check[2]),
        ]
    )
    return row


def save_to_google_sheets(payload):
    worksheet = get_worksheet()
    row = build_sheet_row(payload)
    worksheet.append_row(row, value_input_option="USER_ENTERED")


# ------------------------------------------------------------
# Streamlit page chrome: keep the page visually close to the source HTML.
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    [data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stHeader"] { background: transparent; }
    .stApp { background: #f1f5f9; }
    .block-container { padding-top: 8px; padding-bottom: 8px; max-width: 1100px; }
    div[data-testid="stVerticalBlock"] > div { gap: 0.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# HTML/CSS copied from the uploaded worksheet's structure/styles,
# with non-visual name/data attributes added for saving to Google Sheets.
# ------------------------------------------------------------
HTML = r'''
<div class="app-root">
  <!-- 상단 제어 바 (인쇄 시 숨김) -->
  <header class="container no-print header-bar">
    <div>
      <div class="header-title">📋 활동지 : 데이터의 구조화 (오프라인 단일 파일)</div>
      <div class="header-subtitle">인터넷 연결이 필요 없는 100% 독립 실행 파일입니다. 빈칸을 클릭하거나 단어를 드래그하세요!</div>
    </div>
    <div class="btn-group">
      <button id="check-all" class="btn-success">✓ 자동 채점</button>
      <button id="toggle-answers" class="btn-secondary">💡 정답 보기/숨기기</button>
      <button id="reset-all" class="btn-secondary">↺ 초기화</button>
      <button id="print-a4" class="btn-primary">🖨️ A4 인쇄 / PDF 저장</button>
    </div>
  </header>

  <!-- 단어 보관함 (인쇄 시 숨김) -->
  <div class="container no-print word-bank-card">
    <div class="word-bank-title">
      <span>💡 단어 보관함 (클릭하거나 아래 빈칸으로 드래그하여 입력하세요)</span>
      <span style="font-weight: normal; color: #4338ca;">남은 단어: <strong id="word-count">10</strong>개</span>
    </div>
    <div class="word-chips" id="chips-container">
      <div class="chip" draggable="true">데이터</div>
      <div class="chip" draggable="true">특성</div>
      <div class="chip" draggable="true">정리 및 배열</div>
      <div class="chip" draggable="true">통일된 모양</div>
      <div class="chip" draggable="true">쉽게 찾을</div>
      <div class="chip" draggable="true">관계</div>
      <div class="chip" draggable="true">효율적으로 관리</div>
      <div class="chip" draggable="true">기준</div>
      <div class="chip" draggable="true">소프트웨어 개발 전문가</div>
      <div class="chip" draggable="true">시스템 SW 개발자</div>
      <div class="chip" draggable="true">응용 SW 개발자</div>
    </div>
  </div>

  <!-- 본문 컨테이너 -->
  <div class="container">

    <!-- PAGE 1 (앞면) -->
    <div class="a4-page">
      <div class="page-header">
        <div>
          <span class="badge">중학교 1학년 정보 Ⅱ.데이터</span>
          <h1 class="page-title">활동지 - 데이터의 구조화</h1>
        </div>
        <div class="student-info">
          <span>1학년</span>
          <input type="text" data-field="student.class" aria-label="반" style="width: 25px; text-align: center;">
          <span>반</span>
          <input type="text" data-field="student.number" aria-label="번호" style="width: 25px; text-align: center;">
          <span>번</span>
          <span style="margin-left: 6px;">이름:</span>
          <input type="text" data-field="student.name" aria-label="이름" style="width: 65px;">
        </div>
      </div>

      <!-- 1. 데이터 구조화의 뜻 -->
      <div class="section-title">1. 데이터 구조화의 뜻과 필요성</div>
      <div class="section-box">
        <strong>[데이터 구조화의 정의]</strong> 전달하려고 하는
        <input type="text" class="blank-input" data-index="1" data-ans="데이터" placeholder="( ① 빈칸 )" style="width: 90px;">
        의 내용 요소들을
        <input type="text" class="blank-input" data-index="2" data-ans="특성" placeholder="( ② 빈칸 )" style="width: 80px;">
        에 맞게
        <input type="text" class="blank-input" data-index="3" data-ans="정리 및 배열" placeholder="( ③ 빈칸 )" style="width: 105px;">
        하여
        <input type="text" class="blank-input" data-index="4" data-ans="통일된 모양" placeholder="( ④ 빈칸 )" style="width: 105px;">
        으로 표현하는 것.
      </div>

      <!-- 2. 데이터 구조화 이유 4가지 표 -->
      <div class="section-title">데이터 구조화를 하는 주요 이유 4가지</div>
      <table>
        <thead>
          <tr>
            <th style="width: 50%;">데이터 구조화를 하는 목적</th>
            <th style="width: 50%;">실생활 대표 예시</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              ① 데이터를
              <input type="text" class="blank-input" data-index="5" data-ans="쉽게 찾을" placeholder="( 빈칸 )" style="width: 85px;">
              수 있다.
            </td>
            <td style="color: #64748b;">학번순 학생 명부, 도서관 십진분류 청구기호</td>
          </tr>
          <tr>
            <td>
              ② 데이터 사이의
              <input type="text" class="blank-input" data-index="6" data-ans="관계" placeholder="( 빈칸 )" style="width: 75px;">
              을 쉽게 이해할 수 있다.
            </td>
            <td style="color: #64748b;">가족 가계도, 회사 및 학교 조직도</td>
          </tr>
          <tr>
            <td>③ 빠지거나 잘못된 내용(오류 및 결측치)을 쉽게 파악할 수 있다.</td>
            <td style="color: #64748b;">용돈 기입장 누락 확인, 시간표 중복 체크</td>
          </tr>
          <tr>
            <td>
              ④ 데이터를
              <input type="text" class="blank-input" data-index="7" data-ans="효율적으로 관리" placeholder="( 빈칸 )" style="width: 120px;">
              할 수 있다.
            </td>
            <td style="color: #64748b;">연간 통계 분석 및 데이터베이스 저장</td>
          </tr>
        </tbody>
      </table>

      <!-- 3. 구조화의 3가지 형태 (목록 -> 표 -> 다이어그램) -->
      <div class="section-title">2. 데이터는 어떤 방법으로 구조화할 수 있을까? (순서: 목록 ➔ 표 ➔ 다이어그램)</div>
      <div class="methods-grid">
        <div class="method-card card-amber">
          <strong style="color: #92400e;">1. 목록 (List)</strong>
          <p style="margin-top: 4px;">일정한 <input type="text" class="blank-input" data-index="8" data-ans="기준" placeholder="( 빈칸 )" style="width: 60px;"> 에 맞추어 항목을 차례대로 나열</p>
          <small style="color: #b45309;">예: 준비물 목록, 장보기 리스트</small>
        </div>
        <div class="method-card card-sky">
          <strong style="color: #0369a1;">2. 표 (Table)</strong>
          <p style="margin-top: 4px;"><strong>행(가로)</strong>과 <strong>열(세로)</strong>의 격자 구조로 구성</p>
          <small style="color: #0284c7;">예: 학교 시간표, 주소록</small>
        </div>
        <div class="method-card card-indigo">
          <strong style="color: #6d28d9;">3. 다이어그램 (Diagram)</strong>
          <p style="margin-top: 4px;">점, 선, 도형, 화살표 등으로 시각화</p>
          <small style="color: #7c3aed;">예: 지하철 노선도, 계층 조직도</small>
        </div>
      </div>

      <!-- [활동 1] 목록 만들기 실습 -->
      <div class="section-title">[활동 1] 목록(List) 만들기 실습 : 우리 모둠 준비물 체크리스트</div>
      <table>
        <thead>
          <tr>
            <th style="width: 50px; text-align: center;">순번</th>
            <th>점검 및 준비 항목</th>
            <th style="width: 120px;">담당자</th>
            <th style="width: 80px; text-align: center;">완료</th>
          </tr>
        </thead>
        <tbody>
          <tr style="background: #f8fafc;">
            <td style="text-align: center; font-weight: 700;">1 (샘플)</td>
            <td>정보 교과서 및 필기도구 챙기기</td>
            <td>나</td>
            <td style="text-align: center; color: #16a34a; font-weight: 700;">✓ 완료</td>
          </tr>
          <tr>
            <td style="text-align: center; color: #94a3b8;">2</td>
            <td><input type="text" data-field="activity1.item2" placeholder="점검 항목을 입력하세요"></td>
            <td><input type="text" data-field="activity1.person2" placeholder="담당 친구"></td>
            <td style="text-align: center;"><input type="checkbox" data-field="activity1.done2"></td>
          </tr>
          <tr>
            <td style="text-align: center; color: #94a3b8;">3</td>
            <td><input type="text" data-field="activity1.item3" placeholder="점검 항목을 입력하세요"></td>
            <td><input type="text" data-field="activity1.person3" placeholder="담당 친구"></td>
            <td style="text-align: center;"><input type="checkbox" data-field="activity1.done3"></td>
          </tr>
        </tbody>
      </table>

      <!-- [활동 2] 표 만들기 실습 -->
      <div class="section-title">[활동 2] 표(Table) 만들기 실습 : 우리 모둠 친구 프로필 데이터 (1번 행 샘플)</div>
      <table>
        <thead>
          <tr>
            <th style="width: 50px; text-align: center;">번호</th>
            <th>친구 이름</th>
            <th>생일 (월/일)</th>
            <th>취미 및 특기</th>
            <th>모둠 내 역할</th>
          </tr>
        </thead>
        <tbody>
          <tr style="background: #f8fafc;">
            <td style="text-align: center; font-weight: 700;">1 (샘플)</td>
            <td>김민수</td>
            <td>3월 15일</td>
            <td>축구, 코딩</td>
            <td>자료 조사 및 발표</td>
          </tr>
          <tr>
            <td style="text-align: center; color: #94a3b8;">2</td>
            <td><input type="text" data-field="activity2.name2" placeholder="이름"></td>
            <td><input type="text" data-field="activity2.birthday2" placeholder="생일"></td>
            <td><input type="text" data-field="activity2.hobby2" placeholder="취미"></td>
            <td><input type="text" data-field="activity2.role2" placeholder="역할"></td>
          </tr>
          <tr>
            <td style="text-align: center; color: #94a3b8;">3</td>
            <td><input type="text" data-field="activity2.name3" placeholder="이름"></td>
            <td><input type="text" data-field="activity2.birthday3" placeholder="생일"></td>
            <td><input type="text" data-field="activity2.hobby3" placeholder="취미"></td>
            <td><input type="text" data-field="activity2.role3" placeholder="역할"></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- PAGE 2 (뒷면) -->
    <div class="a4-page">
      <div class="page-header">
        <div>
          <h2 class="page-title">활동지 - 데이터의 구조화 (뒷면: 다이어그램과 차트)</h2>
        </div>
      </div>

      <!-- [활동 3] 계층 다이어그램 만들기 -->
      <div class="section-title">[활동 3] 다이어그램 만들기 : (가) 글을 읽고 (나) 계층형 다이어그램 빈칸 채우기</div>
      <div class="section-box" style="background: #ffffff; border-color: #cbd5e1;">
        <strong>(가) 제시문 :</strong> "소프트웨어 개발 전문가는 시스템 SW 개발자와 응용 SW 개발자로 나뉜다. 시스템 SW 개발자는 운영체제 프로그래머와 임베디드 프로그래머가 있다. 응용 SW 개발자는 응용 SW 프로그래머, 네트워크 프로그래머, 컴퓨터 및 모바일 게임 프로그래머가 있다."
      </div>

      <div class="tree-box">
        <div class="tree-level-1">
          <small style="color: #0284c7; display: block; font-weight: 700;">최상위 직무 분류</small>
          <input type="text" class="blank-input" data-index="9" data-ans="소프트웨어 개발 전문가" placeholder="( 빈칸 채우기 )" style="width: 170px;">
        </div>
        <div class="tree-arrow">│<br>▼</div>
        <div class="tree-level-2">
          <div class="sub-tree-card">
            <strong style="color: #0284c7; font-size: 11px;">↙ 하위 분류 1</strong>
            <input type="text" class="blank-input" data-index="10" data-ans="시스템 SW 개발자" placeholder="( 빈칸 )" style="width: 100%; margin: 4px 0;">
            <ul style="padding-left: 18px; font-size: 11px; color: #475569; margin-top: 4px;">
              <li>운영체제 프로그래머</li>
              <li>임베디드 프로그래머</li>
            </ul>
          </div>
          <div class="sub-tree-card">
            <strong style="color: #0284c7; font-size: 11px;">↘ 하위 분류 2</strong>
            <input type="text" class="blank-input" data-index="11" data-ans="응용 SW 개발자" placeholder="( 빈칸 )" style="width: 100%; margin: 4px 0;">
            <ul style="padding-left: 18px; font-size: 11px; color: #475569; margin-top: 4px;">
              <li>응용 SW 프로그래머</li>
              <li>네트워크 프로그래머</li>
              <li>모바일 게임 프로그래머</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- [활동 4] 실전 구조화 & 막대그래프 -->
      <div class="section-title">[활동 4] 민호의 체험학습 계획 구조화 및 통계 막대그래프 다이어그램</div>
      <div class="section-box">
        "4월에는 봄꽃을 보러 경복궁, 창덕궁, 종묘 등을 방문할 예정이다. 서울 지하철 3호선을 탄다. 5월에는 가족과 함께 지하철 2호선을 타고 미술관이 있는 덕수궁에 간다. 6월에는 선조들의 얼을 기리고자 전쟁기념관과 국립중앙박물관을 방문하며 지하철 4호선을 탄다."
      </div>

      <div class="chart-container">
        <div style="font-size: 12px; font-weight: 700; margin-bottom: 8px;">📊 호선별 방문 장소 수 비교 (막대그래프 다이어그램)</div>
        <div class="chart-row">
          <span class="chart-label" style="color: #ea580c;">3호선 (4월)</span>
          <div class="chart-bar-bg">
            <div class="chart-bar-fill bar-orange">3곳 (경복궁, 창덕궁, 종묘)</div>
          </div>
        </div>
        <div class="chart-row">
          <span class="chart-label" style="color: #16a34a;">2호선 (5월)</span>
          <div class="chart-bar-bg">
            <div class="chart-bar-fill bar-green">1곳 (덕수궁)</div>
          </div>
        </div>
        <div class="chart-row">
          <span class="chart-label" style="color: #0284c7;">4호선 (6월)</span>
          <div class="chart-bar-bg">
            <div class="chart-bar-fill bar-blue">2곳 (전쟁기념관, 국립중앙박물관)</div>
          </div>
        </div>
      </div>

      <textarea data-field="reflection" rows="3" placeholder="자신이 정리한 구조화 내용(목록/표/노선 흐름)을 자유롭게 기록해 보세요..." style="width: 100%; padding: 8px; border: 1px solid #cbd5e1; border-radius: 8px; font-family: inherit; font-size: 12px; outline: none; margin-bottom: 16px;"></textarea>

      <!-- 자기 배움 점검 -->
      <div class="section-title">스스로 배움 점검하기</div>
      <div class="section-box" style="margin-bottom: 0;">
        <label style="display: block; margin-bottom: 4px; cursor: pointer;">
          <input type="checkbox" data-field="selfCheck.1"> 1. 데이터 구조화의 뜻과 필요한 이유 4가지를 설명할 수 있다.
        </label>
        <label style="display: block; margin-bottom: 4px; cursor: pointer;">
          <input type="checkbox" data-field="selfCheck.2"> 2. 데이터의 특성에 맞춰 목록, 표, 다이어그램을 올바르게 선택할 수 있다.
        </label>
        <label style="display: block; cursor: pointer;">
          <input type="checkbox" data-field="selfCheck.3"> 3. 줄글 데이터를 표나 계층형/차트 다이어그램으로 직접 표현할 수 있다.
        </label>
      </div>
    </div>
  </div>
</div>
'''

CSS = r'''
:host {
  display: block;
  width: 100%;
  background: #f1f5f9;
  color: #1e293b;
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", "맑은 고딕", "Pretendard", Roboto, sans-serif;
  line-height: 1.5;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
.app-root { background-color: #f1f5f9; padding: 16px; }
.container { max-width: 900px; margin: 0 auto; }
.header-bar {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 12px 18px;
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.header-title { font-size: 16px; font-weight: 700; color: #0f172a; }
.header-subtitle { font-size: 12px; color: #64748b; margin-top: 2px; }
.btn-group { display: flex; gap: 8px; flex-wrap: wrap; }
button {
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s ease;
}
.btn-primary { background: #2563eb; color: #ffffff; }
.btn-primary:hover { background: #1d4ed8; }
.btn-success { background: #059669; color: #ffffff; }
.btn-success:hover { background: #047857; }
.btn-secondary { background: #f8fafc; color: #334155; border-color: #cbd5e1; }
.btn-secondary:hover { background: #e2e8f0; }
.word-bank-card {
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 20px;
}
.word-bank-title {
  font-size: 12px;
  font-weight: 700;
  color: #312e81;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
}
.word-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  background: #ffffff;
  border: 1px solid #a5b4fc;
  color: #3730a3;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: grab;
  user-select: none;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.chip:hover { background: #e0e7ff; }
.a4-page {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 28px 32px;
  margin-bottom: 24px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.04);
}
.page-header {
  border-bottom: 2px solid #0f172a;
  padding-bottom: 12px;
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
.page-title { font-size: 20px; font-weight: 800; color: #0f172a; }
.badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  background: #eff6ff;
  color: #1d4ed8;
  padding: 2px 8px;
  border-radius: 4px;
  margin-bottom: 4px;
}
.student-info {
  font-size: 13px;
  display: flex;
  gap: 6px;
  align-items: center;
  background: #f8fafc;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}
.student-info input {
  border: none;
  border-bottom: 1px solid #94a3b8;
  background: transparent;
  padding: 2px 4px;
  font-size: 13px;
  font-weight: 600;
  outline: none;
}
.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-title::before {
  content: "";
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2563eb;
}
.section-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  line-height: 1.7;
}
input.blank-input {
  border: 1px solid #94a3b8;
  border-radius: 4px;
  background: #ffffff;
  padding: 3px 6px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  outline: none;
  transition: all 0.15s ease;
  margin: 0 3px;
}
input.blank-input:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
}
input.blank-input.correct {
  background-color: #dcfce7 !important;
  border-color: #16a34a !important;
  color: #15803d !important;
}
input.blank-input.wrong {
  background-color: #fee2e2 !important;
  border-color: #dc2626 !important;
  color: #b91c1c !important;
}
table { width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 16px; }
th, td { border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }
th { background: #f1f5f9; color: #334155; font-weight: 700; }
td input[type="text"] { width: 100%; border: none; background: transparent; font-size: 12px; outline: none; }
.methods-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 16px; }
.method-card { border-radius: 8px; padding: 10px 12px; font-size: 12px; }
.card-amber { background: #fef3c7; border: 1px solid #fde68a; }
.card-sky { background: #e0f2fe; border: 1px solid #bae6fd; }
.card-indigo { background: #ede9fe; border: 1px solid #ddd6fe; }
.tree-box { background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 16px; text-align: center; margin-bottom: 16px; }
.tree-level-1 { display: inline-block; background: #ffffff; border: 2px solid #0284c7; padding: 8px 16px; border-radius: 8px; }
.tree-arrow { color: #0284c7; font-size: 14px; font-weight: 700; margin: 8px 0; }
.tree-level-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; text-align: left; }
.sub-tree-card { background: #ffffff; border: 1px solid #7dd3fc; border-radius: 8px; padding: 10px 12px; }
.chart-container { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; }
.chart-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font-size: 12px; }
.chart-label { width: 90px; font-weight: 700; }
.chart-bar-bg { flex: 1; height: 22px; background: #e2e8f0; border-radius: 12px; overflow: hidden; }
.chart-bar-fill { height: 100%; color: #ffffff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; border-radius: 12px; }
.bar-orange { background: #f97316; width: 75%; }
.bar-green { background: #10b981; width: 25%; }
.bar-blue { background: #0ea5e9; width: 50%; }
@media (max-width: 720px) {
  .app-root { padding: 8px; }
  .a4-page { padding: 20px 16px; }
  .methods-grid { grid-template-columns: 1fr; }
  .tree-level-2 { grid-template-columns: 1fr; }
  .header-bar { align-items: flex-start; }
  .student-info { flex-wrap: wrap; }
}
'''

# ------------------------------------------------------------
# JavaScript: preserve original interactions and send one submission event
# to Python only when the original "자동 채점" button is pressed.
# ------------------------------------------------------------
JS = r'''
export default function(component) {
  const { parentElement, setTriggerValue, setStateValue, data } = component;
  let focusedElement = null;
  let showingAnswers = false;
  let initialized = false;

  const root = parentElement.querySelector('.app-root');
  if (!root) return;

  function setFocus(el) {
    focusedElement = el;
  }

  function normalize(value) {
    return (value || '').trim().replace(/\s+/g, '');
  }

  function checkSingle(input) {
    const val = normalize(input.value);
    const ans = normalize(input.getAttribute('data-ans') || '');
    if (!val) {
      input.classList.remove('correct', 'wrong');
      return false;
    }
    if (val === ans) {
      input.classList.add('correct');
      input.classList.remove('wrong');
      return true;
    }
    input.classList.add('wrong');
    input.classList.remove('correct');
    return false;
  }

  function fillFocus(text) {
    if (!focusedElement) return;
    focusedElement.value = text;
    checkSingle(focusedElement);
    focusedElement.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function onDragStart(e) {
    e.dataTransfer.setData('text/plain', e.target.innerText.trim());
  }

  function onDrop(e) {
    e.preventDefault();
    const text = e.dataTransfer.getData('text/plain');
    if (text && e.target.matches('input.blank-input')) {
      e.target.value = text;
      checkSingle(e.target);
      e.target.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function collectField(selector) {
    const el = root.querySelector(selector);
    return el ? el.value || '' : '';
  }

  function isChecked(selector) {
    const el = root.querySelector(selector);
    return !!(el && el.checked);
  }

  function collectFormState() {
    const blanks = Array.from(root.querySelectorAll('input.blank-input'))
      .sort((a,b) => Number(a.dataset.index) - Number(b.dataset.index));
    return {
      student: {
        class: collectField('[data-field="student.class"]'),
        number: collectField('[data-field="student.number"]'),
        name: collectField('[data-field="student.name"]')
      },
      blanks: blanks.map(input => input.value || ''),
      activity1: {
        item2: collectField('[data-field="activity1.item2"]'),
        person2: collectField('[data-field="activity1.person2"]'),
        done2: isChecked('[data-field="activity1.done2"]'),
        item3: collectField('[data-field="activity1.item3"]'),
        person3: collectField('[data-field="activity1.person3"]'),
        done3: isChecked('[data-field="activity1.done3"]')
      },
      activity2: {
        name2: collectField('[data-field="activity2.name2"]'),
        birthday2: collectField('[data-field="activity2.birthday2"]'),
        hobby2: collectField('[data-field="activity2.hobby2"]'),
        role2: collectField('[data-field="activity2.role2"]'),
        name3: collectField('[data-field="activity2.name3"]'),
        birthday3: collectField('[data-field="activity2.birthday3"]'),
        hobby3: collectField('[data-field="activity2.hobby3"]'),
        role3: collectField('[data-field="activity2.role3"]')
      },
      reflection: collectField('[data-field="reflection"]'),
      selfCheck: [
        isChecked('[data-field="selfCheck.1"]'),
        isChecked('[data-field="selfCheck.2"]'),
        isChecked('[data-field="selfCheck.3"]')
      ]
    };
  }

  function collectData(scoresOverride=null) {
    const form = collectFormState();
    const blanks = Array.from(root.querySelectorAll('input.blank-input'))
      .sort((a,b) => Number(a.dataset.index) - Number(b.dataset.index));
    const scores = scoresOverride || blanks.map(input => checkSingle(input) ? 1 : 0);
    const score = scores.reduce((a,b) => a + b, 0);
    return {
      ...form,
      scores: scores,
      score: score,
      maxScore: blanks.length,
      scoreRate: blanks.length ? (score / blanks.length) * 100 : 0
    };
  }

  function syncState() {
    setStateValue('form', collectFormState());
  }

  let syncTimer = null;
  function scheduleStateSync() {
    clearTimeout(syncTimer);
    syncTimer = setTimeout(syncState, 350);
  }

  function applyFormState(form) {
    if (!form) return;
    const fields = [
      ['[data-field="student.class"]', form.student?.class || ''],
      ['[data-field="student.number"]', form.student?.number || ''],
      ['[data-field="student.name"]', form.student?.name || ''],
      ['[data-field="activity1.item2"]', form.activity1?.item2 || ''],
      ['[data-field="activity1.person2"]', form.activity1?.person2 || ''],
      ['[data-field="activity1.item3"]', form.activity1?.item3 || ''],
      ['[data-field="activity1.person3"]', form.activity1?.person3 || ''],
      ['[data-field="activity2.name2"]', form.activity2?.name2 || ''],
      ['[data-field="activity2.birthday2"]', form.activity2?.birthday2 || ''],
      ['[data-field="activity2.hobby2"]', form.activity2?.hobby2 || ''],
      ['[data-field="activity2.role2"]', form.activity2?.role2 || ''],
      ['[data-field="activity2.name3"]', form.activity2?.name3 || ''],
      ['[data-field="activity2.birthday3"]', form.activity2?.birthday3 || ''],
      ['[data-field="activity2.hobby3"]', form.activity2?.hobby3 || ''],
      ['[data-field="activity2.role3"]', form.activity2?.role3 || ''],
      ['[data-field="reflection"]', form.reflection || '']
    ];
    fields.forEach(([selector, value]) => {
      const el = root.querySelector(selector);
      if (el && el.value !== value) el.value = value;
    });

    const blanks = Array.from(root.querySelectorAll('input.blank-input'))
      .sort((a,b) => Number(a.dataset.index) - Number(b.dataset.index));
    const answers = Array.isArray(form.blanks) ? form.blanks : [];
    blanks.forEach((el, i) => {
      const value = answers[i] || '';
      if (el.value !== value) el.value = value;
    });

    const checks = [
      ['[data-field="activity1.done2"]', !!form.activity1?.done2],
      ['[data-field="activity1.done3"]', !!form.activity1?.done3],
      ['[data-field="selfCheck.1"]', !!form.selfCheck?.[0]],
      ['[data-field="selfCheck.2"]', !!form.selfCheck?.[1]],
      ['[data-field="selfCheck.3"]', !!form.selfCheck?.[2]]
    ];
    checks.forEach(([selector, value]) => {
      const el = root.querySelector(selector);
      if (el) el.checked = value;
    });
  }

  function checkAllAnswers() {
    const blanks = Array.from(root.querySelectorAll('input.blank-input'));
    let correct = 0;
    const scores = [];
    blanks.forEach(input => {
      const ok = checkSingle(input);
      const score = ok ? 1 : 0;
      scores.push(score);
      if (ok) correct++;
    });
    alert('자동 채점 완료! 총 ' + blanks.length + '개 빈칸 중 ' + correct + '개를 맞혔습니다.');
    const payload = collectData(scores);
    setTriggerValue('submit', JSON.stringify(payload));
  }

  function toggleAnswers() {
    showingAnswers = !showingAnswers;
    const inputs = Array.from(root.querySelectorAll('input.blank-input'));
    inputs.forEach(input => {
      if (showingAnswers) {
        input.value = input.getAttribute('data-ans') || '';
        input.classList.add('correct');
        input.classList.remove('wrong');
      } else {
        input.value = '';
        input.classList.remove('correct', 'wrong');
      }
    });
    syncState();
  }

  function resetAll() {
    if (!confirm('모든 입력 내용을 초기화하시겠습니까?')) return;
    root.querySelectorAll('input.blank-input').forEach(input => {
      input.value = '';
      input.classList.remove('correct', 'wrong');
    });
    root.querySelectorAll('input[type="text"]:not(.blank-input)').forEach(input => {
      input.value = '';
    });
    root.querySelectorAll('textarea').forEach(area => area.value = '');
    root.querySelectorAll('input[type="checkbox"]').forEach(box => box.checked = false);
    syncState();
  }

  function printA4() {
    const pages = root.querySelector('.container')?.innerHTML || '';
    const printCss = `
      * { box-sizing: border-box; margin:0; padding:0; }
      body { font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","맑은 고딕",Pretendard,Roboto,sans-serif; background:#fff; color:#1e293b; line-height:1.5; }
      .container { max-width:900px; margin:0 auto; }
      .a4-page { background:#fff; border:none !important; box-shadow:none !important; padding:15mm !important; margin:0 !important; page-break-after:always; }
      .no-print { display:none !important; }
      input.blank-input { border-bottom:1px solid #000 !important; border-top:none !important; border-left:none !important; border-right:none !important; }
      @page { size:A4; margin:0; }
    `;
    const w = window.open('', '_blank', 'width=1000,height=900');
    if (!w) return;
    w.document.write('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>활동지 - 데이터의 구조화</title><style>' + printCss + '</style></head><body>' + pages + '</body></html>');
    w.document.close();
    setTimeout(() => { w.focus(); w.print(); }, 250);
  }

  // Initial event wiring.
  if (!initialized) {
    initialized = true;
    applyFormState(data?.form || null);

    root.querySelectorAll('input.blank-input').forEach(input => {
      input.addEventListener('focus', () => setFocus(input));
      input.addEventListener('input', () => { checkSingle(input); scheduleStateSync(); });
      input.addEventListener('dragover', e => e.preventDefault());
      input.addEventListener('drop', onDrop);
    });

    root.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('dragstart', onDragStart);
      chip.addEventListener('click', () => fillFocus(chip.innerText));
    });

    root.querySelectorAll('input[type="text"]:not(.blank-input), input[type="checkbox"], textarea').forEach(el => {
      el.addEventListener('input', scheduleStateSync);
      el.addEventListener('change', scheduleStateSync);
    });

    root.querySelector('#check-all')?.addEventListener('click', checkAllAnswers);
    root.querySelector('#toggle-answers')?.addEventListener('click', toggleAnswers);
    root.querySelector('#reset-all')?.addEventListener('click', resetAll);
    root.querySelector('#print-a4')?.addEventListener('click', printA4);
  }
}
'''

# Mount the custom component. This is the current Streamlit Components v2
# mechanism and lets trusted HTML/CSS/JS communicate with the Python app.
worksheet_component = st.components.v2.component(
    "data_structure_worksheet_v1",
    html=HTML,
    css=CSS,
    js=JS,
    isolate_styles=True,
)

# Components v2 state persists through Streamlit reruns. The key lets the
# current form state live in st.session_state and be fed back to the JS UI.
component_state = st.session_state.get("worksheet", {})
current_form = component_state.get("form", {})
result = worksheet_component(
    data={"form": current_form},
    default={"form": current_form},
    on_form_change=lambda: None,
    on_submit_change=lambda: None,
    key="worksheet",
)

# ------------------------------------------------------------
# Handle Google Sheets save after "자동 채점".
# ------------------------------------------------------------
if getattr(result, "submit", None):
    try:
        payload = json.loads(result.submit)
        save_to_google_sheets(payload)
        st.success(
            f"자동 채점 결과 저장 완료 · {int(payload.get('score', 0))}/{int(payload.get('maxScore', 11))}점 · Google Sheets에 입력 내용과 칸별 점수를 저장했습니다."
        )
    except Exception as exc:
        st.error(f"자동 채점 결과는 화면에서 계산되었지만 Google Sheets 저장에 실패했습니다: {exc}")
