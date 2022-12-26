import json
import logging
import asyncio
import aiohttp
import sys
import tempfile
import os
import time
from pathlib import Path

from deltachat_rpc_client import DeltaChat, EventType, Rpc


async def get_temp_credentials() -> dict:
    url = os.getenv("DCC_NEW_TMP_EMAIL")
    assert url, "Failed to get online account, DCC_NEW_TMP_EMAIL is not set"
    async with aiohttp.ClientSession() as session:
        async with session.post(url) as response:
            return json.loads(await response.text())


async def run(api, window, limit):
    accounts = []
    for _ in range(2):
        creds = await get_temp_credentials()
        account = await api.add_account()

        await account.set_config("bot", "1")
        await account.set_config("bcc_self", "0")
        await account.set_config("mvbox_move", "0")
        await account.set_config("mdns_enabled", "0")
        await account.set_config("e2ee_enabled", "0")

        await account.set_config("mail_port", "993")
        await account.set_config("send_port", "465")

        await account.set_config("socks5_enabled", "0")
        await account.set_config("socks5_host", "127.0.0.1")
        await account.set_config("socks5_port", "9050")

        assert not await account.is_configured()

        await account.set_config("addr", creds["email"])
        await account.set_config("mail_pw", creds["password"])
        await account.configure()
        await account.start_io()
        accounts.append(account)
    logging.info("Configured accounts")

    async def process_messages(account) -> bool:
        for message in await account.get_fresh_messages_in_arrival_order():
            snapshot = await message.get_snapshot()
            received = int(snapshot.text)
            now = time.time()
            print(f"{received},{now - start_time}")
            if received < limit:
                await snapshot.chat.send_text(str(received + window))
            else:
                await snapshot.chat.send_text("STOP")
            await snapshot.message.mark_seen()

            if received >= limit:
                return True
        return False

    async def pinger_process(account):
        while True:
            event = await account.wait_for_event()
            if event["type"] == EventType.INFO:
                logging.info("%s", event["msg"])
            elif event["type"] == EventType.WARNING:
                logging.warning("%s", event["msg"])
            elif event["type"] == EventType.ERROR:
                logging.error("%s", event["msg"])
            elif event["type"] == EventType.INCOMING_MSG:
                logging.info("Got an incoming message")
                if await process_messages(account):
                    return

    async def echo_process(account):
        while True:
            event = await account.wait_for_event()
            if event["type"] == EventType.INFO:
                logging.info("%s", event["msg"])
            elif event["type"] == EventType.WARNING:
                logging.warning("%s", event["msg"])
            elif event["type"] == EventType.ERROR:
                logging.error("%s", event["msg"])
            elif event["type"] == EventType.INCOMING_MSG:
                logging.info("Got an incoming message")

                for message in await account.get_fresh_messages_in_arrival_order():
                    snapshot = await message.get_snapshot()
                    received = snapshot.text
                    if received == "STOP":
                        return
                    await snapshot.chat.send_text(snapshot.text)
                    await snapshot.message.mark_seen()

    ponger_addr = await accounts[1].get_config("addr")
    pinger_ponger_contact = await accounts[0].create_contact(ponger_addr, "")
    pinger_ponger_chat = await pinger_ponger_contact.create_chat()

    logging.info("Creating tasks")
    ponger = asyncio.create_task(echo_process(accounts[1]))
    pinger = asyncio.create_task(pinger_process(accounts[0]))

    logging.info("Sending text")
    for i in range(window):
        await pinger_ponger_chat.send_text(str(1 + i))
    start_time = time.time()

    await pinger
    await ponger


async def run_bot(window, limit):
    logging.basicConfig(level=logging.ERROR)
    with tempfile.TemporaryDirectory() as tmpdirname:
        async with Rpc(accounts_dir=Path(tmpdirname) / "accounts") as rpc:
            api = DeltaChat(rpc)
            await run(api, window, limit)
