"""The CFBD production fetcher and its credential (SPEC-phase0 5.5).

The seam is the same one used everywhere else, one level further down:
``CfbdClient`` takes a ``fetch`` callable, and this is the callable it takes in
production. That callable in turn takes a ``get_secret`` callable, so the key
*source* is swappable without the request-building code knowing where a key comes
from. Every test below hands it a lambda returning a fake key; no AWS, no network.

**What is not covered here, and cannot be.** ``ssm_secret`` makes one boto3 call
to read a SecureString. Nothing offline can verify that the parameter exists, is
encrypted, is readable by the publisher role, or comes back decrypted -- those are
facts about an AWS account, not about this code. The seam exists precisely so the
*rest* of the path is testable, and the untested part is one function whose whole
body is the call.

**The scheme does not carry over from Sagarin, and that is the point.**
``fetch_page`` pins Sagarin to plain HTTP because the site 302s HTTPS down to
HTTP and a client that upgrades loops forever. Carrying that rule across would
put a bearer token on the wire in the clear. CFBD is a normal JSON API over TLS,
so this fetcher pins the other way -- and refuses to send at all if the scheme is
ever anything but https, because "the request failed" is a recoverable Sunday and
"the key was transmitted in plaintext" is a key that has to be rotated.

**The key must not appear anywhere a human or a log reader can see it.** SPEC 5.3
requires the status and body of every non-2xx to be logged, which means the
logging path runs on exactly the requests most likely to be pasted into an issue.
Those tests drive a real ``CfbdClient`` over this fetcher so the composition is
what gets checked, not the fetcher alone.
"""

import httpx
import pytest

from cfb.collectors.cfbd import BASE_URL, SSM_PARAMETER, CfbdClient, http_fetch
from cfb.errors import FetchError

#: Distinctive enough to grep for, and shaped like the real thing.
KEY = "cfbd-secret-key-do-not-log-me-0123456789"


def recorder(handler=None):
    """``(transport, requests)`` over a handler, recording what was sent."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request) if handler else httpx.Response(200, content=b"[]")

    return httpx.MockTransport(respond), requests


def fetcher(*, key: str = KEY, handler=None, calls: list | None = None):
    """The production fetcher with its credential source swapped for a lambda."""
    transport, requests = recorder(handler)

    def get_secret() -> str:
        if calls is not None:
            calls.append("read")
        return key

    return http_fetch(get_secret=get_secret, transport=transport), requests


class TestTheBearerHeader:
    def test_the_header_is_bearer_space_key(self):
        """The space after ``Bearer`` is load-bearing.

        The vendor calls it out as the usual cause of a 401 that looks like a bad
        key -- the failure sends you to regenerate a credential that was fine.
        """
        fetch, requests = fetcher()

        fetch("/games", {"year": 2026})

        assert requests[0].headers["authorization"] == f"Bearer {KEY}"

    def test_every_request_carries_it(self):
        """SPEC 5.5: on every protected operation, which is all of them."""
        fetch, requests = fetcher()

        fetch("/games", {"year": 2026, "week": 4})
        fetch("/teams/fbs", {"year": 2026})

        assert [r.headers["authorization"] for r in requests] == [f"Bearer {KEY}"] * 2

    def test_whatever_get_secret_returns_is_what_is_sent(self):
        """The fetcher does not know or care where a key comes from."""
        fetch, requests = fetcher(key="a-completely-different-key")

        fetch("/calendar", {"year": 2026})

        assert requests[0].headers["authorization"] == "Bearer a-completely-different-key"

    def test_surrounding_whitespace_is_stripped(self):
        """A SecureString set with `--value "$(cat key.txt)"` keeps the newline.

        That produces ``Bearer abc\\n``, which is a malformed header and a 401
        that reads as a bad key -- the exact trap the vendor documents, arriving
        by a route nobody suspects.
        """
        fetch, requests = fetcher(key=f"  {KEY}\n")

        fetch("/games", {"year": 2026})

        assert requests[0].headers["authorization"] == f"Bearer {KEY}"

    @pytest.mark.parametrize("blank", ["", "   ", "\n"])
    def test_a_blank_key_raises_instead_of_sending_bearer_nothing(self, blank):
        """``Bearer `` is a request that spends quota to earn a 401.

        Worse, it is a 401 indistinguishable from a revoked key, so it sends
        whoever reads the run to rotate a credential when the real problem is an
        empty SSM parameter.
        """
        fetch, requests = fetcher(key=blank)

        with pytest.raises(FetchError):
            fetch("/games", {"year": 2026})

        assert requests == [], "nothing should have been sent"

    def test_the_key_is_never_a_query_parameter(self):
        """Query strings end up in access logs, proxies and browser history."""
        fetch, requests = fetcher()

        fetch("/games", {"year": 2026, "week": 4})

        query = str(requests[0].url.query)
        assert KEY not in query
        assert "year=2026" in query and "week=4" in query


class TestTheSchemeIsHttpsAndStaysThere:
    """The inverse of ``fetch_page``'s pin, for the opposite reason."""

    def test_requests_go_to_the_https_base_url(self):
        fetch, requests = fetcher()

        fetch("/games", {"year": 2026})

        assert requests[0].url.scheme == "https"
        assert str(requests[0].url).startswith(f"{BASE_URL}/games")

    def test_the_base_url_is_https(self):
        assert BASE_URL.startswith("https://")

    def test_a_non_https_base_url_refuses_to_send(self, monkeypatch):
        """A failed Sunday is recoverable. A leaked key is a rotation.

        This is the guard against a well-meaning edit that copies Sagarin's HTTP
        pin across, or a proxy setting that downgrades the base URL.
        """
        monkeypatch.setattr(
            "cfb.collectors.cfbd.BASE_URL", "http://api.collegefootballdata.com"
        )
        fetch, requests = fetcher()

        with pytest.raises(FetchError) as excinfo:
            fetch("/games", {"year": 2026})

        assert requests == [], "the token must not reach the wire over http"
        assert "https" in str(excinfo.value)

    def test_a_redirect_is_returned_rather_than_followed(self):
        """Following a 3xx could hand the Authorization header to another host.

        The client classifies it -- a 3xx is not in the retryable whitelist -- so
        the fetcher's job is only to not chase it.
        """
        def handler(request):
            return httpx.Response(302, headers={"Location": "http://evil.example/games"})

        fetch, requests = fetcher(handler=handler)

        response = fetch("/games", {"year": 2026})

        assert response.status_code == 302
        assert len(requests) == 1


