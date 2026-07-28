"""
배포된 API로 서명 요청 → 상태 동기화까지 확인

스파이크(modusign_spike.py)는 모두싸인에 직접 쏘기 때문에 문서가
백엔드 저장소(_store)에 없다. 그래서 웹훅이 와도 reconcile()이 돌지 않고
"저장소에 없는 문서" 로그만 남는다.

이 스크립트는 백엔드 API를 거치므로 저장소에 기록이 남고,
웹훅 → reconcile() → 상태 갱신 경로가 실제로 동작하는지 확인할 수 있다.

실행:
    cd ~/AI-Builder-Sprint
    python3 spikes/api_e2e.py                    # /contracts/sign
    python3 spikes/api_e2e.py analyze            # /contracts/analyze-sign (검증 포함)
    python3 spikes/api_e2e.py status <문서ID>     # 상태 조회

대상 서버는 환경변수로 바꾼다:
    API_BASE=http://localhost:8000 python3 spikes/api_e2e.py
"""

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get(
    "API_BASE", "https://ai-builder-sprint-production.up.railway.app"
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
try:
    from make_test_pdf import SAMPLE  # 데모 시나리오와 동일한 가상 계약
except ImportError as e:
    sys.exit(
        f"backend 모듈을 불러오지 못했습니다: {e}\n"
        "  가상환경을 켜고 프로젝트 루트에서 실행하세요:\n"
        "    source backend/.venv/bin/activate && cd ~/AI-Builder-Sprint"
    )

EMAIL = os.environ.get("TEST_WORKER_EMAIL") or os.environ.get("MODUSIGN_EMAIL", "")


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(API_BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json; charset=utf-8")

    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"\n❌ HTTP {e.code}")
        try:
            print(json.dumps(json.loads(detail), ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print(detail)
        if e.code == 409:
            print(
                "\n💡 법정 기준 위반이 있어 막혔습니다. 의도된 동작입니다.\n"
                "   그대로 진행하려면: python3 spikes/api_e2e.py analyze --force"
            )
        sys.exit(1)


def send(endpoint: str, force: bool) -> None:
    if not EMAIL:
        sys.exit("TEST_WORKER_EMAIL 또는 MODUSIGN_EMAIL 을 설정하세요.")

    body = {
        "terms": json.loads(SAMPLE.model_dump_json()),
        "worker_name": "김하늘",
        "worker_email": EMAIL,
        "employer_name": "박정호",
        "employer_email": EMAIL,
        "entry_path": "PHOTO",
    }
    if endpoint.endswith("analyze-sign"):
        body["proceed_with_violations"] = force

    print(f"대상 : {API_BASE}{endpoint}")
    print(f"메일 : {EMAIL}")
    print("\n발송 중...")

    result = call("POST", endpoint, body)
    doc_id = result["document_id"]

    print("\n✅ 서명 요청 성공")
    print(f"   문서 ID : {doc_id}")
    print(f"   상태    : {result['status']}")

    report = result.get("report")
    if report:
        problems = [
            c["label"] for c in report.get("checks", [])
            if c.get("status") in ("VIOLATION", "MISSING")
        ]
        print(f"   검증    : 문제 {len(problems)}건 {problems}")

    print("\n다음:")
    print("  1. 메일에서 근로자 → 사업주 순서로 서명")
    print("  2. Railway 로그에서 아래 두 줄을 확인 (이번 테스트의 핵심)")
    print(f"       문서 {doc_id} 상태 갱신: ...")
    print(f"       문서 {doc_id} 동기화 완료: ... (n/2 서명)")
    print("     ⚠️ '저장소에 없는 문서' 가 뜨면 실패다")
    print(f"  3. python3 spikes/api_e2e.py status {doc_id}")


def status(doc_id: str) -> None:
    r = call("GET", f"/contracts/{doc_id}/status")
    print(f"상태      : {r['status']}")
    print(f"서명 완료 : {r['signed']} / {r['total']}명")
    if r.get("download_url"):
        print(f"다운로드  : {r['download_url']}  (10분 유효)")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    cmd = args[0] if args else "sign"

    if cmd == "status":
        if len(args) < 2:
            sys.exit("사용법: python3 spikes/api_e2e.py status <문서ID>")
        status(args[1])
    elif cmd == "analyze":
        send("/contracts/analyze-sign", force)
    elif cmd == "sign":
        send("/contracts/sign", force)
    else:
        sys.exit(f"알 수 없는 명령: {cmd}  (sign | analyze | status)")
