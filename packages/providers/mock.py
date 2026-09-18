"""Deterministic, zero-paid-call adapter. Units and prices are synthetic."""
import asyncio


def input_units(chat):
    return sum(len(m.content.encode("utf-8")) + 8 for m in chat.messages)


def bound(chat):
    return input_units(chat) + chat.max_tokens * 2


def output(chat):
    return "Deterministic mock response."[:chat.max_tokens]


async def chunks(chat):
    if chat.mock_fault == "timeout":
        raise TimeoutError("mock timeout after dispatch")
    for index, char in enumerate(output(chat)):
        await asyncio.sleep(0.002)
        if chat.mock_fault == "partial_stream" and index == 3:
            raise TimeoutError("mock partial stream")
        yield char
