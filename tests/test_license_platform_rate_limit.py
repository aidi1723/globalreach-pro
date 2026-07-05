import json
import subprocess
import sys
from pathlib import Path


def test_in_memory_rate_limiter_blocks_after_threshold():
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"

    code = """
import json
import sys

sys.path.insert(0, sys.argv[1])

from app.rate_limit import InMemoryRateLimiter

limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
first = limiter.allow("activate:127.0.0.1", now=100.0)
second = limiter.allow("activate:127.0.0.1", now=101.0)
third = limiter.allow("activate:127.0.0.1", now=102.0)
fourth = limiter.allow("activate:127.0.0.1", now=161.0)

print(json.dumps(
    {
        "first": first,
        "second": second,
        "third": third,
        "fourth": fourth,
    }
))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout.strip())
    assert payload["first"] == [True, 0]
    assert payload["second"] == [True, 0]
    assert payload["third"][0] is False
    assert payload["third"][1] > 0
    assert payload["fourth"] == [True, 0]


def test_extract_client_ip_only_trusts_forwarded_header_from_configured_proxy():
    project_root = Path(__file__).resolve().parents[1]
    api_root = project_root / "license-platform" / "apps" / "api"

    code = """
import json
import sys

sys.path.insert(0, sys.argv[1])

from starlette.requests import Request

from app.config import settings
from app.rate_limit import extract_client_ip

original_trust_proxy_headers = settings.trust_proxy_headers
original_trusted_proxy_ips_raw = settings.trusted_proxy_ips_raw

try:
    spoofed_request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/licenses/activate",
            "raw_path": b"/licenses/activate",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"8.8.8.8")],
            "client": ("198.51.100.10", 12345),
            "server": ("testserver", 80),
        }
    )

    settings.trust_proxy_headers = False
    settings.trusted_proxy_ips_raw = "127.0.0.1"
    direct_only = extract_client_ip(spoofed_request)

    settings.trust_proxy_headers = True
    settings.trusted_proxy_ips_raw = "127.0.0.1"
    untrusted_proxy = extract_client_ip(spoofed_request)

    trusted_proxy_request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/licenses/activate",
            "raw_path": b"/licenses/activate",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"8.8.4.4, 127.0.0.1")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    trusted_proxy = extract_client_ip(trusted_proxy_request)
finally:
    settings.trust_proxy_headers = original_trust_proxy_headers
    settings.trusted_proxy_ips_raw = original_trusted_proxy_ips_raw

print(json.dumps(
    {
        "direct_only": direct_only,
        "untrusted_proxy": untrusted_proxy,
        "trusted_proxy": trusted_proxy,
    }
))
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(api_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout.strip())
    assert payload["direct_only"] == "198.51.100.10"
    assert payload["untrusted_proxy"] == "198.51.100.10"
    assert payload["trusted_proxy"] == "8.8.4.4"
