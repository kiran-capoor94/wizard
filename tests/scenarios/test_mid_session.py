import asyncio

from wizard.mid_session import cancel_mid_session_synthesis, register_mid_session_task


async def test_cancel_nonexistent_is_safe():
    cancel_mid_session_synthesis("no-such-id")


async def test_register_and_cancel():
    task = asyncio.create_task(asyncio.sleep(999))
    await register_mid_session_task("test-session", task)
    cancel_mid_session_synthesis("test-session")
    await asyncio.sleep(0)
    assert task.cancelled() or task.done()


async def test_double_cancel_is_safe():
    task = asyncio.create_task(asyncio.sleep(999))
    await register_mid_session_task("session-x", task)
    cancel_mid_session_synthesis("session-x")
    cancel_mid_session_synthesis("session-x")
