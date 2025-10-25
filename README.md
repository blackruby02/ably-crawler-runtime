# Ably Crawler Runtime (server one-shot)

크롤링 로직은 **`ably_seller_crawler.py` (사용자 성공 코드 그대로)**를 사용합니다.  
이 레포는 서버에서 `git pull` 후 즉시 실행할 **배치 러너**(`batch_runner.py`)를 제공합니다.

## 1) 서버 준비 (Ubuntu 22.04)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
  xvfb
```

## 2) 파이썬 환경

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## 3) 실행

GUI 없는 서버에서는 headful 세션 발급을 위해 **전체 명령을 xvfb-run**으로 감싸 실행하세요.

```bash
# 예: 1 ~ 110000까지 CSV 저장
xvfb-run -a python batch_runner.py --start 1 --end 110000 --out sellers.csv
```

- 중간에 끊겼다면, `--start` 없이 다시 실행하면 `progress.json`을 확인해 자동 재개합니다:

```bash
xvfb-run -a python batch_runner.py --end 110000 --out sellers.csv
```

## 4) 출력

- **sellers.csv** (기본): 각 ID별 추출 결과를 누적 저장
- **progress.json**: 마지막 처리 ID 저장(재개용)
- **session.json**: Cloudflare 통과 세션(최초 1회 자동 생성)

## 5) 참고

- 배치 러너는 로컬에서 성공한 크롤링 로직(`save_session_once`, `fetch_html_headless`, `parse_seller_info`)을 그대로 호출합니다.
- 대량 운영/오류 재시도/DB저장/세션쿨다운 등의 고도화는 별도 브랜치에서 확장 가능합니다.

---

## 6) 서버 배포/실행 스크립트 (예시)

서버에서:

```bash
# 클론 또는 업데이트
git clone <YOUR_REPO_URL> ably-crawler-runtime || (cd ably-crawler-runtime && git pull)

# 의존성
cd ably-crawler-runtime
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# 1회 실행 (세션 발급 + 대량 수집)
xvfb-run -a python batch_runner.py --start 1 --end 110000 --out sellers.csv
```
