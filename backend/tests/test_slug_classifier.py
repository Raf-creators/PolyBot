"""
Tests for Crypto Sniper Slug-based Classification
Tests the new slug patterns: btc-updown-5m, bitcoin-up-or-down, bitcoin-above-{price}, will-bitcoin-hit-{price}
Also tests strike parsing with 'k' and 'm' suffixes
"""

import pytest
import os
import sys
from datetime import datetime, timezone, timedelta

# Add backend to path for unit tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.strategies.crypto_sniper import (
    classify_market_question, _parse_strike, _classify_from_slug,
    _SLUG_PATTERNS
)

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestStrikeParser:
    """Test the _parse_strike function for k/m suffix handling"""
    
    def test_parse_strike_plain_number(self):
        """Plain number without suffix"""
        assert _parse_strike("100000") == 100000.0
        print("PASS: Plain number 100000 parsed correctly")
    
    def test_parse_strike_with_comma(self):
        """Number with comma formatting"""
        assert _parse_strike("97,000") == 97000.0
        print("PASS: Number with comma 97,000 parsed correctly")
    
    def test_parse_strike_k_suffix(self):
        """Number with 'k' suffix for thousands"""
        assert _parse_strike("150k") == 150000.0
        assert _parse_strike("150K") == 150000.0  # Case insensitive
        print("PASS: 150k parsed to 150000.0")
    
    def test_parse_strike_m_suffix(self):
        """Number with 'm' suffix for millions"""
        assert _parse_strike("1m") == 1000000.0
        assert _parse_strike("1M") == 1000000.0  # Case insensitive
        print("PASS: 1m parsed to 1000000.0")
    
    def test_parse_strike_decimal_with_k(self):
        """Decimal with 'k' suffix"""
        assert _parse_strike("1.5k") == 1500.0
        print("PASS: 1.5k parsed to 1500.0")
    
    def test_parse_strike_decimal_with_m(self):
        """Decimal with 'm' suffix"""
        assert _parse_strike("2.5m") == 2500000.0
        print("PASS: 2.5m parsed to 2500000.0")


class TestSlugPatterns:
    """Test slug pattern matching"""
    
    def test_updown_slug_pattern(self):
        """btc-updown-5m-{timestamp} pattern"""
        # Create a future timestamp (1 hour from now)
        future_ts = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        slug = f"btc-updown-5m-{future_ts}"
        
        m = _SLUG_PATTERNS[0].search(slug)
        assert m is not None, f"Failed to match slug: {slug}"
        assert m.group("asset") == "btc"
        assert m.group("window") == "5m"
        assert m.group("ts") == str(future_ts)
        print(f"PASS: btc-updown-5m-{future_ts} pattern matched")
    
    def test_bitcoin_up_or_down_slug_pattern(self):
        """bitcoin-up-or-down-{date} pattern"""
        slug = "bitcoin-up-or-down-march-17-2026-12pm-et"
        m = _SLUG_PATTERNS[1].search(slug)
        assert m is not None, f"Failed to match slug: {slug}"
        assert m.group("asset").lower() == "bitcoin"
        print("PASS: bitcoin-up-or-down pattern matched")
    
    def test_bitcoin_above_price_slug_pattern(self):
        """bitcoin-above-{price}-on-{date} pattern"""
        slug = "ethereum-above-2400-on-march-16"
        m = _SLUG_PATTERNS[2].search(slug)
        assert m is not None, f"Failed to match slug: {slug}"
        assert m.group("asset").lower() == "ethereum"
        assert m.group("strike") == "2400"
        print("PASS: ethereum-above-2400-on-march-16 pattern matched")
    
    def test_will_bitcoin_hit_slug_pattern(self):
        """will-bitcoin-hit-{price}-by-{date} pattern"""
        slug = "will-bitcoin-hit-150k-by-march-31-2026"
        m = _SLUG_PATTERNS[3].search(slug)
        assert m is not None, f"Failed to match slug: {slug}"
        assert m.group("asset").lower() == "bitcoin"
        assert m.group("strike") == "150k"
        print("PASS: will-bitcoin-hit-150k-by-march-31-2026 pattern matched")
    
    def test_will_bitcoin_hit_1m_slug_pattern(self):
        """will-bitcoin-hit-1m-before... pattern"""
        slug = "will-bitcoin-hit-1m-by-end-of-2026"
        m = _SLUG_PATTERNS[3].search(slug)
        assert m is not None, f"Failed to match slug: {slug}"
        assert m.group("asset").lower() == "bitcoin"
        assert m.group("strike") == "1m"
        print("PASS: will-bitcoin-hit-1m-by-end-of-2026 pattern matched")


