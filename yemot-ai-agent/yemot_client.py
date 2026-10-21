"""API הניהול של ימות המשיח (call2all). רץ רק בשרת, הטוקן לא יוצא ממנו."""
import requests

import config

BASE = "https://www.call2all.co.il/ym/api/"


class YemotError(Exception):
    pass


def call(command: str, **params) -> dict:
    r = requests.post(BASE + command, json={"token": config.YEMOT_TOKEN, **params}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("responseStatus") != "OK":
        raise YemotError(f"{command}: {data.get('message') or data.get('responseStatus')}")
    return data


def send_sms(phone: str, message: str) -> dict:
    return call("SendSms", phones=phone, message=message)


def bridge_call(dial_first: str, connect_to: str) -> dict:
    """מחייג ל-dial_first ואחרי מענה מגשר אל connect_to."""
    return call("CreateBridgeCall", Phones=dial_first, BridgePhones=connect_to,
                DialSip=0, DialSipExtension=0, RecordCall=0)
