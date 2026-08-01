"""
숫자 검증 테스트.

이 검증이 뚫리면 "판정은 코드가 한다"는 주장이 무너진다.
그래서 통과보다 **차단**을 더 촘촘히 확인한다.
"""

from app.bridge.numbers import allowed_numbers, find_unverified, verify
from app.validation.rules import validate


class TestAllowedNumbers:
    def test_collects_wage_from_calculation(self, terms):
        """계산식의 '시급 10,000원 < 최저임금 10,320원' 에서 둘 다 모은다."""
        allowed = allowed_numbers(validate(terms), terms)
        assert "10000" in allowed
        assert "10320" in allowed

    def test_collects_standard_year(self, terms):
        assert "2026" in allowed_numbers(validate(terms), terms)

    def test_collects_article_number_from_legal_basis(self, terms):
        """'근로기준법 제55조' 의 55 도 정당한 숫자다."""
        allowed = allowed_numbers(validate(terms), terms)
        report = validate(terms)
        for check in report.checks:
            for token in check.legal_basis.replace("제", " ").split():
                digits = "".join(c for c in token if c.isdigit())
                if digits:
                    assert digits in allowed

    def test_collects_contract_values(self, terms):
        """계약 조건의 시각·연락처 숫자도 포함된다."""
        allowed = allowed_numbers(validate(terms), terms)
        assert "09" in allowed or "0900" in allowed


class TestBlocking:
    """환각 차단 — 여기가 이 모듈의 존재 이유다."""

    def test_blocks_fabricated_minimum_wage(self, terms):
        ok, bad = verify(
            "시급이 최저임금 12,500원이랑 차이가 있어서요", validate(terms), terms
        )
        assert not ok
        assert "12,500" in bad

    def test_blocks_fabricated_monthly_pay(self, terms):
        ok, bad = verify("월급이 3,200,000원으로 계산되던데요", validate(terms), terms)
        assert not ok

    def test_blocks_even_one_bad_number_among_good_ones(self, terms):
        """맞는 숫자에 섞여 있어도 잡아야 한다."""
        ok, bad = verify(
            "시급 10,000원이 최저임금 10,320원보다 낮아서 월 250,000원 손해입니다",
            validate(terms),
            terms,
        )
        assert not ok
        assert "250,000" in bad

    def test_comma_variants_are_same_number(self, terms):
        """'10320' 과 '10,320' 은 같은 숫자로 본다."""
        ok, _ = verify("최저임금 10320원", validate(terms), terms)
        assert ok


class TestPassing:
    def test_passes_numbers_from_report(self, terms):
        ok, bad = verify(
            "시급이 최저임금 10,320원이랑 차이가 있어서요", validate(terms), terms
        )
        assert ok, bad

    def test_passes_text_without_digits(self, terms):
        ok, _ = verify("확인 한 번 부탁드려요", validate(terms), terms)
        assert ok

    def test_passes_small_numbers(self, terms):
        """'1~2일' 같은 작은 수는 근거 없이도 통과. 이걸로 임금 위조는 불가능하다."""
        assert find_unverified("2~3일 안에 답 주시면", {"99999"}) == []

    def test_eleven_is_not_trivial(self):
        """경계값 — 10까지만 통과."""
        assert find_unverified("11명", set()) == ["11"]
        assert find_unverified("10명", set()) == []
