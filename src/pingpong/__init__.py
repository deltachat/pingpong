import json
import logging
import os
import sys
import random
import tempfile
import time
import concurrent.futures
from pathlib import Path
from threading import Thread

from deltachat_rpc_client import DeltaChat, EventType, Rpc


def get_temp_credentials() -> dict:
    domain = os.getenv("CHATMAIL_DOMAIN")
    username = "ci-" + "".join(
        random.choice("2345789acdefghjkmnpqrstuvwxyz") for i in range(6)
    )
    password = f"{username}${username}"
    addr = f"{username}@{domain}"
    return {"email": addr, "password": password}


def make_accounts(num, account_maker):
    """Test that long-running task does not block short-running task from completion."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=num) as executor:
        futures = [executor.submit(account_maker) for i in range(num)]
        done, pending = concurrent.futures.wait(futures)
        return [x.result() for x in done]


def create_account(api):
    account = api.add_account()

    account.set_config("bot", "1")
    account.set_config("bcc_self", "0")
    account.set_config("mvbox_move", "0")
    account.set_config("mdns_enabled", "0")
    account.set_config("e2ee_enabled", "0")

    account.set_config("mail_port", "993")
    account.set_config("send_port", "465")

    account.set_config("socks5_enabled", "0")
    account.set_config("socks5_host", "127.0.0.1")
    account.set_config("socks5_port", "9050")

    assert not account.is_configured()

    creds = get_temp_credentials()
    account.set_config("addr", creds["email"])
    account.set_config("mail_pw", creds["password"])
    account.configure()
    account.start_io()
    return account


def run(api, window, limit):
    now = time.time()
    def elapsed():
        el = time.time() - now
        return f"{el:0.2f}"

    print(f"make accounts {elapsed()} started")
    accounts = make_accounts(window * 2, lambda: create_account(api))
    print(f"make accounts {elapsed()} finished")

    ping_start_times = {}

    def send_ping(chat, num):
        ping_start_times[num] = time.time()
        chat.send_text(f"{num}")
        # print(f"ping seq={num}")

    def pinger_process(account, chat, num):
        while True:
            send_ping(chat, num)

            while True:
                event = account.wait_for_event()
                if event["kind"] == EventType.INFO:
                    logging.info(f"{account.desc} {event['msg']}")
                elif event["kind"] == EventType.WARNING:
                    logging.warning(f"{account.desc} {event['msg']}")
                elif event["kind"] == EventType.ERROR:
                    logging.error(f"{account.desc} {event['msg']}")
                elif event["kind"] == EventType.INCOMING_MSG:
                    logging.info("Got an incoming message")
                    now = time.time()
                    message = account.get_message_by_id(event["msg_id"])
                    snapshot = message.get_snapshot()
                    assert int(snapshot.text) == num
                    print(f"{num},{now - ping_start_times[num]}")
                    num += window
                    if num >= limit:
                        snapshot.chat.send_text("STOP")
                        return True
                    snapshot.message.mark_seen()
                    break

    def ponger_process(account):
        while True:
            event = account.wait_for_event()
            if event["kind"] == EventType.INFO:
                logging.info(f"{account.desc} {event['msg']}")
            elif event["kind"] == EventType.WARNING:
                logging.warning(f"{account.desc} {event['msg']}")
            elif event["kind"] == EventType.ERROR:
                logging.error(f"{account.desc} {event['msg']}")
            elif event["kind"] == EventType.INCOMING_MSG:
                logging.info("Got an incoming message")
                message = account.get_message_by_id(event["msg_id"])
                snapshot = message.get_snapshot()
                received = snapshot.text
                if received == "STOP":
                    return
                snapshot.chat.send_text(snapshot.text)

    with concurrent.futures.ThreadPoolExecutor(max_workers=window*2) as executor:
        for i in range(window):
            ac_ping = accounts[i]
            ac_pong = accounts[i + window]
            pong_addr = ac_pong.get_config("addr")
            chat = ac_ping.create_contact(pong_addr, "").create_chat()
            ac_ping.desc = f"ping-{i}"
            ac_pong.desc = f"pong-{i}"
            futures = [executor.submit(lambda: pinger_process(ac_ping, chat, i))]
            futures.append(executor.submit(lambda: ponger_process(ac_pong)))
        done, pending = concurrent.futures.wait(futures)
        assert not pending
        return [x.result() for x in done]


def run_bot(window, limit):
    logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(message)s")
    with tempfile.TemporaryDirectory() as tmpdirname:
        with Rpc(accounts_dir=Path(tmpdirname) / "accounts") as rpc:
            api = DeltaChat(rpc)
            run(api, window, limit)