class TestSlugClassification:
    """Test full classify_market_question with slug input"""
    
    def test_classify_updown_slug(self):
        """Classify btc-updown-5m slug - should return market_type='updown'"""
        future_ts = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        slug = f"btc-updown-5m-{future_ts}"
        question = "Will BTC be up or down in 5 minutes?"
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_updown",
            yes_token_id="yes_updown",
            no_token_id="no_updown",
            slug=slug,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.market_type == "updown"
        assert result.direction == "above"  # updown → YES=Up → direction=above
        assert result.strike == 0  # sentinel for updown
        assert result.window == "5m"
        print(f"PASS: updown slug classified - asset={result.asset}, market_type={result.market_type}, window={result.window}")
    
    def test_classify_bitcoin_up_or_down_slug(self):
        """Classify bitcoin-up-or-down-{date} slug"""
        slug = "bitcoin-up-or-down-march-17-2026-12pm-et"
        question = "Bitcoin Up or Down - March 17, 12PM ET"
        # Need end_date for this pattern since slug doesn't contain timestamp
        end_date = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_updown2",
            yes_token_id="yes_updown2",
            no_token_id="no_updown2",
            slug=slug,
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.market_type == "updown"
        print(f"PASS: bitcoin-up-or-down slug classified - asset={result.asset}")
    
    def test_classify_bitcoin_above_price_slug(self):
        """Classify bitcoin-above-{price} slug with end_date"""
        slug = "ethereum-above-2400-on-march-16"
        question = "Will the price of Ethereum be above $2,400 on March 16?"
        end_date = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_above",
            yes_token_id="yes_above",
            no_token_id="no_above",
            slug=slug,
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "ETH"
        assert result.direction == "above"
        assert result.strike == 2400.0
        assert result.market_type == "threshold"
        print(f"PASS: ethereum-above-2400 slug classified - strike={result.strike}")
    
    def test_classify_will_bitcoin_hit_slug(self):
        """Classify will-bitcoin-hit-{price} slug"""
        slug = "will-bitcoin-hit-150k-by-march-31-2026"
        question = "Will Bitcoin hit $150k by March 31, 2026?"
        end_date = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_hit",
            yes_token_id="yes_hit",
            no_token_id="no_hit",
            slug=slug,
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.direction == "above"
        assert result.strike == 150000.0  # 150k → 150000
        assert result.market_type == "threshold"
        print(f"PASS: will-bitcoin-hit-150k slug classified - strike={result.strike}")
    
    def test_classify_will_bitcoin_hit_1m_slug(self):
        """Classify will-bitcoin-hit-1m slug (millions suffix)"""
        slug = "will-bitcoin-hit-1m-by-july-31-2026"
        question = "Will Bitcoin hit $1M before August?"
        end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_1m",
            yes_token_id="yes_1m",
            no_token_id="no_1m",
            slug=slug,
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.strike == 1000000.0  # 1m → 1000000
        print(f"PASS: will-bitcoin-hit-1m slug classified - strike={result.strike}")


class TestQuestionFallbackClassification:
    """Test question-based classification when slug doesn't match"""
    
    def test_question_fallback_hit(self):
        """'hit' keyword in question should work for direction=above"""
        question = "Will Bitcoin hit $150,000 by December 2026?"
        end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_q1",
            yes_token_id="yes_q1",
            no_token_id="no_q1",
            slug="",  # No slug, force question parsing
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.direction == "above"  # 'hit' maps to above
        assert result.strike == 150000.0
        print(f"PASS: 'hit' keyword classified - direction={result.direction}")
    
    def test_question_fallback_reach(self):
        """'reach' keyword in question should work for direction=above"""
        question = "Will Ethereum reach $5,000 by end of year?"
        end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_q2",
            yes_token_id="yes_q2",
            no_token_id="no_q2",
            slug="",
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "ETH"
        assert result.direction == "above"  # 'reach' maps to above
        assert result.strike == 5000.0
        print(f"PASS: 'reach' keyword classified - direction={result.direction}")
    
    def test_question_fallback_dip(self):
        """'dip' keyword in question should work for direction=below"""
        question = "Will Bitcoin dip to $60,000 by next week?"
        end_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_q3",
            yes_token_id="yes_q3",
            no_token_id="no_q3",
            slug="",
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.direction == "below"  # 'dip' maps to below
        assert result.strike == 60000.0
        print(f"PASS: 'dip' keyword classified - direction={result.direction}")
    
    def test_question_fallback_between_range(self):
        """'between X and Y' pattern for range markets"""
        question = "Will the price of Bitcoin be between $70,000 and $72,000 on March 16?"
        end_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_range",
            yes_token_id="yes_range",
            no_token_id="no_range",
            slug="",
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.market_type == "range"
        # Strike should be midpoint: (70000 + 72000) / 2 = 71000
        assert result.strike == 71000.0
        print(f"PASS: 'between X and Y' classified - strike={result.strike}, market_type={result.market_type}")
    
    def test_question_fallback_bitcoin_up_or_down(self):
        """'Up or Down' pattern for updown markets"""
        question = "Bitcoin Up or Down - March 17, 12PM ET"
        end_date = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_updown3",
            yes_token_id="yes_updown3",
            no_token_id="no_updown3",
            slug="",  # No slug
            end_date=end_date,
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.market_type == "updown"
        assert result.strike == 0  # updown has strike=0
        print(f"PASS: 'Up or Down' pattern classified - market_type={result.market_type}")


class TestBackwardCompatibility:
    """Test backward compatibility with question-only parsing (slug='')"""
    
    def test_question_only_btc_above(self):
        """Original question parsing still works when slug is empty"""
        question = "Will BTC be above $97,000 at 12:15 UTC?"
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_compat1",
            yes_token_id="yes_compat1",
            no_token_id="no_compat1",
            slug="",  # Empty slug → fall back to question parsing
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.direction == "above"
        assert result.strike == 97000.0
        print(f"PASS: Backward compat - question-only parsing works")
    
    def test_question_only_eth_below(self):
        """ETH below question parsing still works"""
        question = "Will ETH be below $3,500 at 14:30 UTC?"
        
        result, reason = classify_market_question(
            question=question,
            condition_id="cid_compat2",
            yes_token_id="yes_compat2",
            no_token_id="no_compat2",
            slug="",
        )
        
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "ETH"
        assert result.direction == "below"
        assert result.strike == 3500.0
        print(f"PASS: Backward compat - ETH below question parsing works")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
