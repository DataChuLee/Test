"""
토지이용계획 스크래퍼
이음(eum.go.kr) 사이트에서 주소 기반으로 토지이용계획 정보를 수집한다.
"""

from playwright.sync_api import (
    sync_playwright,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)


def get_land_use_info(address: str, headless: bool = True) -> dict:
    """
    주소를 입력받아 토지이용계획 정보를 반환한다.

    Args:
        address: 검색할 주소 (예: '강남구 테헤란로 152')
        headless: 브라우저를 백그라운드에서 실행할지 여부 (기본: True)
                  디버깅 시 False로 설정하면 브라우저 화면을 볼 수 있음

    Returns:
        {
            "address": "입력한 주소",
            "소재지": "서울특별시 강남구 역삼동 737번지",
            "지목": "대",
            "면적": "13,156.7 ㎡",
            "지역지구구역": [
                {"구분": "국토계획법", "지역지구구역명": "도시지역"},
                {"구분": "국토계획법", "지역지구구역명": "일반상업지역"},
                {"구분": "다른법령", "지역지구구역명": "가로구역별 최고높이 제한지역<건축법>"},
                ...
            ]
        }

    Raises:
        ValueError: 주소를 찾을 수 없거나 검색 결과가 없는 경우
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
        page = context.new_page()

        try:
            page.goto(
                "https://www.eum.go.kr/web/am/amMain.jsp",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(2000)

            _search_and_navigate(page, address)
            return _extract_data(page, address)
        finally:
            browser.close()


# ── 내부 헬퍼 함수 ────────────────────────────────────────────────────────────


def _search_and_navigate(page: Page, address: str) -> None:
    """주소 검색 → 첫 번째 결과 클릭 → 토지이용계획 상세 페이지로 이동한다."""
    # 검색창 입력 (class: addrTxt_back)
    inp = page.locator("input.addrTxt_back").first
    inp.click()
    page.keyboard.type(address, delay=80)

    # 자동완성 결과 대기 (div.recent_see ul li a)
    try:
        page.wait_for_selector("div.recent_see ul li a", timeout=8000)
    except PlaywrightTimeoutError:
        raise ValueError(
            f"주소 '{address}'에 대한 검색 결과를 찾을 수 없습니다. "
            "주소 형식을 확인하세요 (예: '강남구 테헤란로 152')."
        )

    first_result = page.locator("div.recent_see ul li a").first

    # 첫 번째 결과 클릭 (chiceAdAddr 호출 → 자동 form submit → 페이지 이동)
    first_result.click()

    # luLandDet.jsp 로딩 대기 (hash 변경과 구분하기 위해 wait_for_url 사용)
    try:
        page.wait_for_url("**/luLandDet.jsp**", timeout=15000)
    except PlaywrightTimeoutError:
        # 이미 이동했거나 다른 경로인 경우 확인
        if "luLandDet" not in page.url and "cvUpisDet" not in page.url:
            raise ValueError(
                f"토지이용계획 페이지로 이동하지 못했습니다. " f"현재 URL: {page.url}"
            )

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(1500)


def _extract_data(page: Page, address: str) -> dict:
    """토지이용계획 상세 페이지에서 데이터를 추출한다."""
    # 첫 번째 테이블(공간정보 테이블)이 로딩될 때까지 대기
    try:
        page.wait_for_selector("table caption", timeout=10000)
    except PlaywrightTimeoutError:
        raise ValueError("토지이용계획 데이터 로딩 시간이 초과되었습니다.")

    result = page.evaluate(
        """
        () => {
            // ── 공간정보: 소재지·지목·면적 ──────────────────────────────
            const firstTable = document.querySelector("table");

            // 소재지 (hidden div #present_addr 제외하고 직접 텍스트 노드만 추출)
            let 소재지 = "";
            const addrTd = firstTable ? firstTable.querySelector("tr:first-child td") : null;
            if (addrTd) {
                // display:none인 자식 요소를 제외한 텍스트만 가져옴
                let raw = "";
                addrTd.childNodes.forEach(node => {
                    if (node.nodeType === Node.TEXT_NODE) {
                        raw += node.textContent;
                    } else if (node.nodeType === Node.ELEMENT_NODE) {
                        const style = window.getComputedStyle(node);
                        if (style.display !== "none") raw += node.textContent;
                    }
                });
                소재지 = raw.replace(/\\s+/g, " ").trim();
            }

            // 지목: hidden input value가 가장 깔끔함
            const classVal = document.getElementById("present_class_val");
            const 지목 = classVal ? classVal.value.trim() : "";

            // 면적: th 텍스트가 '면적'인 셀의 인접 td
            let 면적 = "";
            if (firstTable) {
                firstTable.querySelectorAll("tr").forEach(tr => {
                    const ths = tr.querySelectorAll("th");
                    const tds = tr.querySelectorAll("td");
                    ths.forEach((th, i) => {
                        if (th.textContent.trim() === "면적" && tds[i]) {
                            면적 = tds[i].textContent.replace(/\\s+/g, " ").trim();
                        }
                    });
                });
            }

            // ── 지역지구구역 ────────────────────────────────────────────
            // present_mark1: 국토의 계획 및 이용에 관한 법률에 따른 지역지구
            // present_mark2: 다른 법령에 따른 지역지구
            // present_mark3: 토지이용규제 기본법 시행령 제9조 제4항 사항
            const getLinkedZones = (cellId, 구분) => {
                const cell = document.getElementById(cellId);
                if (!cell) return [];
                // 팝업 레이어(div.layer_pop) 내부 a는 제외하고, 직계 자식 a만 수집
                const zones = [];
                cell.childNodes.forEach(node => {
                    if (node.nodeName === "A") {
                        const nm = node.textContent.trim();
                        if (nm) zones.push({ 구분, 지역지구구역명: nm });
                    }
                });
                return zones;
            };

            const getTextZones = (cellId, 구분) => {
                const cell = document.getElementById(cellId);
                if (!cell) return [];
                // 콤마로 구분된 텍스트 아이템
                const rawText = cell.textContent.replace(/<[^>]+>/g, "").trim();
                if (!rawText) return [];
                return rawText
                    .split(",")
                    .map(s => s.replace(/\\s+/g, " ").trim())
                    .filter(s => s.length > 0)
                    .map(nm => ({ 구분, 지역지구구역명: nm }));
            };

            const 지역지구구역 = [
                ...getLinkedZones("present_mark1", "국토계획법"),
                ...getLinkedZones("present_mark2", "다른법령"),
                ...getTextZones("present_mark3", "토지이용규제기본법"),
            ];

            return { 소재지, 지목, 면적, 지역지구구역 };
        }
    """
    )

    if not result.get("소재지") and not result.get("지역지구구역"):
        raise ValueError(
            f"'{address}'에 대한 토지이용계획 데이터를 추출하지 못했습니다. "
            "headless=False로 실행하여 화면을 직접 확인해보세요."
        )

    return {
        "address": address,
        "소재지": result.get("소재지", ""),
        "지목": result.get("지목", ""),
        "면적": result.get("면적", ""),
        "지역지구구역": result.get("지역지구구역", []),
    }


# ── 직접 실행 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    addr = sys.argv[1] if len(sys.argv) > 1 else "강남구 테헤란로 152"
    print(f"검색 중: {addr}")
    result = get_land_use_info(addr, headless=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
