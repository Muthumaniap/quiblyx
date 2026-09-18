import asyncio
import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError
from packages.contracts.chat import Chat
from packages.providers import mock
from packages.domain.security import issue_secret, digest, encrypt


@given(st.text(max_size=200), st.integers(min_value=1, max_value=4096))
def test_bound_is_conservative(text, maximum):
    body = Chat(messages=[{"role": "user", "content": text}], max_tokens=maximum)
    actual = mock.input_units(body) + len(mock.output(body))*2
    assert 0 <= actual <= mock.bound(body)


def test_unsupported_tools_rejected():
    with pytest.raises(ValidationError):
        Chat(messages=[{"role": "user", "content": "hello"}], tools=[{}])


def test_keys_and_secrets():
    secret, hashed = issue_secret()
    assert digest(secret) == hashed
    assert secret not in hashed
    assert secret not in encrypt(secret)
    assert issue_secret()[0] != secret


def test_partial_stream_is_not_retried():
    async def run():
        seen = []
        body = Chat(messages=[{"role": "user", "content": "hello"}], mock_fault="partial_stream")
        with pytest.raises(TimeoutError):
            async for chunk in mock.chunks(body):
                seen.append(chunk)
        assert "".join(seen) == "Det"
    asyncio.run(run())
