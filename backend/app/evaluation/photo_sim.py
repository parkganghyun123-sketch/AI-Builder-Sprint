"""
촬영 조건 시뮬레이션 — 평가셋을 '휴대폰으로 찍은 사진'처럼 망가뜨린다.

평가셋 10장은 Pillow로 깨끗하게 렌더링한 합성 이미지다.
그 상태의 정확도 100%는 "실제 사진도 그러냐"는 질문에 답하지 못한다.

이 모듈은 실제 촬영에서 생기는 왜곡을 단계적으로 입힌다.
  1. 원근 왜곡   — 정면이 아닌 각도에서 찍음
  2. 회전        — 손으로 든 각도
  3. 조명 불균일 — 한쪽이 밝고 반대쪽이 어두움
  4. 그림자      — 찍는 사람 손/몸 그림자
  5. 초점 흐림   — 흔들림
  6. 압축 손실   — JPEG 저장

⚠️ 이것은 손글씨 테스트가 아니다.
   글자 자체는 여전히 인쇄체다. 진짜 손글씨는 사람이 직접 써서
   찍은 사진으로만 검증할 수 있다.
   이 모듈이 답하는 질문은 "촬영 조건이 나빠도 읽히는가" 하나다.

실행:
    cd backend
    python -m app.evaluation.photo_sim                 # 전부, 중간 강도
    python -m app.evaluation.photo_sim --level hard    # 강하게
    python -m app.evaluation.photo_sim --level light

결과:
    app/evaluation/contracts_photo/contract_01_photo.jpg ...

이후:
    python3 spikes/full_pipeline.py \\
        backend/app/evaluation/contracts_photo/contract_01_photo.jpg
"""

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SRC_DIR = Path(__file__).parent / "contracts"
OUT_DIR = Path(__file__).parent / "contracts_photo"

# 강도별 설정. 실제 사진이 어느 정도인지 몰라 세 단계를 둔다.
LEVELS = {
    "light": dict(warp=0.008, rotate=1.0, light=0.18, shadow=0.10, blur=0.4, jpeg=88),
    "medium": dict(warp=0.020, rotate=2.5, light=0.32, shadow=0.20, blur=0.8, jpeg=72),
    "hard": dict(warp=0.038, rotate=5.0, light=0.48, shadow=0.32, blur=1.4, jpeg=55),
}


def _perspective(img: Image.Image, amount: float, rng: random.Random) -> Image.Image:
    """
    네 모서리를 조금씩 밀어 원근 왜곡을 만든다.
    Pillow의 QUAD 변환은 '원본에서 이 사각형을 떼어내 채운다'는 의미다.
    """
    w, h = img.size
    d = amount * min(w, h)

    def jitter() -> float:
        return rng.uniform(-d, d)

    quad = (
        jitter(), jitter(),                    # 좌상
        jitter(), h + jitter(),                # 좌하
        w + jitter(), h + jitter(),            # 우하
        w + jitter(), jitter(),                # 우상
    )
    return img.transform((w, h), Image.QUAD, quad, Image.BICUBIC, fillcolor=(246, 244, 240))


def _lighting(img: Image.Image, strength: float, rng: random.Random) -> Image.Image:
    """
    한쪽에서 빛이 드는 상황. 밝기 기울기를 곱한다.
    실내 조명은 대개 한 방향에서 오므로 선형 기울기로 충분하다.
    """
    w, h = img.size
    grad = Image.new("L", (w, h))
    px = grad.load()

    # 빛의 방향을 무작위로 정한다
    ax, ay = rng.uniform(-1, 1), rng.uniform(-1, 1)
    norm = max(abs(ax) + abs(ay), 1e-6)
    ax, ay = ax / norm, ay / norm

    for y in range(h):
        fy = ay * (y / h - 0.5)
        row = 128 + fy * 255 * strength
        for x in range(w):
            fx = ax * (x / w - 0.5)
            px[x, y] = max(0, min(255, int(row + fx * 255 * strength)))

    # 128을 중립으로 보고 곱한다 → 한쪽은 밝게, 반대쪽은 어둡게
    base = img.convert("RGB")
    bright = Image.new("RGB", (w, h), (255, 255, 255))
    return Image.composite(bright, base, grad).convert("RGB") if False else Image.blend(
        base, Image.merge("RGB", (grad, grad, grad)), strength * 0.55
    )


def _shadow(img: Image.Image, strength: float, rng: random.Random) -> Image.Image:
    """찍는 사람의 손/몸 그림자. 한쪽 모서리에서 들어오는 부드러운 어두움."""
    w, h = img.size
    layer = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(layer)

    # 네 변 중 하나에서 들어오는 삼각형 그림자
    side = rng.choice(["left", "right", "top", "bottom"])
    depth = rng.uniform(0.18, 0.42)
    if side == "left":
        poly = [(0, 0), (w * depth, 0), (0, h)]
    elif side == "right":
        poly = [(w, 0), (w, h), (w * (1 - depth), h)]
    elif side == "top":
        poly = [(0, 0), (w, 0), (0, h * depth)]
    else:
        poly = [(0, h), (w, h), (w, h * (1 - depth))]

    draw.polygon(poly, fill=int(255 * strength))
    layer = layer.filter(ImageFilter.GaussianBlur(min(w, h) * 0.06))

    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(dark, img, layer.point(lambda v: int(v * 0.85)))


def photograph(
    src: Path,
    dst: Path,
    level: str = "medium",
    seed: int | None = None,
) -> None:
    cfg = LEVELS[level]
    rng = random.Random(seed if seed is not None else hash(src.name) & 0xFFFF)

    img = Image.open(src).convert("RGB")

    img = _perspective(img, cfg["warp"], rng)
    img = img.rotate(
        rng.uniform(-cfg["rotate"], cfg["rotate"]),
        resample=Image.BICUBIC,
        fillcolor=(246, 244, 240),
    )
    img = _lighting(img, cfg["light"], rng)
    img = _shadow(img, cfg["shadow"], rng)
    if cfg["blur"] > 0:
        img = img.filter(ImageFilter.GaussianBlur(cfg["blur"]))

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=cfg["jpeg"])


def main() -> None:
    parser = argparse.ArgumentParser(description="평가셋을 촬영 사진처럼 변형")
    parser.add_argument(
        "--level", choices=list(LEVELS), default="medium", help="왜곡 강도"
    )
    args = parser.parse_args()

    sources = sorted(SRC_DIR.glob("*.png"))
    if not sources:
        raise SystemExit(
            f"원본이 없습니다: {SRC_DIR}\n"
            "  python -m app.evaluation.generate_contracts 를 먼저 실행하세요."
        )

    for src in sources:
        dst = OUT_DIR / f"{src.stem}_photo.jpg"
        photograph(src, dst, level=args.level)
        print(f"  {src.name} → {dst.name}")

    print(f"\n{len(sources)}장 생성 ({args.level}) → {OUT_DIR}")
    print("\n다음:")
    print("  python3 spikes/full_pipeline.py \\")
    print(f"      {OUT_DIR.relative_to(Path.cwd().parent)}/contract_01_photo.jpg")


if __name__ == "__main__":
    main()
