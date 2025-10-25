# ably_seller_crawler.py
# pip install playwright beautifulsoup4
# python -m playwright install chromium
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup
import re, json, os, time, sys
from typing import Dict, Optional

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)

SESSION_PATH = "session.json"
BASE = "https://m.a-bly.com"

def save_session_once(market_id: int = 2083, wait_ms: int = 8000) -> None:
    """서버/로컬에서 1회 Cloudflare 챌린지 통과 후 세션 저장."""
    with sync_playwright() as p:
        # 최초 1회는 headful 권장 (headless도 가능할 수 있으나 성공률↓)
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent=MOBILE_UA, locale="ko-KR")
        page = ctx.new_page()
        url = f"{BASE}/market/{market_id}/info"
        print(f"[save_session] Opening: {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)  # CF 챌린지 통과 대기
        ctx.storage_state(path=SESSION_PATH)
        print(f"[save_session] Saved session → {SESSION_PATH}")
        browser.close()

def fetch_html_headless(market_id: int, timeout_ms: int = 15000) -> str:
    """저장된 세션을 사용해 headless로 HTML 수집."""
    if not os.path.exists(SESSION_PATH):
        raise FileNotFoundError(f"{SESSION_PATH} not found. Run save_session_once() first.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=SESSION_PATH, user_agent=MOBILE_UA, locale="ko-KR")
        page = ctx.new_page()
        url = f"{BASE}/market/{market_id}/info"
        print(f"[headless] Opening: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except PWTimeout:
            print("[headless] Timeout loading page.")
        page.wait_for_timeout(3000)  # 숨쉬기 딜레이
        html = page.content()
        browser.close()
        return html

def looks_like_cf_challenge(html: str) -> bool:
    """Cloudflare 'Just a moment...' 감지."""
    if "Just a moment..." in html:
        return True
    if "/cdn-cgi/challenge-platform/" in html:
        return True
    return False

def parse_seller_info(html: str) -> Dict[str, Optional[str]]:
    """판매자 정보 섹션에서 정보 추출."""
    soup = BeautifulSoup(html, "html.parser")
    data: Dict[str, Optional[str]] = {
        "상호": None,
        "대표자": None,
        "사업자등록번호": None,
        "통신판매업신고번호": None,
        "이메일": None,
        "전화번호": None,
        "주소": None,
    }

    # 판매자 정보 섹션 찾기
    seller_section = None
    
    # 방법 1: "판매자 정보" 텍스트를 포함한 섹션 찾기
    seller_heading = soup.find(string=re.compile("판매자 정보"))
    if seller_heading:
        # 부모 요소들을 거슬러 올라가면서 적절한 섹션 찾기
        current = seller_heading.parent
        while current:
            if current.name in ['div', 'section']:
                seller_section = current
                break
            current = current.parent
    
    if seller_section:
        # 판매자 정보 섹션 내의 모든 텍스트 추출
        section_text = seller_section.get_text("\n", strip=True)
        
        # 정규식으로 각 정보 추출
        patterns = {
            "상호": r"상호\s*[:：]\s*([^\n]+)",
            "대표자": r"대표자\s*[:：]\s*([^\n]+)",
            "주소": r"주소\s*[:：]\s*([^\n]+)",
            "사업자등록번호": r"사업자등록번호\s*[:：]\s*([0-9\-]+)",
            "통신판매업신고번호": r"통신판매업신고번호\s*[:：]\s*([0-9A-Za-z\-]+)",
            "이메일": r"이메일\s*[:：]\s*([^\n]+)",
            "전화번호": r"전화번호\s*[:：]\s*([0-9\-\(\) ]+)"
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                data[key] = match.group(1).strip()
        
        # 이메일과 전화번호에 대한 추가 패턴 매칭
        if not data["이메일"]:
            email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", section_text)
            if email_match:
                data["이메일"] = email_match.group(1)
        
        if not data["전화번호"]:
            phone_match = re.search(r"((?:0\d{1,2}-)?\d{3,4}-\d{4})", section_text)
            if phone_match:
                data["전화번호"] = phone_match.group(1)
    
    # 방법 2: 전체 HTML에서 정규식으로 백업 추출
    if not any(data.values()):
        full_text = soup.get_text("\n", strip=True)
        
        backup_patterns = {
            "상호": r"상호\s*[:：]\s*([^\n]+)",
            "대표자": r"대표자\s*[:：]\s*([^\n]+)",
            "주소": r"주소\s*[:：]\s*([^\n]+)",
            "사업자등록번호": r"사업자등록번호\s*[:：]\s*([0-9\-]+)",
            "통신판매업신고번호": r"통신판매업신고번호\s*[:：]\s*([0-9A-Za-z\-]+)",
            "이메일": r"이메일\s*[:：]\s*([^\n]+)",
            "전화번호": r"전화번호\s*[:：]\s*([0-9\-\(\) ]+)"
        }
        
        for key, pattern in backup_patterns.items():
            if not data[key]:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    data[key] = match.group(1).strip()

    return data

def main():
    # 1) 세션 없으면 headful로 1회 저장
    if not os.path.exists(SESSION_PATH):
        print("[main] session.json 없음 → 최초 1회 세션 저장 시도")
        save_session_once(market_id=2083)
        time.sleep(1)

    # 2) headless 수집 테스트
    market_ids = [2083, 2084]  # 필요 시 수정
    results = []

    for mid in market_ids:
        html = fetch_html_headless(mid)
        if looks_like_cf_challenge(html):
            print(f"[main] market_id={mid}: Cloudflare 챌린지 화면 감지 → 세션 재발급 필요")
            continue
        info = parse_seller_info(html)
        info["market_id"] = mid
        results.append(info)
        print(f"[OK] {mid} → {json.dumps(info, ensure_ascii=False)}")
        time.sleep(1.5)  # 예의 있는 지연

    if not results:
        print("[main] 수집 결과가 비었습니다. 세션 만료/차단 가능성 → save_session_once() 다시 실행 권장.")

if __name__ == "__main__":
    # 서버 GUI가 없다면: xvfb-run -a python ably_seller_crawler.py
    try:
        main()
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)
