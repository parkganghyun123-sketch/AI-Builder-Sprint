"""
모두싸인 API 스파이크 테스트

실제 서비스 흐름(근로자 → 사업주 순서 서명)과 동일하게 테스트한다.
backend/app/signing/modusign.py 와 같은 anchor 상수를 사용한다.

실행:
    cd ~/AI-Builder-Sprint
    set -a; source .env; set +a

    python3 spikes/modusign_spike.py auth              # 1. 인증
    python3 spikes/modusign_spike.py check             # 2. PDF anchor 텍스트 검사
    python3 spikes/modusign_spike.py send              # 3. 서명 요청 발송
    python3 spikes/modusign_spike.py status <문서ID>    # 4. 상태 조회
"""

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime

BASE_URL = "https://api.modusign.co.kr"

# backend/app/signing/modusign.py 와 반드시 동일해야 한다
#
# anchor는 서명이 들어갈 위치 "바로 옆"에 두어야 정확하다.
# 멀리 떨어진 텍스트에서 offset으로 밀면 오차가 크게 벌어진다.
ANCHOR_EMPLOYER = "(사업주 서명)"
ANCHOR_WORKER = "(근로자 서명)"

# 위치 미세조정 — 환경변수로 덮어쓸 수 있다 (반복 테스트용)
#   SIGN_OFFSET_X=0.12 SIGN_OFFSET_Y=-0.02 python3 spikes/modusign_spike.py send
SIGN_OFFSET_X = float(os.environ.get("SIGN_OFFSET_X", 0.10))
SIGN_OFFSET_Y = float(os.environ.get("SIGN_OFFSET_Y", -0.012))

EMAIL = os.environ.get("MODUSIGN_EMAIL", "")
API_KEY = os.environ.get("MODUSIGN_API_KEY", "")
PDF_PATH = os.environ.get("TEST_PDF", "spikes/sample_contract.pdf")


def auth_header() -> str:
    if not EMAIL or not API_KEY:
        sys.exit(
            "MODUSIGN_EMAIL, MODUSIGN_API_KEY 환경변수를 설정하세요.\n"
            "  set -a; source .env; set +a"
        )
    raw = f"{EMAIL}:{API_KEY}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def request(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(BASE_URL + path, data=data, method=method)
    req.add_header("Authorization", auth_header())
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json; charset=utf-8")

    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"\n❌ HTTP {e.code}")
        print(detail)
        if "Anchor text not found" in detail:
            print(
                "\n💡 PDF에서 anchor 텍스트를 못 찾았습니다.\n"
                "   python3 spikes/modusign_spike.py check 로 먼저 확인하세요."
            )
        sys.exit(1)


# ------------------------------------------------------------ 1. 인증

def check_auth() -> None:
    print("인증 확인 중...")
    result = request("GET", "/documents?offset=0&limit=1")
    print("✅ 인증 성공")
    print(f"   기존 문서 수: {result.get('count', '?')}")


# ------------------------------------------- 2. PDF anchor 사전 검사

