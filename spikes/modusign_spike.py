"""
모두싸인 API 스파이크 테스트 (Day 1)

목적: API 승인 → 키 발급 후, 실제로 서명 요청이 발송되는지 확인한다.
스택 확정 전이므로 의존성 없는 표준 라이브러리만 사용한다.

실행:
    export MODUSIGN_EMAIL="your@email.com"
    export MODUSIGN_API_KEY="발급받은키"
    python spikes/modusign_spike.py auth      # 1단계: 인증만 확인
    python spikes/modusign_spike.py send      # 2단계: 서명 요청 발송
    python spikes/modusign_spike.py status <문서ID>   # 3단계: 상태 조회
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "https://api.modusign.co.kr"

EMAIL = os.environ.get("MODUSIGN_EMAIL", "")
API_KEY = os.environ.get("MODUSIGN_API_KEY", "")


def auth_header() -> str:
    """HTTP Basic 인증 헤더 생성 — base64(이메일:API_KEY)"""
    if not EMAIL or not API_KEY:
        sys.exit("MODUSIGN_EMAIL, MODUSIGN_API_KEY 환경변수를 설정하세요.")
    raw = f"{EMAIL}:{API_KEY}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def request(method: str, path: str, body: dict | None = None) -> dict:
    url = BASE_URL + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", auth_header())
    req.add_header("Accept", "application/json")
    if data:
        # 요청 본문은 반드시 UTF-8 (모두싸인 문서 명시)
        req.add_header("Content-Type", "application/json; charset=utf-8")

    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"\n❌ HTTP {e.code}")
        print(detail)
        sys.exit(1)


# ---------------------------------------------------------------- 1. 인증 확인

def check_auth() -> None:
    print("인증 확인 중...")
    result = request("GET", "/documents?offset=0&limit=1")
    print("✅ 인증 성공")
    print(f"   기존 문서 수: {result.get('totalCount', '(응답에 없음)')}")
    print(f"\n응답 키: {list(result.keys())}")


# ------------------------------------------------------- 2. 서명 요청 (anchor)

def build_payload(pdf_base64: str) -> dict:
    """
    Anchor 기반 필드 배치.
    PDF 안에 '근로자 서명', '사업주 서명' 텍스트가 반드시 있어야 한다.
    좌표(x,y,page)와 anchor는 동시에 쓸 수 없다 (400 에러).
    """
    return {
        "title": "[테스트] 근로계약서_스파이크",
        "file": {"base64": pdf_base64, "extension": "pdf"},
        "participants": [
            {
                "name": "테스트근로자",
                "signingOrder": 1,
                "signingMethod": {
                    "type": "EMAIL",
                    "value": os.environ.get("TEST_WORKER_EMAIL", EMAIL),
                },
                "fields": [
                    {
                        "type": "SIGNATURE",
                        "required": True,
                        "position": {
                            "anchor": {
                                "text": "근로자 서명",
                                "offset": {"x": 0.15, "y": 0.0},
                            }
                        },
                        "size": {"width": 0.15, "height": 0.05},
                    }
                ],
            }
        ],
    }


def send_signature_request() -> None:
    pdf_path = os.environ.get("TEST_PDF", "spikes/sample_contract.pdf")
    if not os.path.exists(pdf_path):
        sys.exit(
            f"테스트 PDF가 없습니다: {pdf_path}\n"
            "  → '근로자 서명' 텍스트가 포함된 텍스트 레이어 PDF를 준비하세요.\n"
            "  → 이미지로 만든 PDF는 anchor를 찾지 못합니다."
        )

    with open(pdf_path, "rb") as f:
        pdf_base64 = base64.b64encode(f.read()).decode("ascii")

    print(f"PDF 로드: {pdf_path} ({len(pdf_base64)} bytes base64)")
    print("서명 요청 발송 중...")

    result = request("POST", "/documents", build_payload(pdf_base64))

    print("\n✅ 서명 요청 성공")
    print(f"   문서 ID : {result['id']}")
    print(f"   상태    : {result['status']}  (ON_PROCESSING이 정상)")
    print(f"   제목    : {result['title']}")
    print(f"\n다음: python spikes/modusign_spike.py status {result['id']}")


# ------------------------------------------------------------- 3. 상태 조회

def check_status(document_id: str) -> None:
    result = request("GET", f"/documents/{document_id}")

    print(f"상태: {result['status']}")
    print(f"현재 서명 차례: {result.get('currentSigningOrder')}")

    signings = result.get("signings", [])
    print(f"서명 완료: {len(signings)}명")

    if result["status"] == "COMPLETED":
        print(f"\n✅ 체결 완료")
        print(f"   다운로드(10분 유효): {result['file']['downloadUrl']}")
    elif result["status"] == "PROCESSING_FAILED":
        print("\n❌ 문서 처리 실패 — anchor 텍스트를 못 찾았을 가능성이 높습니다")


# ------------------------------------------------------------------ main

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "auth"

    if cmd == "auth":
        check_auth()
    elif cmd == "send":
        send_signature_request()
    elif cmd == "status":
        if len(sys.argv) < 3:
            sys.exit("사용법: python spikes/modusign_spike.py status <문서ID>")
        check_status(sys.argv[2])
    else:
        sys.exit(f"알 수 없는 명령: {cmd}  (auth | send | status)")
