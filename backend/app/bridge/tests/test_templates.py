"""
템플릿 문구 테스트.

핵심 성질 두 가지:
  1. 생성된 문구는 항상 숫자 검증을 통과한다 (값을 report에서만 꺼내므로)
  2. 문제가 없으면 문구를 만들지 않는다
"""

from app.bridge.numbers import verify
from app.bridge.templates import build_lines, build_message
from app.validation.rules import validate


class TestBuildMessage:
    def test_returns_none_when_no_problem(self, compliant_terms):
        """위반이 없으면 말 꺼낼 일도 없다."""
        assert build_message(validate(compliant_terms)) is None

    def test_includes_actual_wage_numbers(self, terms):
        msg = build_message(validate(terms))
        assert "10,000" in msg
        assert "10,320" in msg

    def test_mentions_missing_weekly_holiday(self, terms):
        assert "주휴일" in build_message(validate(terms))

    def test_has_opening_and_closing(self, terms):
        msg = build_message(validate(terms))
        assert msg.startswith("사장님")
        assert msg.rstrip().endswith("감사합니다.")


class TestNumberSafety:
    """템플릿은 정의상 환각이 불가능해야 한다."""

    def test_generated_message_always_passes_verification(self, terms):
        report = validate(terms)
        ok, bad = verify(build_message(report), report, terms)
        assert ok, f"근거 없는 숫자: {bad}"

    def test_holds_for_compliant_and_violating_cases(self, terms, compliant_terms):
        for t in (terms, compliant_terms):
            report = validate(t)
            msg = build_message(report)
            if msg is None:
                continue
            ok, bad = verify(msg, report, t)
            assert ok, f"근거 없는 숫자: {bad}"


class TestTone:
    """
    고발이 아니라 문의여야 한다.
    관계를 지키면서 확인을 요청하는 것이 이 기능의 목적이다.
    """

    def test_does_not_accuse(self, terms):
        msg = build_message(validate(terms))
        for word in ("위반", "불법", "신고", "고발", "처벌"):
            assert word not in msg

    def test_leaves_room_for_misreading(self, terms):
        """'제가 잘못 본 것일 수도' — 사장님이 방어적으로 나오지 않게 한다."""
        assert "잘못 본" in build_message(validate(terms))


class TestBuildLines:
    def test_one_line_per_problem(self, terms):
        report = validate(terms)
        problems = [
            c for c in report.checks
            if c.status.value in ("VIOLATION", "MISSING")
        ]
        assert len(build_lines(report)) == len(problems)

    def test_no_lines_when_compliant(self, compliant_terms):
        assert build_lines(validate(compliant_terms)) == []
