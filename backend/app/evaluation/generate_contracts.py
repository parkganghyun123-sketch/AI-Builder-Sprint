"""
평가셋용 가상 계약서 '사진'(PNG) 생성.

WeasyPrint(GTK 시스템 의존성) 없이도 실제 Upstage API로 Document Parse·
Information Extract를 테스트하려고, 표준근로계약서 형식 텍스트를
Pillow로 직접 그린다. specs.py의 값을 그대로 그리므로, specs.py가
곧 정답 라벨이 된다 (evaluate.py가 비교 기준으로 사용).

실행:
    cd backend
    python -m app.evaluation.generate_contracts
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.evaluation.specs import CONTRACT_SPECS

FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/malgunbd.ttf"

W, H = 1240, 1600
OUT_DIR = Path(__file__).parent / "contracts"


def _hhmm_to_korean(value: str | None) -> str:
    """'09:00' → '09시 00분'. 표준양식은 시·분이 이렇게 표기된다."""
    if not value:
        return ""
    h, _, m = value.partition(":")
    return f"{h}시 {m}분"


def _build_lines(spec: dict) -> list[tuple[str, bool, int]]:
    """(텍스트, 굵게 여부, 폰트 크기) 목록. 값이 없는 항목은 빈칸으로 그린다."""
    lines: list[tuple[str, bool, int]] = [
        ("표 준 근 로 계 약 서", True, 30),
        ("", False, 14),
        (
            f"{spec['employer_business_name']} (이하 '사업주'라 함)과(와) "
            f"{spec['worker_name']} (이하 '근로자'라 함)은",
            False,
            20,
        ),
        ("다음과 같이 근로계약을 체결한다.", False, 20),
        ("", False, 8),
        (
            f"1. 근로계약기간 : {spec['contract_start']} 부터 {spec['contract_end']} 까지",
            False,
            20,
        ),
        (f"2. 근 무 장 소 : {spec['workplace']}", False, 20),
        (f"3. 업무의 내용 : {spec['job_description']}", False, 20),
    ]

    work_time = (
        f"4. 소정근로시간 : {_hhmm_to_korean(spec['work_start_time'])}부터 "
        f"{_hhmm_to_korean(spec['work_end_time'])}까지"
    )
    if spec["break_start_time"] and spec["break_end_time"]:
        work_time += (
            f" (휴게시간 : {_hhmm_to_korean(spec['break_start_time'])} ~ "
            f"{_hhmm_to_korean(spec['break_end_time'])})"
        )
    lines.append((work_time, False, 20))

    holiday = f"매주 ({spec['weekly_holiday_day']}) 요일" if spec["weekly_holiday_day"] else "매주 (   ) 요일"
    lines.append(
        (f"5. 근무일/휴일 : 매주 {spec['work_days_per_week']}일 근무, 주휴일 {holiday}", False, 20)
    )

    wage_label = {"HOURLY": "시간급", "DAILY": "일급", "MONTHLY": "월급"}[spec["wage_type"]]
    lines.append(("6. 임    금", False, 20))
    lines.append((f"   - 시간(일, 월)급 : {wage_label} 금 {int(spec['wage_amount']):,}원", False, 20))
    lines.append((f"   - 상여금 : {spec['has_bonus']}", False, 20))
    lines.append(
        (f"   - 기타급여(제수당 등) : {spec['other_allowance'] or ''}", False, 20)
    )
    lines.append((f"   - 임금지급일 : {spec['payday']} (휴일의 경우는 전일 지급)", False, 20))
    lines.append((f"   - 지급방법 : {spec['payment_method']}", False, 20))
    lines.append(("", False, 8))

    employer_line = f"(사업주)   사업체명 : {spec['employer_business_name']}"
    if spec["employer_phone"]:
        employer_line += f"        전화 : {spec['employer_phone']}"
    lines.append((employer_line, False, 20))
    lines.append((f"           주    소 : {spec['employer_address']}", False, 20))
    lines.append((f"           대 표 자 : {spec['employer_name']}               (서명)", False, 20))
    lines.append((f"(근로자)   주    소 : {spec['worker_address']}", False, 20))
    lines.append((f"           연 락 처 : {spec['worker_contact']}", False, 20))
    lines.append((f"           성    명 : {spec['worker_name']}               (서명)", False, 20))

    return lines


def render(spec: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    y = 60
    for text, bold, size in _build_lines(spec):
        font = ImageFont.truetype(FONT_BOLD_PATH if bold else FONT_PATH, size)
        if bold:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) / 2, y), text, font=font, fill="black")
        else:
            draw.text((80, y), text, font=font, fill="black")
        y += size + 18

    return img


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for spec in CONTRACT_SPECS:
        img = render(spec)
        out = OUT_DIR / f"{spec['id']}.png"
        img.save(out)
        print(f"저장: {out}")


if __name__ == "__main__":
    main()
