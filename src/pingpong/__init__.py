import logging
import os
import sys
import random
import tempfile
import time
import concurrent.futures
from pathlib import Path

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
    domain = creds["email"].split("@")[1]
    account.set_config("mail_server", domain)
    account.set_config("send_server", domain)
    account.configure()
    # print(f"account configured {creds['email']}", file=sys.stderr)
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
    def __init__(self, account, chat, num_pings, window, reportfunc):
        assert window <= num_pings
        self.account = account
        self.chat = chat
        self.num_pings = num_pings
        self.window = window
        self.reportfunc = reportfunc

    def __call__(self):
        ping2start = {}

        def receive_one_pong():
            num = int(get_next_incoming_message_snapshot(self.account).text)
            elapsed = ping2start.pop(num)()
            self.reportfunc(self.account, num, elapsed)

        for seq in range(self.num_pings):
            ping2start[seq] = Elapsed()
            self.chat.send_text(f"{seq}")
            if len(ping2start) == self.window:
                receive_one_pong()

        while ping2start:
            receive_one_pong()


class PongerProcess:
    def __init__(self, account, num_pings):
        self.account = account
        self.num_pings = num_pings

    def __call__(self):
        for i in range(self.num_pings):
            snapshot = get_next_incoming_message_snapshot(self.account)
            snapshot.chat.send_text(snapshot.text)


def run(api, proc, num_pings, window):
    elapsed = Elapsed()

    print(f"making {proc} ping-accounts and {proc} pong-accounts", file=sys.stderr)
    accounts = make_accounts(proc * 2, lambda: create_account(api))
    speed = proc * 2 / elapsed()
    print(
        f"finished, took {elapsed} ({speed:0.02f} accounts per second)", file=sys.stderr
    )

    def reportfunc(account, num, elapsed):
        print(f"{num},{elapsed}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=proc * 2) as executor:
        for i in range(proc):
            ac_ping = accounts[i]
            ac_pong = accounts[i + proc]
            pong_addr = ac_pong.get_config("addr")
            chat = ac_ping.create_contact(pong_addr, "").create_chat()
            ac_ping.desc = f"ping-{i}"
            ac_pong.desc = f"pong-{i}"
            futures = [
                executor.submit(
                    PingerProcess(ac_ping, chat, num_pings, window, reportfunc)
                ),
                executor.submit(PongerProcess(ac_pong, num_pings)),
            ]
        done, pending = concurrent.futures.wait(futures)
        assert not pending
        return [x.result() for x in done]


def run_bot(proc, num_pings, window):
    logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(message)s")
    with tempfile.TemporaryDirectory() as tmpdirname:
        with Rpc(accounts_dir=Path(tmpdirname) / "accounts") as rpc:
            api = DeltaChat(rpc)
            run(api, proc, num_pings, window)
