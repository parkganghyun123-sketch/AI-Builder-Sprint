"""
권리 안내 테스트.

⚠️ 이 모듈은 법 조문을 사용자에게 옮기는 곳이다. 문구가 틀리면
   사용자가 잘못 알고 사장님께 말한다. 그래서 내용까지 검사한다.
"""

import pytest

from app.validation.entitlements import (
    ENTITLEMENTS,
    Audience,
    all_entitlements,
    by_code,
    for_audiences,
)

# 확정적 법률 결론을 뜻하는 표현.
#
# ⚠️ AGENTS.md: "확정적인 법률 판단을 내리지 않고, FairSign을 법률 상담
#    서비스로 표현하지 않습니다."
#    "신고할 수 있습니다" 를 우리가 말하면 그 결과에 책임이 생긴다.
#    법이 무엇을 정하고 있는지를 옮기고 판단은 사용자와 전문가가 한다.
FORBIDDEN_PHRASES = (
    "신고하세요",
    "신고할 수 있습니다",
    "고발",
    "위법입니다",
    "불법입니다",
    "받을 수 있는 것이 확실",
    "소송",
    "처벌받습니다",
)


def test_모든_안내에_법적_근거가_있다():
    """
    ⚠️ 근거 없는 법령 설명을 만들지 않는다(AGENTS.md).
       조문 번호와 KB 출처 ID가 둘 다 있어야 한다.
    """
    for item in ENTITLEMENTS:
        assert item.legal_basis, item.code
        assert "제" in item.legal_basis or "법" in item.legal_basis, item.code
        assert "SRC-" in item.legal_basis, f"{item.code}: KB 출처 ID 누락"


def test_확정적_법률_결론을_말하지_않는다():
    for item in ENTITLEMENTS:
        text = f"{item.summary} {item.detail} {item.employer_penalty or ''}"
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in text, f"{item.code} 에 '{phrase}'"


def test_코드가_중복되지_않는다():
    codes = [item.code for item in ENTITLEMENTS]
    assert len(codes) == len(set(codes))


def test_판정_가능_여부를_정확히_표시한다():
    """
    ⚠️ verifiable=False 인 항목을 화면이 "위반"처럼 보이게 만들면
       확인하지도 않은 사실을 단정하는 셈이 된다.

    계약서로 확인할 수 있는 것만 True 여야 한다.
    """
    verifiable = {i.code for i in ENTITLEMENTS if i.verifiable}

    # 계약 조건과 대조할 수 있는 것들
    assert "MINOR_WORKING_HOURS" in verifiable
    assert "MINOR_NIGHT_WORK" in verifiable
    assert "SHORT_TIME_EXCLUSIONS" in verifiable
    assert "PREGNANT_NO_OVERTIME_NIGHT" in verifiable

    # 서류 비치·신청 여부는 계약서에 없다
    assert "MINOR_GUARDIAN_CONSENT" not in verifiable
    assert "PREGNANT_REDUCED_HOURS" not in verifiable
    assert "MENSTRUAL_LEAVE" not in verifiable
    assert "DISABILITY_REASONABLE_ACCOMMODATION" not in verifiable


def test_모든_근로자_안내는_항상_포함된다():
    """대상을 하나도 고르지 않아도 공통 권리는 보여야 한다."""
    result = for_audiences(set())
    codes = {item["code"] for item in result}

    assert "SHORT_TIME_EXCLUSIONS" in codes
    assert "CONTRACT_COPY" in codes
    # 해당하지 않는 것은 빠진다
    assert "MINOR_GUARDIAN_CONSENT" not in codes


def test_대상별로_골라준다():
    codes = {i["code"] for i in for_audiences({Audience.MINOR})}

    assert "MINOR_GUARDIAN_CONSENT" in codes
    assert "MINOR_OWN_CONTRACT" in codes
    assert "CONTRACT_COPY" in codes  # EVERYONE 은 항상
    assert "PREGNANT_REDUCED_HOURS" not in codes


def test_여러_대상을_한꺼번에_고를_수_있다():
    """임신 중인 미성년 근로자도 있을 수 있다."""
    codes = {
        i["code"] for i in for_audiences({Audience.MINOR, Audience.PREGNANT})
    }

    assert "MINOR_GUARDIAN_CONSENT" in codes
    assert "PREGNANT_REDUCED_HOURS" in codes


def test_전체_목록은_필터링하지_않는다():
    """
    ⚠️ 화면이 전체를 받아 스스로 필터링하면 서버는 사용자가 임신했는지
       장애가 있는지 알지 못한다. 민감정보를 다루는 가장 안전한 방법이다.
    """
    assert len(all_entitlements()) == len(ENTITLEMENTS)


def test_사업주_제재는_사업주_의무에만_붙는다():
    """
    ⚠️ 근로자가 못 한 일에 제재를 붙이면 근로자를 탓하는 화면이 된다.
       제재가 붙은 항목은 전부 사업주의 의무여야 한다.
    """
    with_penalty = {i.code for i in ENTITLEMENTS if i.employer_penalty}

    assert with_penalty == {
        "MINOR_GUARDIAN_CONSENT",  # 서류 비치는 사업주 의무
        "PREGNANT_REDUCED_HOURS",  # 단축 허용은 사업주 의무
        "CONTRACT_COPY",  # 교부는 사업주 의무
    }


@pytest.mark.parametrize(
    "code,must_contain",
    [
        # 숫자가 틀리면 사용자가 잘못 알고 말한다. 조문 그대로여야 한다.
        ("MINOR_WORKING_HOURS", "7시간"),
        ("MINOR_NIGHT_WORK", "10시"),
        ("PREGNANT_REDUCED_HOURS", "32주"),  # 2025-02-23 시행으로 36주→32주
        ("POSTPARTUM_NURSING_TIME", "30분"),
        ("MENSTRUAL_LEAVE", "월 1일"),
        ("SHORT_TIME_EXCLUSIONS", "15시간"),
    ],
)
def test_핵심_수치가_조문과_일치한다(code, must_contain):
    item = by_code(code)
    assert item is not None
    assert must_contain in f"{item.summary} {item.detail}"


def test_주15시간_안내가_세_가지를_모두_말한다():
    """
    ⚠️ 주휴수당만 말하면 절반만 알려주는 것이다.
       15시간 미만이면 연차와 퇴직금도 함께 빠진다.
    """
    item = by_code("SHORT_TIME_EXCLUSIONS")
    text = f"{item.summary} {item.detail}"

    assert "주휴" in text
    assert "연차" in text
    assert "퇴직" in text
    # 그래도 위법이라고 단정하지 않는다
    assert "위법한 것은 아니" in text
