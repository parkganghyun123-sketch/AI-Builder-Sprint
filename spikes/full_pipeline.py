"""
전 구간 통합 확인 — 사진 한 장 → 추출 → 검증 → 계약서 → 서명 요청

지금까지 A·B·C·D가 각자 파트만 검증했고 전 구간을 한 번에 돌린 적이 없다.
이 스크립트가 그 공백을 메운다. 데모 리허설에도 그대로 쓴다.

실행:
    cd ~/AI-Builder-Sprint
    set -a; source .env; set +a

    python3 spikes/full_pipeline.py                       # 배포 서버
    python3 spikes/full_pipeline.py --local               # localhost:8000
    python3 spikes/full_pipeline.py 사진.png               # 다른 사진으로
    python3 spikes/full_pipeline.py --force               # 위반 있어도 서명 진행

확인 순서:
    0. /health          — 연동 설정 여부 (여기서 막히면 나머지는 무의미)
    1. /contracts/extract    사진 → 23개 항목
    2. /contracts/validate   항목 → 법정 기준 판정
    3. /contracts/analyze-sign  검증 + 계약서 + 서명 요청
"""

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

DEFAULT_IMAGE = "backend/app/evaluation/contracts/contract_01.png"
EMAIL = os.environ.get("TEST_WORKER_EMAIL") or os.environ.get("MODUSIGN_EMAIL", "")


def _api_base(args: list[str]) -> str:
    if "--local" in args:
        return "http://localhost:8000"
    return os.environ.get(
        "API_BASE", "https://ai-builder-sprint-production.up.railway.app"
    )


def call(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req, timeout=120) as res:
        return json.loads(res.read().decode("utf-8"))


def upload(base: str, path: str, file_path: str) -> dict:
    """multipart/form-data 업로드. 외부 라이브러리 없이 직접 조립한다."""
    with open(file_path, "rb") as f:
        content = f.read()

    filename = os.path.basename(file_path)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = f"----fairsign{uuid.uuid4().hex}"

    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])

    req = urllib.request.Request(base + path, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=120) as res:
        return json.loads(res.read().decode("utf-8"))


def fail(step: str, e: Exception) -> None:
    print(f"\n❌ {step} 실패")
    if isinstance(e, urllib.error.HTTPError):
        detail = e.read().decode("utf-8", errors="replace")
        print(f"   HTTP {e.code}")
        try:
            print("   " + json.dumps(json.loads(detail), ensure_ascii=False, indent=2)
                  .replace("\n", "\n   "))
        except json.JSONDecodeError:
            print("   " + detail[:500])
    else:
        print(f"   {e}")
    sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    base = _api_base(args)
    force = "--force" in args
    images = [a for a in args if not a.startswith("--")]
    image = images[0] if images else DEFAULT_IMAGE

    if not os.path.exists(image):
        sys.exit(f"사진이 없습니다: {image}")
    if not EMAIL:
        sys.exit("TEST_WORKER_EMAIL 또는 MODUSIGN_EMAIL 을 설정하세요.")

    print(f"서버 : {base}")
    print(f"사진 : {image}\n")

    # ---------------------------------------------- 0. 연동 설정 확인
    print("[0/3] /health")
    try:
        health = call(base, "GET", "/health")
    except Exception as e:
        fail("서버 접속", e)

    print(f"      모두싸인 : {health.get('modusign')}")
    print(f"      Upstage  : {health.get('upstage')}")
    if health.get("cors_origins"):
        print(f"      CORS     : {health['cors_origins']}")

    if not health.get("upstage"):
        sys.exit("\n❌ UPSTAGE_API_KEY 미설정. Railway 환경변수에 등록하세요.")
    if not health.get("modusign"):
        sys.exit("\n❌ 모두싸인 미설정. MODUSIGN_EMAIL / MODUSIGN_API_KEY 확인.")

    # ---------------------------------------------------- 1. 추출
    print("\n[1/3] POST /contracts/extract  (Upstage — 20초쯤 걸린다)")
    try:
        terms = upload(base, "/contracts/extract", image)
    except Exception as e:
        fail("추출", e)

    found = sum(1 for f in terms.values() if f.get("value") is not None)
    low = [k for k, f in terms.items() if f.get("confidence") == "LOW"]
    missing = [k for k, f in terms.items() if f.get("confidence") == "NOT_FOUND"]
    no_source = [
        k for k, f in terms.items()
        if f.get("value") is not None and not f.get("source_text")
    ]

    print(f"      추출 {found}/{len(terms)}개")
    print(f"      확인 필요(LOW) : {low or '없음'}")
    print(f"      누락(NOT_FOUND): {missing or '없음'}")
    print(f"      근거 문장 없음  : {no_source or '없음'}")

    # ---------------------------------------------------- 2. 검증
    print("\n[2/3] POST /contracts/validate  (코드 판정 — AI 아님)")
    try:
        report = call(base, "POST", "/contracts/validate", {"terms": terms})
    except Exception as e:
        fail("검증", e)

    for c in report.get("checks", []):
        mark = {"OK": "✅", "VIOLATION": "❌", "MISSING": "⚠️", "UNKNOWN": "❔"}.get(
            c.get("status"), "·"
        )
        print(f"      {mark} {c.get('label')}")
        if c.get("status") in ("VIOLATION", "MISSING") and c.get("reason"):
            print(f"         {c['reason']}")

    if report.get("estimated_monthly_pay") is not None:
        print(f"\n      예상 월급 : {report['estimated_monthly_pay']:,}원")
    if report.get("wage_shortfall"):
        print(f"      최저임금 차액 : {report['wage_shortfall']:,}원/월")

    problems = [
        c["label"] for c in report.get("checks", [])
        if c.get("status") in ("VIOLATION", "MISSING")
    ]

    # ------------------------------------------- 3. 계약서 + 서명 요청
    print(f"\n[3/3] POST /contracts/analyze-sign  (문제 {len(problems)}건)")
    if problems and not force:
        print("      ⚠️ 위반·누락이 있어 서명 요청이 막힙니다 (409). 의도된 동작입니다.")
        print("         실제 서비스에서는 사용자가 조건을 고치거나 알고도 진행합니다.")
        print("         그대로 진행하려면: python3 spikes/full_pipeline.py --force")
        print("\n✅ 추출 → 검증까지 정상 동작 확인")
        return

    body = {
        "terms": terms,
        "worker_name": (terms.get("worker_name") or {}).get("value") or "김하늘",
        "worker_email": EMAIL,
        "employer_name": (terms.get("employer_name") or {}).get("value") or "박정호",
        "employer_email": EMAIL,
        "entry_path": "PHOTO",
        "proceed_with_violations": True,
    }
    try:
        result = call(base, "POST", "/contracts/analyze-sign", body)
    except Exception as e:
        fail("서명 요청", e)

    doc_id = result["document_id"]
    print(f"      문서 ID : {doc_id}")
    print(f"      상태    : {result['status']}")

    print("\n✅ 전 구간 통과")
    print("\n다음:")
    print(f"  1. {EMAIL} 메일함에서 근로자 → 사업주 순서로 서명")
    print("  2. 서버 로그에서 아래 두 줄 확인 (reconcile 동작 검증)")
    print(f"       문서 {doc_id} 상태 갱신: ...")
    print(f"       문서 {doc_id} 동기화 완료: ... (n/2 서명)")
    print(f"  3. python3 spikes/api_e2e.py status {doc_id}")


if __name__ == "__main__":
    main()