class TestTheKeyNeverLeaks:
    """Driven through a real ``CfbdClient``, because the logging lives there.

    SPEC 5.3 logs the status and body of every non-2xx without exception, so the
    logging path runs on precisely the requests someone is most likely to paste
    into an issue.
    """

    def test_not_in_the_log_of_a_successful_call(self, capsys):
        fetch, _ = fetcher()
        CfbdClient(fetch=fetch).get("/games", year=2026)

        captured = capsys.readouterr()
        assert KEY not in captured.out
        assert KEY not in captured.err

    def test_not_in_the_log_of_a_non_2xx(self, capsys):
        def handler(request):
            return httpx.Response(401, content=b'{"message":"unauthorized"}')

        fetch, _ = fetcher(handler=handler)
        with pytest.raises(FetchError):
            CfbdClient(fetch=fetch).get("/games", year=2026)

        captured = capsys.readouterr()
        assert KEY not in captured.out
        assert KEY not in captured.err

    def test_not_in_a_response_body_that_echoes_it(self, capsys):
        """A vendor that echoed the header would otherwise put it in our log.

        SPEC 5.3 wants the body kept because it is the only evidence of what an
        over-quota response looks like. Keeping it must not mean keeping a
        credential.
        """
        def handler(request):
            return httpx.Response(400, content=f'{{"sent":"Bearer {KEY}"}}'.encode())

        fetch, _ = fetcher(handler=handler)
        with pytest.raises(FetchError):
            CfbdClient(fetch=fetch).get("/games", year=2026)

        assert KEY not in capsys.readouterr().out

    def test_not_in_the_exception_from_a_failed_request(self):
        def handler(request):
            raise httpx.ConnectError("connection refused", request=request)

        fetch, _ = fetcher(handler=handler)
        with pytest.raises(FetchError) as excinfo:
            CfbdClient(fetch=fetch, sleep=lambda _: None).get("/games", year=2026)

        assert KEY not in str(excinfo.value)

    def test_not_in_the_repr_of_anything_a_debugger_shows(self):
        fetch, _ = fetcher()
        client = CfbdClient(fetch=fetch)

        assert KEY not in repr(client)
        assert KEY not in repr(fetch)


class TestReadingTheSecret:
    def test_building_the_fetcher_reads_nothing(self):
        """Constructing must not touch AWS.

        The CLI builds a fetcher while parsing arguments; a read at construction
        would mean `--help` needed credentials.
        """
        calls: list[str] = []
        fetcher(calls=calls)

        assert calls == []

    def test_the_secret_is_read_once_and_reused(self):
        """A run makes up to 25 requests (SPEC 5.1) and needs one credential."""
        calls: list[str] = []
        fetch, _ = fetcher(calls=calls)

        fetch("/games", {"year": 2026})
        fetch("/lines", {"year": 2026})
        fetch("/teams/fbs", {"year": 2026})

        assert calls == ["read"]

    def test_the_parameter_name_is_the_one_spec_5_5_pins(self):
        """Not a guess and not configurable: SPEC 5.5 names this exact path, and
        the publisher IAM policy is scoped to the prefix it sits under.
        """
        assert SSM_PARAMETER == "/travispollard/cfb/cfbd_api_key"
