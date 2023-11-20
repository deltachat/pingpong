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


class Elapsed:
    def __init__(self):
        self.start = time.time()

    def __call__(self):
        return time.time() - self.start

    def __str__(self):
        return f"{self():0.2f}s"


def get_next_incoming_message_snapshot(account):
    while True:
        event = account.wait_for_event()
        if event["kind"] == EventType.INFO:
            logging.info(f"{account.desc} {event['msg']}")
        elif event["kind"] == EventType.WARNING:
            logging.warning(f"{account.desc} {event['msg']}")
        elif event["kind"] == EventType.ERROR:
            logging.error(f"{account.desc} {event['msg']}")
        elif event["kind"] == EventType.INCOMING_MSG:
            message = account.get_message_by_id(event["msg_id"])
            return message.get_snapshot()


class PingerProcess:
    def __init__(self, account, chat, num_pings):
        self.account = account
        self.chat = chat
        self.num_pings = num_pings

    def __call__(self):
        for seq in range(self.num_pings):
            elapsed = Elapsed()
            self.chat.send_text(f"{seq}")
            num = int(get_next_incoming_message_snapshot(self.account).text)
            assert num == seq
            print(f"{num},{elapsed()}")


class PongerProcess:
    def __init__(self, account, num_pings):
        self.account = account
        self.num_pings = num_pings

    def __call__(self):
        for i in range(self.num_pings):
            snapshot = get_next_incoming_message_snapshot(self.account)
            snapshot.chat.send_text(snapshot.text)


def run(api, proc, num_pings):
    elapsed = Elapsed()

    print(f"make accounts {elapsed} started")
    accounts = make_accounts(proc * 2, lambda: create_account(api))
    print(f"make accounts finished, took {elapsed}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=proc * 2) as executor:
        for i in range(proc):
            ac_ping = accounts[i]
            ac_pong = accounts[i + proc]
            pong_addr = ac_pong.get_config("addr")
            chat = ac_ping.create_contact(pong_addr, "").create_chat()
            ac_ping.desc = f"ping-{i}"
            ac_pong.desc = f"pong-{i}"
            futures = [
                executor.submit(PingerProcess(ac_ping, chat, num_pings)),
                executor.submit(PongerProcess(ac_pong, num_pings)),
            ]
        done, pending = concurrent.futures.wait(futures)
        assert not pending
        return [x.result() for x in done]


def run_bot(proc, num_pings):
    logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(message)s")
    with tempfile.TemporaryDirectory() as tmpdirname:
        with Rpc(accounts_dir=Path(tmpdirname) / "accounts") as rpc:
            api = DeltaChat(rpc)
            run(api, proc, num_pings)
