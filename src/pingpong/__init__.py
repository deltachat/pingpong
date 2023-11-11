import json
import logging
import os
import sys
import random
import tempfile
import time
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


def run(api, window, limit):
    accounts = []
    for _ in range(2):
        creds = get_temp_credentials()
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

        account.set_config("addr", creds["email"])
        account.set_config("mail_pw", creds["password"])
        account.configure()
        account.start_io()
        accounts.append(account)
    logging.info("Configured accounts")

    def process_messages(account) -> bool:
        for message in account.get_fresh_messages_in_arrival_order():
            snapshot = message.get_snapshot()
            received = int(snapshot.text)
            now = time.time()
            print(f"{received},{now - start_time}")
            if received < limit:
                snapshot.chat.send_text(str(received + window))
            else:
                snapshot.chat.send_text("STOP")
            snapshot.message.mark_seen()

            if received >= limit:
                return True
        return False

    def pinger_process(account):
        while True:
            event = account.wait_for_event()
            if event["type"] == EventType.INFO:
                logging.info("%s", event["msg"])
            elif event["type"] == EventType.WARNING:
                logging.warning("%s", event["msg"])
            elif event["type"] == EventType.ERROR:
                logging.error("%s", event["msg"])
            elif event["type"] == EventType.INCOMING_MSG:
                logging.info("Got an incoming message")
                if process_messages(account):
                    return

    def echo_process(account):
        while True:
            event = account.wait_for_event()
            if event["type"] == EventType.INFO:
                logging.info("%s", event["msg"])
            elif event["type"] == EventType.WARNING:
                logging.warning("%s", event["msg"])
            elif event["type"] == EventType.ERROR:
                logging.error("%s", event["msg"])
            elif event["type"] == EventType.INCOMING_MSG:
                logging.info("Got an incoming message")

                for message in account.get_fresh_messages_in_arrival_order():
                    snapshot = message.get_snapshot()
                    received = snapshot.text
                    if received == "STOP":
                        return
                    snapshot.chat.send_text(snapshot.text)
                    snapshot.message.mark_seen()

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
        pinger_ponger_chat.send_text(str(1 + i))
    start_time = time.time()

    pinger.join()
    ponger.join()


def run_bot(window, limit):
    logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(message)s")
    with tempfile.TemporaryDirectory() as tmpdirname:
        with Rpc(accounts_dir=Path(tmpdirname) / "accounts") as rpc:
            api = DeltaChat(rpc)
            run(api, window, limit)
