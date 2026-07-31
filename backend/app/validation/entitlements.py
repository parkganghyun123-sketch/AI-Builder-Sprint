"""
권리 안내 — "몰라서 못 받는 것들" (B 담당)

--- 판정과 무엇이 다른가 ---

``rules.py`` 의 ``CheckResult`` 는 **판정**이다.
계약서에 적힌 값을 법정 기준과 대조해 OK / VIOLATION / MISSING / UNKNOWN 을 낸다.

이 모듈의 ``Entitlement`` 는 **안내**다.
"당신에게 이런 권리가 있는데, 계약서만으로는 확인할 수 없습니다"를 알려준다.

⚠️ 둘을 섞으면 안 된다.
   친권자 동의서를 안 받은 것은 사업주의 의무 위반이지만, 우리는 그 사실을
   계약서로 알 수 없다. 이걸 VIOLATION 으로 표시하면 확인하지도 않은 것을
   위반이라고 단정하는 셈이다. 반대로 안내를 아예 안 하면
   "몰라서 못 받는" 상태가 그대로 남는다.

--- 왜 이 모듈이 필요한가 ---

README 의 근거: 근로계약서 미작성 이유 1위가 **"작성해야 하는지 몰라서" 40.4%**.
나쁜 마음이 아니라 무지가 원인이다. 그건 계약서 작성만의 이야기가 아니다.
미성년자·임산부에게는 법이 따로 정해 둔 보호가 있는데, 그 존재 자체를
모르면 있으나 마나다.

--- 개인정보 원칙 ---

⚠️ 임신 여부·장애 여부는 민감정보다. **서버에 저장하지 않는다.**
   이 모듈은 순수 함수이고, 프로필을 받아 목록을 돌려줄 뿐 어디에도 남기지 않는다.
   저장이 필요 없는 안내는 아예 프론트엔드에서 필터링해도 된다
   (``all_entitlements()`` 가 전체 목록을 주므로 서버가 프로필을 모를 수 있다).

--- 절대 하지 않는 것 ---

⚠️ 확정적 법률 결론을 내리지 않는다.
   "신고할 수 있습니다" / "받을 수 있습니다" / "위법입니다" 를 쓰지 않는다.
   법이 무엇을 정하고 있는지를 옮기고, 판단은 사용자와 전문가가 한다.
   AGENTS.md · KB.md 의 공용 규칙이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Audience(str, Enum):
    """이 안내가 누구에게 해당하는가."""

    EVERYONE = "EVERYONE"  # 모든 근로자
    MINOR = "MINOR"  # 만 18세 미만
    PREGNANT = "PREGNANT"  # 임신 중
    POSTPARTUM = "POSTPARTUM"  # 출산 후 1년 미만 (수유·육아시간)
    FEMALE = "FEMALE"  # 여성 근로자
    DISABILITY = "DISABILITY"  # 장애가 있는 근로자


@dataclass(frozen=True)
class Entitlement:
    """
    권리 안내 한 건.

    ⚠️ ``verifiable`` 을 반드시 정확히 표시할 것.
       False 인데 화면이 "위반입니다"처럼 보이게 만들면
       확인하지도 않은 사실을 단정하는 셈이 된다.
    """

    code: str
    label: str
    audience: Audience
    summary: str  # 한 줄 요약. 카드 제목 아래 들어간다
    detail: str  # 무엇을 어떻게 하면 되는지
    legal_basis: str  # 조문 + KB 출처 ID
    # 계약서 값으로 대조해 판정할 수 있는가.
    #   True  → rules.py 에 대응하는 판정이 있거나 있어야 한다
    #   False → 안내만 한다. 위반 여부를 표시하지 않는다
    verifiable: bool = False
    # 사업주에게 부과되는 제재. 있으면 표시한다.
    # ⚠️ "신고하세요"라고 쓰지 않는다. 법이 정한 내용만 옮긴다.
    employer_penalty: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "label": self.label,
            "audience": self.audience.value,
            "summary": self.summary,
            "detail": self.detail,
            "legal_basis": self.legal_basis,
            "verifiable": self.verifiable,
            "employer_penalty": self.employer_penalty,
        }


# ============================================================
# 목록
#
# ⚠️ 여기에 항목을 추가할 때는 KB.md 에 출처를 먼저 기록할 것.
#    출처 우선순위: 국가법령정보센터 > 고용노동부 > 기타 공공기관.
#    뉴스·블로그·모델 기억은 근거로 쓰지 않는다.
# ============================================================

ENTITLEMENTS: tuple[Entitlement, ...] = (
    # ---------------------------------------------------------- 만 18세 미만
    Entitlement(
        code="MINOR_GUARDIAN_CONSENT",
        label="친권자 동의서와 가족관계증명서",
        audience=Audience.MINOR,
        summary="사장님이 부모님 동의서와 가족관계증명서를 받아 사업장에 두어야 합니다.",
        detail=(
            "만 18세 미만을 고용하는 사업주는 나이를 증명하는 가족관계기록사항에 "
            "관한 증명서와 친권자 또는 후견인의 동의서를 사업장에 갖추어 두어야 "
            "합니다. 이건 근로자가 챙길 일이 아니라 사업주의 의무입니다. "
            "제출한 기억이 없다면 사장님께 여쭤보세요."
        ),
        legal_basis="근로기준법 제66조 (SRC-LSA-66)",
        verifiable=False,  # 계약서로는 서류 비치 여부를 알 수 없다
        employer_penalty="미비 시 사업주에게 500만원 이하 과태료",
    ),
    Entitlement(
        code="MINOR_OWN_CONTRACT",
        label="계약과 임금은 본인이",
        audience=Audience.MINOR,
        summary="부모님이 대신 계약할 수 없고, 임금은 본인이 직접 받습니다.",
        detail=(
            "친권자나 후견인은 미성년자를 대신해 근로계약을 체결할 수 없습니다. "
            "임금도 미성년자가 독자적으로 청구할 수 있습니다. "
            "부모님 계좌로 임금을 받고 있다면 본인 명의 계좌로 바꿔달라고 "
            "요청할 수 있습니다."
        ),
        legal_basis="근로기준법 제67조·제68조 (SRC-LSA-67, SRC-LSA-68)",
        verifiable=False,
    ),
    Entitlement(
        code="MINOR_WORKING_HOURS",
        label="근로시간 상한",
        audience=Audience.MINOR,
        summary="1일 7시간·주 35시간을 넘길 수 없습니다. 합의해도 1일 1시간·주 5시간까지만 연장됩니다.",
        detail=(
            "만 15세 이상 18세 미만은 1일 7시간, 1주 35시간을 초과할 수 "
            "없습니다. 당사자 합의가 있어도 1일 1시간, 1주 5시간까지만 "
            "연장할 수 있습니다."
        ),
        legal_basis="근로기준법 제69조 (SRC-LSA-69)",
        verifiable=True,  # rules.check_minor_working_hours 가 판정한다
    ),
    Entitlement(
        code="MINOR_NIGHT_WORK",
        label="야간·휴일근로 제한",
        audience=Audience.MINOR,
        summary="밤 10시부터 새벽 6시까지, 그리고 휴일에는 원칙적으로 일할 수 없습니다.",
        detail=(
            "18세 미만자는 오후 10시부터 오전 6시까지의 시간 및 휴일에 "
            "근로시키지 못합니다. 본인의 동의와 고용노동부장관의 인가가 "
            "있는 경우에만 예외가 됩니다."
        ),
        legal_basis="근로기준법 제70조제2항 (SRC-LSA-70)",
        verifiable=True,  # rules.check_minor_night_work 가 판정한다
    ),
    # ---------------------------------------------------------- 임신 중
    Entitlement(
        code="PREGNANT_NO_OVERTIME_NIGHT",
        label="연장·야간·휴일근로 금지",
        audience=Audience.PREGNANT,
        summary="임신 중에는 연장근로를 시킬 수 없고, 야간·휴일근로도 원칙적으로 금지됩니다.",
        detail=(
            "사용자는 임신 중인 여성 근로자에게 시간외근로를 시키지 못합니다. "
            "야간(오후 10시~오전 6시) 및 휴일근로도 본인의 명시적 청구와 "
            "고용노동부장관의 인가가 있는 경우에만 가능합니다."
        ),
        legal_basis="근로기준법 제70조제2항·제71조 (SRC-LSA-70, SRC-LSA-71)",
        verifiable=True,  # 계약 시각과 대조할 수 있다
    ),
    Entitlement(
        code="PREGNANT_REDUCED_HOURS",
        label="임신기 근로시간 단축",
        audience=Audience.PREGNANT,
        summary="임신 12주 이내 또는 32주 이후에는 하루 2시간 단축을 신청할 수 있습니다.",
        detail=(
            "임신 후 12주 이내 또는 32주 이후인 여성 근로자는 1일 2시간의 "
            "근로시간 단축을 신청할 수 있고, 사용자는 이를 허용해야 합니다. "
            "임금을 깎을 수 없습니다. "
            "단축 개시 예정일 3일 전까지 의사의 진단서를 첨부해 신청합니다. "
            "(2025-02-23 시행으로 '36주 이후'에서 '32주 이후'로 확대되었습니다)"
        ),
        legal_basis="근로기준법 제74조제7항·제8항 (SRC-LSA-74)",
        verifiable=False,  # 임신 주수는 계약서에 없다
        employer_penalty="허용하지 않으면 사업주에게 500만원 이하 과태료",
    ),
    Entitlement(
        code="PREGNANT_SCHEDULE_CHANGE",
        label="출퇴근 시각 변경 신청",
        audience=Audience.PREGNANT,
        summary="하루 일하는 시간을 유지하면서 출퇴근 시각만 바꿔달라고 요청할 수 있습니다.",
        detail=(
            "임신 중인 여성 근로자가 1일 소정근로시간을 유지하면서 업무의 "
            "시작 및 종료 시각의 변경을 신청하는 경우 사용자는 이를 허용해야 "
            "합니다. 혼잡한 시간대의 출퇴근을 피할 수 있습니다."
        ),
        legal_basis="근로기준법 제74조제9항 (SRC-LSA-74)",
        verifiable=False,
    ),
    Entitlement(
        code="PREGNANT_CHECKUP_TIME",
        label="태아검진 시간",
        audience=Audience.PREGNANT,
        summary="임산부 정기건강진단을 받는 데 필요한 시간을 청구할 수 있고, 임금을 깎을 수 없습니다.",
        detail=(
            "사용자는 임신한 여성 근로자가 모자보건법에 따른 임산부 정기건강진단을 "
            "받는 데 필요한 시간을 청구하는 경우 이를 허용해야 하며, "
            "그 시간에 대해 임금을 삭감해서는 안 됩니다."
        ),
        legal_basis="근로기준법 제74조의2 (SRC-LSA-74-2)",
        verifiable=False,
    ),
    # ---------------------------------------------------------- 출산 후
    Entitlement(
        code="POSTPARTUM_NURSING_TIME",
        label="육아 시간",
        audience=Audience.POSTPARTUM,
        summary="생후 1년 미만 아이가 있으면 하루 두 번, 각 30분 이상의 유급 수유 시간을 청구할 수 있습니다.",
        detail=(
            "생후 1년 미만의 유아를 가진 여성 근로자가 청구하면 사용자는 "
            "1일 2회 각각 30분 이상의 유급 수유 시간을 주어야 합니다."
        ),
        legal_basis="근로기준법 제75조 (SRC-LSA-75)",
        verifiable=False,
    ),
    # ---------------------------------------------------------- 여성 근로자
    Entitlement(
        code="MENSTRUAL_LEAVE",
        label="생리휴가",
        audience=Audience.FEMALE,
        summary="청구하면 월 1일의 생리휴가를 받을 수 있습니다(무급).",
        detail=(
            "사용자는 여성 근로자가 청구하면 월 1일의 생리휴가를 주어야 합니다. "
            "단시간·아르바이트 근로자도 대상입니다."
        ),
        legal_basis="근로기준법 제73조 (SRC-LSA-73)",
        verifiable=False,
    ),
    # ---------------------------------------------------------- 장애
    Entitlement(
        code="DISABILITY_REASONABLE_ACCOMMODATION",
        label="정당한 편의 제공 요구",
        audience=Audience.DISABILITY,
        summary="일하는 데 필요한 시설·도구·업무 조정을 요구할 수 있습니다.",
        detail=(
            "사용자는 장애인이 장애가 없는 사람과 동등하게 근로할 수 있도록 "
            "정당한 편의를 제공해야 합니다. 시설·장비 개조, 작업 일정 조정, "
            "보조인 배치 등이 포함됩니다. 정당한 편의 제공을 거부하는 것도 "
            "차별에 해당합니다.\n"
            "근로시간·최저임금 등 기본 근로조건은 다른 근로자와 동일하게 "
            "적용됩니다."
        ),
        legal_basis="장애인차별금지 및 권리구제 등에 관한 법률 제11조 (SRC-ADA-11)",
        verifiable=False,
    ),
    # ---------------------------------------------------------- 모든 근로자
    Entitlement(
        code="SHORT_TIME_EXCLUSIONS",
        label="주 15시간의 벽",
        audience=Audience.EVERYONE,
        summary="주 소정근로시간이 15시간 미만이면 주휴수당·연차·퇴직금이 모두 빠집니다.",
        detail=(
            "4주 평균 1주 소정근로시간이 15시간 미만인 근로자에게는 "
            "주휴일(제55조)과 연차유급휴가(제60조)가 적용되지 않고, "
            "퇴직급여 지급 대상에서도 제외됩니다. "
            "주 15시간 미만 계약 자체가 위법한 것은 아니지만, "
            "세 가지가 한꺼번에 빠진다는 사실은 계약서에 적혀 있지 않습니다."
        ),
        legal_basis=(
            "근로기준법 제18조제3항 · 근로자퇴직급여 보장법 제4조제1항 "
            "(SRC-LSA-18, SRC-ERBA-4)"
        ),
        verifiable=True,  # rules.check_weekly_holiday 가 계산한다
    ),
    Entitlement(
        code="CONTRACT_COPY",
        label="계약서 교부",
        audience=Audience.EVERYONE,
        summary="사장님은 근로계약서를 써서 근로자에게 한 부 주어야 합니다.",
        detail=(
            "사용자는 임금, 소정근로시간, 주휴일, 연차유급휴가 등이 명시된 "
            "서면을 근로자에게 교부해야 합니다. 근로자가 요구하지 않아도 "
            "주어야 하는 의무입니다."
        ),
        legal_basis="근로기준법 제17조 (SRC-LSA-17)",
        verifiable=False,
        employer_penalty="위반 시 사업주에게 500만원 이하 벌금",
    ),
)


# ============================================================
# 조회
# ============================================================


def all_entitlements() -> list[dict]:
    """
    전체 목록.

    ⚠️ 프론트엔드가 이걸 받아 화면에서 필터링하면, 서버는 사용자가
       임신했는지 장애가 있는지 **아예 알지 못한다.**
       민감정보를 다루는 가장 안전한 방법은 받지 않는 것이다.
    """
    return [item.to_dict() for item in ENTITLEMENTS]


def for_audiences(audiences: set[Audience]) -> list[dict]:
    """
    해당하는 안내만 고른다. EVERYONE 은 항상 포함한다.

    ⚠️ 이 함수에 넘긴 값은 **저장하지 않는다.** 순수 함수이고
       호출자도 저장해서는 안 된다.
    """
    wanted = {Audience.EVERYONE} | audiences
    return [item.to_dict() for item in ENTITLEMENTS if item.audience in wanted]


def by_code(code: str) -> Entitlement | None:
    for item in ENTITLEMENTS:
        if item.code == code:
            return item
    return None
