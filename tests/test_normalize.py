"""Tests for normalize.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from transithear.normalize import normalize, find_train_numbers, match_alias


class TestNormalize:
    def test_english_digit_sequence(self):
        """'one two one two eight' → '12128'"""
        result = normalize("one two one two eight")
        assert "12128" in result

    def test_double_digit(self):
        """'double one two eight' should expand 'double one' → 11"""
        result = normalize("double one two eight")
        # 'double one' → 11, then 'two eight' → 28 → run of 4 ≥ 3 → '1128'
        assert "11" in result

    def test_devanagari_digits(self):
        """Unicode Devanagari digits should map to ASCII."""
        result = normalize("१२१२८")
        assert "12128" in result

    def test_devanagari_word_digits(self):
        """'एक दो एक दो आठ' should collapse to '12128'"""
        result = normalize("एक दो एक दो आठ")
        assert "12128" in result

    def test_to_and_for_not_collapsed_short_run(self):
        """'to' and 'for' in normal sentences should NOT become digits."""
        # These are 2-word "digit-like" tokens — below the ≥3 threshold
        text = "Please proceed to platform 3 for boarding"
        result = normalize(text)
        # 'to' should not be replaced with 2; 'for' should not be replaced with 4
        assert "to" in result or "platform" in result  # sentence intact
        # Specifically, we should not get '2' in place of 'to' in isolation
        tokens = result.split()
        # Find 'platform'; next should be '3', not '24' or similar mangling
        if "platform" in tokens:
            idx = tokens.index("platform")
            if idx + 1 < len(tokens):
                assert tokens[idx + 1] == "3"

    def test_hindi_digits(self):
        """Hindi spoken digits (Roman) should map correctly."""
        result = normalize("ek do ek do aath")
        assert "12128" in result

    def test_lowercase_and_punctuation(self):
        """Should lowercase and strip punctuation."""
        result = normalize("PLATFORM 3, Pune!")
        assert "platform" in result
        assert "3" in result
        assert "," not in result


class TestFindTrainNumbers:
    def test_five_digit(self):
        numbers = find_train_numbers("train 12123 arrives at platform 4")
        assert any(n["number"] == "12123" and not n["malformed"] for n in numbers)

    def test_malformed_four_digit(self):
        numbers = find_train_numbers("train 1212 is running late")
        assert any(n["number"] == "1212" and n["malformed"] for n in numbers)

    def test_no_numbers(self):
        numbers = find_train_numbers("please mind the gap")
        assert numbers == []


class TestMatchAlias:
    def test_exact_name(self):
        entries = [
            {"name": "Pune Junction", "code": "PUNE", "aliases": ["Pune", "Pune Jn"]},
            {"name": "Lonavala", "code": "LNL", "aliases": []},
        ]
        result = match_alias("Pune Junction", entries)
        assert result is not None
        assert result["code"] == "PUNE"

    def test_alias_match(self):
        entries = [
            {"name": "Mumbai CSMT", "code": "CSMT", "aliases": ["CST", "VT"]},
        ]
        result = match_alias("CST", entries)
        assert result is not None
        assert result["code"] == "CSMT"

    def test_no_match_below_threshold(self):
        entries = [{"name": "Pune Junction", "code": "PUNE", "aliases": []}]
        result = match_alias("Delhi", entries)
        assert result is None
