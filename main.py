# app.py
import streamlit as st
import pandas as pd
import requests
import json
import io
import time
import re



st.set_page_config(page_title="사업자 상태조회 배치", layout="wide")

st.title("국세청 사업자 상태조회 서비스")


def get_service_key():
    key = None
    try:
        key = st.secrets.get("GUKSECHEONG_SERVICE_KEY", None)
    except Exception:
        key = None
    if key:
        return key
    with st.expander("인증 설정", expanded=True):
        key = st.text_input(
            "국세청 serviceKey (URL 인코딩 형태)",
            value="",
            type="password",
            help="st.secrets 미설정 시 여기에 입력. 화면에 마스킹 처리됨."
        )
    return key
    
# 1) 입력 영역
with st.sidebar:
    st.header("설정")
    batch_size = st.number_input("배치 크기", min_value=1, max_value=100, value=100, step=1)
    throttle = st.number_input("요청 간 대기(초)", min_value=0.0, max_value=5.0, value=0.5, step=0.1)
    strip_non_digits = st.checkbox("숫자만 추출하여 조회", value=True, help="하이픈 등 제거")


st.markdown("#### 1) 엑셀 업로드")
uploaded = st.file_uploader("xlsx만 허용", type=["xlsx"])

def sanitize_bno_series(s: pd.Series, digits_only: bool = True) -> pd.Series:
    s = s.astype(str).str.strip()
    if digits_only:
        s = s.apply(lambda x: re.sub(r"\D", "", x))
    return s.replace({"": pd.NA}).dropna()

def call_api(bno_list, key, batch_size=100, sleep_sec=0.5):
    url = f"https://api.odcloud.kr/api/nts-businessman/v1/status?serviceKey={key}"
    headers = {"Content-Type": "application/json"}
    all_rows = []
    progress = st.progress(0)
    logs = st.empty()
    total = len(bno_list)
    for i in range(0, total, batch_size):
        batch = bno_list[i:i+batch_size]
        payload = {"b_no": batch}
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                rows = result.get("data", [])
                all_rows.extend(rows)
                logs.text(f"{i+1}~{i+len(batch)}건 요청 완료 • 누적 {len(all_rows)}건")
            else:
                logs.text(f"요청 실패 • 코드 {resp.status_code} • {resp.text[:200]}")
        except Exception as e:
            logs.text(f"예외 발생 • {type(e).__name__}: {e}")
        progress.progress(min((i+batch_size)/total, 1.0))
        time.sleep(sleep_sec)
    return pd.DataFrame(all_rows)

result_df = None
if uploaded is not None:
    try:
        df = pd.read_excel(uploaded, dtype=str)
    except Exception as e:
        st.error(f"엑셀 로드 실패: {e}")
        st.stop()

    if df.shape[1] < 1:
        st.error("엑셀의 첫 번째 컬럼에 사업자등록번호 필요")
        st.stop()    

        
result_df = None
if uploaded is not None:
    try:
        df = pd.read_excel(uploaded, dtype=str)
    except Exception as e:
        st.error(f"엑셀 로드 실패: {e}")
        st.stop()

    if df.shape[1] < 1:
        st.error("엑셀의 첫 번째 컬럼에 사업자등록번호 필요")
        st.stop()

    st.markdown("#### 2) 데이터 확인")
    st.write("첫 5행 미리보기")
    st.dataframe(df.head())

    # 첫 컬럼을 사업자번호로 사용
    bno_series = sanitize_bno_series(df.iloc[:, 0], digits_only=strip_non_digits)
    business_numbers = bno_series.tolist()

    st.info(f"유효 사업자번호 {len(business_numbers)}건 인식")
    service_key = get_service_key()
    run = st.button("조회 실행")
    if run:
        if len(business_numbers) == 0:
            st.warning("조회할 번호 없음")
        elif not service_key:
            st.warning("serviceKey 필요")
        else:
            st.markdown("#### 3) API 조회 진행")
            result_df = call_api(
                business_numbers,
                service_key,
                batch_size=int(batch_size),
                sleep_sec=float(throttle)
            )

# 4) 결과 출력 및 다운로드
if result_df is not None:
    if result_df.empty:
        st.warning("응답 데이터 없음")
    else:
        st.success(f"조회 완료 • 총 {len(result_df)}행")
        # CSV 변환(EUC-KR)
        result_df= result_df[["b_no",'b_stt','tax_type','end_dt']]
        result_df.columns = ['사업자등록번호','사업자 상태','과세 유형','폐업일']
        st.dataframe(result_df.head(50), use_container_width=True)
        csv_bytes = result_df.to_csv(index=False, encoding="euc-kr").encode("euc-kr", errors="ignore")
        
        st.download_button(
            label="결과 CSV 다운로드(EUC-KR)",
            data=csv_bytes,
            file_name="business_check_results.csv",
            mime="text/csv"
        )

st.markdown("---")
st.caption("주의: 동시 사용시 충돌 주의 발생 가능")