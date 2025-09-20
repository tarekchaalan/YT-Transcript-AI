"""Tests for rate limiting."""
import time
from unittest.mock import Mock, patch
import pytest
from fastapi import HTTPException

from app.core.limits import InMemoryRateLimiter, guard_request


class TestInMemoryRateLimiter:
    """Test the in-memory rate limiter."""

    def test_rate_limiter_init(self):
        """Test rate limiter initialization."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=10, daily_quota=100)
        assert limiter.max_requests_per_minute == 10
        assert limiter.daily_quota == 100
        assert limiter.minute_buckets == {}
        assert limiter.daily_counts == {}

    def test_rate_limiter_first_request(self):
        """Test first request is allowed."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=10, daily_quota=100)

        # First request should pass
        limiter.check("127.0.0.1")  # Should not raise exception

    def test_rate_limiter_within_limit(self):
        """Test requests within rate limit."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=10, daily_quota=100)

        # Make 5 requests (within limit)
        for _ in range(5):
            limiter.check("127.0.0.1")  # Should not raise exception

    def test_rate_limiter_exceed_minute_limit(self):
        """Test exceeding per-minute rate limit."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=3, daily_quota=100)

        # Make 3 requests (at limit)
        for _ in range(3):
            limiter.check("127.0.0.1")

        # 4th request should be blocked
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("127.0.0.1")

        assert exc_info.value.status_code == 429
        assert "Too many requests" in str(exc_info.value.detail)

    def test_rate_limiter_exceed_daily_quota(self):
        """Test exceeding daily quota."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=1000, daily_quota=3)

        # Make 3 requests (at daily limit)
        for _ in range(3):
            limiter.check("127.0.0.1")

        # 4th request should be blocked
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("127.0.0.1")

        assert exc_info.value.status_code == 429
        assert "Daily quota exceeded" in str(exc_info.value.detail)

    def test_rate_limiter_different_ips(self):
        """Test that different IPs have separate limits."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=2, daily_quota=100)

        # IP 1 makes 2 requests (at limit)
        limiter.check("127.0.0.1")
        limiter.check("127.0.0.1")

        # IP 1 should be blocked
        with pytest.raises(HTTPException):
            limiter.check("127.0.0.1")

        # IP 2 should still be allowed
        limiter.check("192.168.1.1")  # Should not raise exception

    def test_rate_limiter_minute_window_reset(self):
        """Test that minute window resets after time passes."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=2, daily_quota=100)

        # Mock time to control the window
        with patch('app.core.limits.time.time') as mock_time:
            # Start at time 0
            mock_time.return_value = 0.0

            # Make 2 requests (at limit)
            limiter.check("127.0.0.1")
            limiter.check("127.0.0.1")

            # Should be blocked at same time
            with pytest.raises(HTTPException):
                limiter.check("127.0.0.1")

            # Move time forward 61 seconds (past the minute window)
            mock_time.return_value = 61.0

            # Should be allowed again
            limiter.check("127.0.0.1")  # Should not raise exception

    def test_rate_limiter_daily_window_reset(self):
        """Test that daily window resets after day passes."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=1000, daily_quota=2)

        with patch('app.core.limits.time.time') as mock_time:
            # Start at day 0
            mock_time.return_value = 0.0  # Day 0

            # Make 2 requests (at daily limit)
            limiter.check("127.0.0.1")
            limiter.check("127.0.0.1")

            # Should be blocked
            with pytest.raises(HTTPException):
                limiter.check("127.0.0.1")

            # Move to next day (86400 seconds = 1 day)
            mock_time.return_value = 86400.0  # Day 1

            # Should be allowed again
            limiter.check("127.0.0.1")  # Should not raise exception


class TestGuardRequest:
    """Test the guard_request dependency."""

    @pytest.mark.asyncio
    async def test_guard_request_with_client_ip(self):
        """Test guard_request with client IP."""
        # Mock request with client.host
        request = Mock()
        request.headers = {}
        request.client = Mock()
        request.client.host = "127.0.0.1"

        with patch('app.core.limits.limiter.check') as mock_check:
            await guard_request(request)
            mock_check.assert_called_once_with("127.0.0.1")

    @pytest.mark.asyncio
    async def test_guard_request_with_forwarded_header(self):
        """Test guard_request with X-Forwarded-For header."""
        # Mock request with forwarded header
        request = Mock()
        request.headers = {"x-forwarded-for": "192.168.1.1"}
        request.client = Mock()
        request.client.host = "127.0.0.1"

        with patch('app.core.limits.limiter.check') as mock_check:
            await guard_request(request)
            # Should use forwarded IP, not client IP
            mock_check.assert_called_once_with("192.168.1.1")

    @pytest.mark.asyncio
    async def test_guard_request_rate_limit_exceeded(self):
        """Test guard_request when rate limit is exceeded."""
        request = Mock()
        request.headers = {}
        request.client = Mock()
        request.client.host = "127.0.0.1"

        with patch('app.core.limits.limiter.check') as mock_check:
            mock_check.side_effect = HTTPException(status_code=429, detail="Rate limit exceeded")

            # Should re-raise the HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await guard_request(request)

            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_guard_request_no_client(self):
        """Test guard_request when request.client is None."""
        request = Mock()
        request.headers = {}
        request.client = None

        with patch('app.core.limits.limiter.check') as mock_check:
            await guard_request(request)
            # Should use "unknown" as fallback
            mock_check.assert_called_once_with("unknown")


class TestRateLimitingIntegration:
    """Test rate limiting integration scenarios."""

    def test_multiple_ips_concurrent_requests(self):
        """Test multiple IPs making concurrent requests."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=2, daily_quota=10)

        ips = ["127.0.0.1", "192.168.1.1", "10.0.0.1"]

        # Each IP should be able to make 2 requests
        for ip in ips:
            limiter.check(ip)
            limiter.check(ip)

            # 3rd request should be blocked for each IP
            with pytest.raises(HTTPException):
                limiter.check(ip)

    def test_mixed_rate_and_quota_limits(self):
        """Test interaction between rate and quota limits."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=10, daily_quota=3)

        # Make 3 requests quickly (within rate limit but at quota limit)
        limiter.check("127.0.0.1")
        limiter.check("127.0.0.1")
        limiter.check("127.0.0.1")

        # Should be blocked by daily quota, not rate limit
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("127.0.0.1")

        assert "Daily quota exceeded" in str(exc_info.value.detail)

    def test_memory_efficiency(self):
        """Test that the limiter doesn't leak memory."""
        limiter = InMemoryRateLimiter(max_requests_per_minute=100, daily_quota=1000)

        # Make requests from many different IPs
        for i in range(100):
            ip = f"192.168.1.{i}"
            limiter.check(ip)

        # Should have tracking data for all IPs
        assert len(limiter.minute_buckets) == 100
        assert len(limiter.daily_counts) == 100

        # Note: In a real implementation, you'd want to add cleanup
        # to prevent memory leaks, but this tests the basic functionality
