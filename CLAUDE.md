# CLAUDE.md

## 절대 규칙

- `venv/` 외부에 패키지를 설치하지 말 것
- 사이트 자동화 셀렉터 변경 시 반드시 실제 브라우저(`headless=False`)로 검증 후 수정
- `scraper.py`의 공개 함수 시그니처(`get_land_use_info`)를 임의로 변경하지 말 것

---

## 아키텍처

```
Test/
├── scraper.py          # 메인 스크래퍼 모듈 (유일한 소스 파일)
├── requirements.txt    # playwright>=1.40.0
├── venv/               # Python 3.11.9 가상환경
└── CLAUDE.md
```

**기술 스택:** Python 3.11 · Playwright (sync API) · Chromium

**대상 사이트:** https://www.eum.go.kr/web/am/amMain.jsp (토지이음, 국토이용정보체계)

---

## 빌드 / 테스트

```bash
# 환경 활성화
source venv/Scripts/activate        # Windows Git Bash
# venv\Scripts\activate.bat         # Windows cmd

# 최초 설치
pip install -r requirements.txt
playwright install chromium

# 실행 (터미널)
python scraper.py "강남구 테헤란로 152"

# 함수 호출
python -c "
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from scraper import get_land_use_info
print(json.dumps(get_land_use_info('강남구 테헤란로 152'), ensure_ascii=False, indent=2))
"
```

---

## 도메인 컨텍스트

**토지이용계획** — 특정 토지에 적용되는 지역·지구·구역 지정 현황

| 용어 | 설명 |
|------|------|
| PNU | 필지고유번호 (19자리). 이음 사이트 내부 식별자 |
| 국토계획법 지역지구 | `present_mark1` 셀. 도시지역·용도지역 등 |
| 다른 법령 지역지구 | `present_mark2` 셀. 건축법·군사시설보호법 등 |
| 토지이용규제기본법 사항 | `present_mark3` 셀. 토지거래허가구역·건축선 등 |

**사이트 자동화 핵심 흐름:**
1. `input.addrTxt_back` 에 주소 키보드 타이핑 (delay=80ms)
2. 자동완성 결과 → `div.recent_see ul li a` (jQuery UI autocomplete 아님, 커스텀 div)
3. 첫 번째 결과 클릭 → `chiceAdAddr(addr, pnu, true)` 자동 호출 → form 제출
4. `wait_for_url("**/luLandDet.jsp**")` 로 실제 페이지 이동 감지 (hash 변경과 구분)
5. 데이터 추출: 첫 번째 `<table>` (공간정보) + `#present_mark1/2/3` (지역지구구역)

**반환 구조:**
```json
{
  "address": "입력 주소",
  "소재지": "서울특별시 강남구 역삼동 737번지",
  "지목": "대",
  "면적": "13,156.7 ㎡",
  "지역지구구역": [
    {"구분": "국토계획법",       "지역지구구역명": "도시지역"},
    {"구분": "다른법령",         "지역지구구역명": "가로구역별 최고높이 제한지역<건축법>"},
    {"구분": "토지이용규제기본법", "지역지구구역명": "토지거래계약에관한허가구역(...)"}
  ]
}
```

---

## 배포 트리거

**키워드:** `배포해줘`

**실행 순서:**
1. 테스트: `python scraper.py "강남구 테헤란로 152"` 실행 → 에러 없이 JSON 반환 확인
2. 검증 통과 시: `git add -A` → `git commit` → `git push`
3. 검증 실패 시: 배포 중단, 오류 내용 보고

**커밋 메시지 형식:** `변경 내용 요약` (예: `토지이용계획 스크래퍼 추가`)
---

## 코딩 컨벤션

- 함수명: `snake_case`. 내부 헬퍼는 `_` 접두사 (`_search_and_navigate`, `_extract_data`)
- Playwright: sync API 사용 (`sync_playwright`). async 전환 금지
- 셀렉터 우선순위: id > class > 텍스트 포함 순. jQuery UI autocomplete 셀렉터(`.ui-autocomplete`) 사용 금지 (이 사이트에서 실제 결과를 담지 않음)
- 에러: `ValueError` 단일 예외 타입. 메시지에 디버깅 힌트(`headless=False`) 포함
- 인코딩: 출력 시 `sys.stdout.reconfigure(encoding='utf-8')` 필요 (Windows cp949 기본값 문제)
