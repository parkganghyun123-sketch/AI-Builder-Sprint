"""
서명 박스 위치 미리보기

모두싸인에 실제로 보내지 않고, 서명 박스가 PDF의 어디에 놓일지
빨간 사각형으로 그려서 PNG로 저장한다.

발송 → 메일 확인 → 위치 확인의 왕복(한 번에 5분 이상)을 없애기 위한 도구.
offset을 바꿔가며 이 스크립트만 돌리면 즉시 결과를 볼 수 있다.

실행:
    python3 spikes/preview_sign_box.py
    SIGN_OFFSET_X=0.0 SIGN_OFFSET_Y=0.0 python3 spikes/preview_sign_box.py

출력:
    spikes/preview.png

⚠️ 전제: 박스의 좌상단 = anchor 텍스트의 좌상단 + offset × (페이지 폭, 높이)
   모두싸인 문서에 기준점이 명시돼 있지 않아 이 전제를 세웠다.
   실제 발송 결과와 어긋나면 ORIGIN 을 바꿔가며 맞춘다.
"""

import os
import re
import subprocess
import sys

PDF_PATH = os.environ.get("TEST_PDF", "spikes/sample_contract.pdf")
OUT_PATH = "spikes/preview.png"
DPI = 100

ANCHOR_EMPLOYER = "(사업주 서명)"
ANCHOR_WORKER = "(근로자 서명)"

OFFSET_X = float(os.environ.get("SIGN_OFFSET_X", 0.10))
OFFSET_Y = float(os.environ.get("SIGN_OFFSET_Y", -0.012))
BOX_W = float(os.environ.get("SIGN_BOX_W", 0.14))
BOX_H = float(os.environ.get("SIGN_BOX_H", 0.045))

# anchor의 어느 지점을 기준으로 offset을 더할지
#   topleft  : anchor 좌상단   (기본 가정)
#   topright : anchor 우상단   (텍스트 오른쪽에 붙이고 싶을 때)
ORIGIN = os.environ.get("SIGN_ORIGIN", "topleft")


def anchor_boxes() -> tuple[float, float, dict]:
    """pdftotext -bbox 로 anchor 텍스트의 좌표를 얻는다."""
    try:
        xml = subprocess.run(
            ["pdftotext", "-bbox", PDF_PATH, "-"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
    except FileNotFoundError:
        sys.exit("pdftotext가 필요합니다: brew install poppler")

    pages = re.findall(
        r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', xml, re.S
    )
    if len(pages) < 2:
        sys.exit("2페이지 이상인 PDF를 기대했습니다.")

    # 서명란은 마지막 페이지에 있다
    pw, ph, body = pages[-1]
    pw, ph = float(pw), float(ph)

    words = re.findall(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)" '
        r'xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>',
        body,
    )
    parsed = [(float(a), float(b), float(c), float(d), w)
              for a, b, c, d, w in words]

    found: dict[str, tuple[float, float, float, float]] = {}
    for anchor in (ANCHOR_EMPLOYER, ANCHOR_WORKER):
        head, tail = anchor.split(" ")  # "(사업주", "서명)"
        for i, (x0, y0, x1, y1, w) in enumerate(parsed):
            if w != head or i + 1 >= len(parsed):
                continue
            nx0, ny0, nx1, ny1, nw = parsed[i + 1]
            if nw != tail or abs(ny0 - y0) > 3:
                continue
            found[anchor] = (x0, y0, nx1, ny1)  # 두 단어를 합친 박스
            break
        else:
            sys.exit(f"anchor를 찾지 못했습니다: {anchor}")

    return pw, ph, found


def main() -> None:
    if not os.path.exists(PDF_PATH):
        sys.exit(f"PDF가 없습니다: {PDF_PATH}")

    pw, ph, anchors = anchor_boxes()
    scale = DPI / 72.0

    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI),
         "-f", "2", "-l", "2", "-singlefile", PDF_PATH, "spikes/_preview_base"],
        check=True, capture_output=True,
    )

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("Pillow가 필요합니다: pip3 install pillow")

    img = Image.open("spikes/_preview_base.png").convert("RGB")
    draw = ImageDraw.Draw(img)

    print(f"페이지: {pw:.0f} x {ph:.0f} pt")
    print(f"offset: x={OFFSET_X}  y={OFFSET_Y}   "
          f"box: {BOX_W} x {BOX_H}   origin: {ORIGIN}\n")

    for anchor, (ax0, ay0, ax1, ay1) in anchors.items():
        # anchor 자체 — 파란 실선
        draw.rectangle(
            [ax0 * scale, ay0 * scale, ax1 * scale, ay1 * scale],
            outline=(40, 90, 220), width=2,
        )

        base_x = ax0 if ORIGIN == "topleft" else ax1
        bx0 = base_x + OFFSET_X * pw
        by0 = ay0 + OFFSET_Y * ph
        bx1 = bx0 + BOX_W * pw
        by1 = by0 + BOX_H * ph

        # 서명 박스 예상 위치 — 빨간 실선
        draw.rectangle(
            [bx0 * scale, by0 * scale, bx1 * scale, by1 * scale],
            outline=(220, 40, 40), width=3,
        )

        over = "⚠️ 페이지 밖으로 벗어남" if bx1 > pw else ""
        print(f"  {anchor}")
        print(f"    anchor  x {ax0:6.1f}-{ax1:6.1f}  y {ay0:6.1f}-{ay1:6.1f}")
        print(f"    서명박스 x {bx0:6.1f}-{bx1:6.1f}  y {by0:6.1f}-{by1:6.1f}  {over}")

    img.save(OUT_PATH)
    try:
        os.remove("spikes/_preview_base.png")
    except OSError:
        pass  # 중간 파일 정리 실패는 무시
    print(f"\n✅ {OUT_PATH} 저장 — 파란색=anchor, 빨간색=서명 박스")


if __name__ == "__main__":
    main()