def check_pdf() -> None:
    """
    서명 요청을 보내기 전에 PDF 텍스트 레이어를 검사한다.
    400 에러로 크레딧을 낭비하지 않기 위한 단계.
    """
    if not os.path.exists(PDF_PATH):
        sys.exit(f"PDF가 없습니다: {PDF_PATH}\n  cd backend && python make_test_pdf.py")

    print(f"검사 대상: {PDF_PATH}\n")

    try:
        text = subprocess.run(
            ["pdftotext", PDF_PATH, "-"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except FileNotFoundError:
        print("⚠️  pdftotext가 없어 텍스트 레이어를 확인할 수 없습니다.")
        print("   설치: brew install poppler")
        print("   설치 없이 진행하려면 send를 바로 실행하되, 400이 나면 이 단계로 돌아오세요.")
        return

    ok = True
    for label, anchor in (("사업주", ANCHOR_EMPLOYER), ("근로자", ANCHOR_WORKER)):
        count = text.count(anchor)
        if count == 1:
            print(f"  ✅ {label} anchor '{anchor}' — 1회 등장 (정상)")
        elif count == 0:
            print(f"  ❌ {label} anchor '{anchor}' — 없음. 폰트 깨짐 또는 문구 불일치")
            ok = False
        else:
            print(f"  ⚠️  {label} anchor '{anchor}' — {count}회 등장")
            print("      여러 번 나오면 매칭 개수만큼 서명란이 생겨 참여자 구분이 안 됩니다")
            ok = False

    if "□" in text or "�" in text:
        print("\n  ⚠️  텍스트에 깨진 문자가 있습니다. 한글 폰트 임베딩을 확인하세요.")
        ok = False

    print("\n✅ 검사 통과. send 가능합니다." if ok else "\n❌ PDF를 먼저 수정하세요.")
    if not ok:
        sys.exit(1)


# ------------------------------------------------- 3. 서명 요청 발송

def _signature_field(anchor_text: str) -> dict:
    return {
        "type": "SIGNATURE",
        "required": True,
        # SIGNATURE 필드에는 필수. SIGN(서명) 또는 STAMP(도장), 최대 2개
        "signatureTypes": ["SIGN"],
        "position": {
            "anchor": {
                "text": anchor_text,
                "offset": {"x": SIGN_OFFSET_X, "y": SIGN_OFFSET_Y},
            }
        },
        "size": {"width": 0.14, "height": 0.045},
    }


def send_signature_request() -> None:
    if not os.path.exists(PDF_PATH):
        sys.exit(f"PDF가 없습니다: {PDF_PATH}\n  cd backend && python make_test_pdf.py")

    with open(PDF_PATH, "rb") as f:
        pdf_b64 = base64.b64encode(f.read()).decode("ascii")

    worker_email = os.environ.get("TEST_WORKER_EMAIL", EMAIL)
    owner_email = os.environ.get("TEST_OWNER_EMAIL", EMAIL)

    # ⚠️ 제목에 반드시 시각을 넣는다.
    #    제목이 매번 같으면 메일함에서 이전 테스트 메일과 구분이 안 되고,
    #    이미 서명을 마친 옛 문서를 열어보게 된다.
    stamp = datetime.now().strftime("%m%d-%H%M%S")
    title = f"[테스트 {stamp}] 근로계약서_김하늘"

    payload = {
        "title": title,
        "file": {"base64": pdf_b64, "extension": "pdf"},
        "participants": [
            {
                "name": "김하늘",
                "signingOrder": 1,
                "signingMethod": {"type": "EMAIL", "value": worker_email},
                "fields": [_signature_field(ANCHOR_WORKER)],
            },
            {
                "name": "박정호",
                "signingOrder": 2,
                "signingMethod": {"type": "EMAIL", "value": owner_email},
                "fields": [_signature_field(ANCHOR_EMPLOYER)],
            },
        ],
    }

    print(f"PDF: {PDF_PATH}")
    print(f"제목: {title}")
    print(f"1순위 서명(근로자): {worker_email}")
    print(f"2순위 서명(사업주): {owner_email}")
    print("\n발송 중...")

    result = request("POST", "/documents", payload)

    print("\n✅ 서명 요청 성공")
    print(f"   문서 ID : {result['id']}")
    print(f"   상태    : {result['status']}")
    print("\n다음:")
    print(f"  1. 메일함에서 제목이 '{title}' 인 메일을 여세요.")
    print("     ⚠️ 제목의 시각이 위와 다르면 이전 테스트 메일입니다. 열지 마세요.")
    print("  2. 서명란이 '(서명)' 자리에 정확히 있는지 확인")
    print(f"  3. python3 spikes/modusign_spike.py status {result['id']}")


# ------------------------------------------------------ 4. 상태 조회

def check_status(document_id: str) -> None:
    doc = request("GET", f"/documents/{document_id}")

    print(f"상태            : {doc['status']}")
    print(f"현재 서명 차례  : {doc.get('currentSigningOrder')}")

    participants = doc.get("participants", [])
    signings = doc.get("signings", [])
    print(f"서명 완료       : {len(signings)} / {len(participants)}명")

    if doc["status"] == "COMPLETED":
        print("\n✅ 체결 완료")
        print(f"   다운로드(10분 유효): {doc['file']['downloadUrl']}")
    elif doc["status"] == "PROCESSING_FAILED":
        print("\n❌ 처리 실패 — anchor 텍스트 문제일 가능성이 높습니다")
    elif doc["status"] == "ON_GOING":
        print("\n⏳ 서명 대기 중")


# ------------------------------------------------------------ main

def list_documents() -> None:
    """
    최근 문서를 최신순으로 보여준다.
    메일함의 어떤 메일이 방금 보낸 것인지 대조할 때 쓴다.
    """
    result = request("GET", "/documents?offset=0&limit=10")
    docs = result.get("documents") or result.get("data") or []

    if not docs:
        print("문서가 없습니다.")
        return

    print(f"최근 문서 {len(docs)}건 (최신순)\n")
    for i, d in enumerate(docs, 1):
        mark = "← 최신" if i == 1 else ""
        print(f"  {i:2}. {d.get('title', '?')}")
        print(f"      {d.get('status', '?'):<16} {d.get('id', '?')} {mark}")


COMMANDS = {
    "auth": lambda: check_auth(),
    "check": lambda: check_pdf(),
    "send": lambda: send_signature_request(),
    "list": lambda: list_documents(),
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "auth"

    if cmd == "status":
        if len(sys.argv) < 3:
            sys.exit("사용법: python3 spikes/modusign_spike.py status <문서ID>")
        check_status(sys.argv[2])
    elif cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        sys.exit(f"알 수 없는 명령: {cmd}  (auth | check | send | status)")
