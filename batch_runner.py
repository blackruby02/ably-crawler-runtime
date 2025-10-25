# batch_runner.py
# 목적: 서버에서 한 번 실행으로 market_id 다량 순회 + CSV 저장 + 진행재개 + 최소 로깅
# - 크롤링은 ably_seller_crawler.py의 성공 로직을 그대로 import하여 사용
# - Docker/스케줄러 없이 1회 실행
# 실행 예:
#   xvfb-run -a python batch_runner.py --start 1 --end 110000 --out sellers.csv

import os, sys, csv, time, json, argparse, random
from datetime import timedelta
from typing import Dict, Optional
from ably_seller_crawler import (
    SESSION_PATH,
    save_session_once,
    fetch_html_headless,
    looks_like_cf_challenge,
    parse_seller_info,
)

PROGRESS_PATH = "progress.json"  # 단일 상태 저장(재개용)
DEFAULT_DELAY_MIN = 1.8
DEFAULT_DELAY_MAX = 3.0

def fmt_td(sec: float) -> str:
    return str(timedelta(seconds=int(sec)))

def load_progress() -> Dict:
    if not os.path.exists(PROGRESS_PATH):
        return {}
    try:
        with open(PROGRESS_PATH, "r") as f:
            return json.load(f)
    except:
        return {}

def save_progress(d: Dict):
    tmp = PROGRESS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, PROGRESS_PATH)

def ensure_csv_header(outfile: str):
    """CSV 파일이 없으면 헤더를 생성"""
    if not os.path.exists(outfile):
        with open(outfile, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["market_id","상호","대표자","사업자등록번호","통신판매업신고번호","이메일","전화번호","주소","source_url","scraped_at"])

def main():
    ap = argparse.ArgumentParser(description="Batch runner using user's successful crawler logic.")
    ap.add_argument("--start", type=int, default=None, help="start market_id (inclusive)")
    ap.add_argument("--end", type=int, required=True, help="end market_id (inclusive)")
    ap.add_argument("--out", type=str, default="sellers.csv", help="output CSV filename")
    ap.add_argument("--delay_min", type=float, default=DEFAULT_DELAY_MIN)
    ap.add_argument("--delay_max", type=float, default=DEFAULT_DELAY_MAX)
    ap.add_argument("--summary_every", type=int, default=100)
    args = ap.parse_args()

    # 세션 준비(없으면 1회 발급)
    if not os.path.exists(SESSION_PATH):
        print("[init] session.json not found → issuing once (headful needed)")
        save_session_once()

    # 진행 재개: progress.json 우선 → 없으면 --start 사용
    progress = load_progress()
    start_id = args.start if args.start is not None else (progress.get("last_id", 0) + 1 or 1)
    if start_id < 1:
        start_id = 1
    if start_id > args.end:
        print(f"[info] nothing to do (start_id {start_id} > end {args.end})")
        sys.exit(0)

    # 출력 준비 - CSV 헤더 생성
    ensure_csv_header(args.out)

    # 통계/타이밍
    ok = cf_hits = skip = 0
    t0 = time.time()

    current = start_id
    while current <= args.end:
        url = f"https://m.a-bly.com/market/{current}/info"
        print(f"[{current}] GET {url}")

        html = fetch_html_headless(current)
        if looks_like_cf_challenge(html):
            # 세션 재발급 1회 → 재시도 1회
            print(f"[{current}] CF detected → refresh session and retry")
            save_session_once()
            html = fetch_html_headless(current)
            if looks_like_cf_challenge(html):
                cf_hits += 1
                skip += 1
                print(f"[{current}] CF persists → skip")
                # 진행 저장
                progress["last_id"] = current
                save_progress(progress)
                current += 1
                time.sleep(random.uniform(args.delay_min, args.delay_max))
                continue

        data = parse_seller_info(html)
        # CSV 저장 - 실시간으로 파일에 추가
        try:
            with open(args.out, 'a', newline='', encoding='utf-8') as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow([
                    current,
                    data.get("상호"), data.get("대표자"), data.get("사업자등록번호"),
                    data.get("통신판매업신고번호"), data.get("이메일"), data.get("전화번호"),
                    data.get("주소"), url, int(time.time())
                ])
            ok += 1
        except Exception as e:
            print(f"[{current}] CSV 저장 실패: {e}")
            skip += 1

        # 진행/요약 로그
        processed = current - start_id + 1
        elapsed = time.time() - t0
        rate = (processed / elapsed * 60) if elapsed > 0 else 0.0
        print(f"[OK] {current} | ok={ok} skip={skip} cf={cf_hits} | rate={rate:.1f}/min elapsed={fmt_td(elapsed)}")
        if processed % args.summary_every == 0:
            print(f"[SUMMARY] done={processed} ok={ok} skip={skip} cf={cf_hits} elapsed={fmt_td(elapsed)}")

        # 진행 저장(재개용)
        progress["last_id"] = current
        save_progress(progress)

        # 다음
        current += 1
        time.sleep(random.uniform(args.delay_min, args.delay_max))

    print("[done] completed range.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[abort] interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)
