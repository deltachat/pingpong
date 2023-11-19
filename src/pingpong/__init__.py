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
    accounts = make_accounts(window, lambda: create_account(api))
    print(f"make accounts {elapsed()} finished")
    logging.info("Configured accounts")

    ping_start_times = {}

    def send_ping(chat, num):
        ping_start_times[num] = time.time()
        chat.send_text(f"{num}")

    def pinger_process(account):
        while True:
            event = account.wait_for_event()
            if event["kind"] == EventType.INFO:
                logging.info("%s", event["msg"])
            elif event["kind"] == EventType.WARNING:
                logging.warning("%s", event["msg"])
            elif event["kind"] == EventType.ERROR:
                logging.error("%s", event["msg"])
            elif event["kind"] == EventType.INCOMING_MSG:
                logging.info("Got an incoming message")

                message = account.get_message_by_id(event["msg_id"])
                snapshot = message.get_snapshot()
                received = int(snapshot.text)
                now = time.time()
                print(f"{received},{now - ping_start_times[received]}")
                if received < limit:
                    send_ping(snapshot.chat, received + window)
                else:
                    snapshot.chat.send_text("STOP")
                snapshot.message.mark_seen()

                if received >= limit:
                    return True

    def echo_process(account):
        while True:
            event = account.wait_for_event()
            if event["kind"] == EventType.INFO:
                logging.info("%s", event["msg"])
            elif event["kind"] == EventType.WARNING:
                logging.warning("%s", event["msg"])
            elif event["kind"] == EventType.ERROR:
                logging.error("%s", event["msg"])
            elif event["kind"] == EventType.INCOMING_MSG:
                logging.info("Got an incoming message")

                message = account.get_message_by_id(event["msg_id"])
                snapshot = message.get_snapshot()
                received = snapshot.text
                if received == "STOP":
                    return
                snapshot.chat.send_text(snapshot.text)

    ponger_addr = accounts[1].get_config("addr")
    pinger_ponger_contact = accounts[0].create_contact(ponger_addr, "")
    pinger_ponger_chat = pinger_ponger_contact.create_chat()

    logging.info("Creating tasks")
    ponger = Thread(target=echo_process, args=(accounts[1],))
    pinger = Thread(target=pinger_process, args=(accounts[0],))
    pinger.start()
    ponger.start()

    logging.info("Sending text")
    for i in range(window):
        send_ping(pinger_ponger_chat, i + 1)

    pinger.join()
    ponger.join()


def run_bot(window, limit):
    logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(message)s")
    with tempfile.TemporaryDirectory() as tmpdirname:
        with Rpc(accounts_dir=Path(tmpdirname) / "accounts") as rpc:
            api = DeltaChat(rpc)
            run(api, window, limit)
