"""
추출 결과를 정답 라벨과 대조한다.

full_pipeline.py 는 개수만 보여준다. 그것만으로는
"몇 개 읽었나"는 알아도 "제대로 읽었나"는 모른다.
특히 위험한 두 경우를 놓친다.

  1. 빈칸에 값을 지어냄        (계약서에 없는 걸 만들어냄)
  2. 틀리게 읽고 confidence HIGH (사용자가 검수할 기회를 잃음)

이 스크립트는 필드별로 정답과 맞춰 그 둘을 드러낸다.

실행:
    cd ~/AI-Builder-Sprint
    set -a; source .env; set +a
    python3 spikes/check_extract.py spikes/fixtures/handwritten_01.png

정답 라벨은 같은 이름 + _answer.json 을 찾는다.
    spikes/fixtures/handwritten_01.png
    spikes/fixtures/handwritten_01_answer.json
"""

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API_BASE = os.environ.get(
    "API_BASE", "https://ai-builder-sprint-production.up.railway.app"
)


def upload(image: Path) -> dict:
    content = image.read_bytes()
    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    boundary = f"----fairsign{uuid.uuid4().hex}"

    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{image.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])

    req = urllib.request.Request(
        API_BASE + "/contracts/extract", data=body, method="POST"
    )
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"추출 실패 HTTP {e.code}\n{e.read().decode('utf-8', 'replace')[:400]}")


def norm(value) -> str:
    """비교용 정규화 — 공백·쉼표를 무시한다."""
    if value is None:
        return ""
    return str(value).replace(",", "").replace(" ", "").strip()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("사용법: python3 spikes/check_extract.py <이미지경로>")

    image = Path(sys.argv[1])
    if not image.exists():
        sys.exit(f"사진이 없습니다: {image}")

    answer_path = image.with_name(f"{image.stem}_answer.json")
    if not answer_path.exists():
        sys.exit(f"정답 라벨이 없습니다: {answer_path}")

    answer = {
        k: v for k, v in json.loads(answer_path.read_text()).items()
        if not k.startswith("_")
    }

    print(f"사진 : {image}")
    print(f"정답 : {answer_path}")
    print(f"서버 : {API_BASE}\n추출 중...\n")

    terms = upload(image)

    hallucinated: list[str] = []   # 빈칸인데 값을 만들어냄
    wrong_confident: list[str] = []  # 틀렸는데 HIGH
    wrong_flagged: list[str] = []    # 틀렸지만 LOW (사용자가 고칠 수 있음)
    missed: list[str] = []           # 값이 있는데 못 읽음
    correct: list[str] = []

    print(f"{'필드':24} {'정답':18} {'추출':18} 신뢰도")
    print("-" * 78)

    for name, expected in answer.items():
        field = terms.get(name) or {}
        actual = field.get("value")
        conf = field.get("confidence", "?")

        exp_s, act_s = norm(expected), norm(actual)
        ok = exp_s == act_s

        if ok:
            mark, bucket = "✅", correct
        elif expected is None:
            mark, bucket = "🚨", hallucinated       # 없는 걸 만들어냄
        elif actual is None:
            mark, bucket = "➖", missed             # 못 읽음 (안전한 실패)
        elif conf == "HIGH":
            mark, bucket = "❌", wrong_confident    # 가장 위험
        else:
            mark, bucket = "⚠️", wrong_flagged      # 틀렸지만 표시됨

        bucket.append(name)
        print(
            f"{mark} {name:22} {str(expected)[:16]:18} "
            f"{str(actual)[:16]:18} {conf}"
        )

    total = len(answer)
    print("\n" + "=" * 78)
    print(f"  정확        {len(correct):2}/{total}")
    print(f"  못 읽음     {len(missed):2}  {missed}")
    print(f"  틀림(LOW)   {len(wrong_flagged):2}  {wrong_flagged}")
    print("=" * 78)
    print("  ↓ 아래 둘이 진짜 위험이다")
    print(f"  🚨 지어냄        {len(hallucinated):2}  {hallucinated}")
    print(f"  ❌ 틀림+HIGH     {len(wrong_confident):2}  {wrong_confident}")
    print("=" * 78)

    if hallucinated:
        print("\n🚨 빈칸에 값을 만들어냈다. 판정을 왜곡할 수 있다.")
        print("   추출 프롬프트에 '빈칸이면 반드시 null' 을 강화할 것.")
    if wrong_confident:
        print("\n❌ 틀렸는데 confidence가 HIGH다. 사용자가 검수할 기회를 잃는다.")
    if not hallucinated and not wrong_confident:
        print("\n✅ 지어내거나 자신 있게 틀린 항목이 없다.")
        print("   못 읽은 항목은 화면에서 사용자가 채우면 된다.")


if __name__ == "__main__":
    main()
