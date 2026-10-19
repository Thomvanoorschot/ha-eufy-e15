#!/usr/bin/env python3
"""Fetch the device ID and local key of the devices in your Eufy account.

Run through ``tools/get-local-key.sh``. This is the only part of the project that
talks to the cloud, and it does so once: it signs in with your Eufy account, opens
the Tuya session that the Eufy app uses behind the scenes, and lists the devices
with their local keys. Nothing is stored; email and password are asked for
interactively.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import secrets
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Public client parameters of the Eufy app.
EUFY_LOGIN_URL = "https://home-api.eufylife.com/v1/user/email/login"
EUFY_CLIENT_ID = "eufyhome-app"
EUFY_CLIENT_SECRET = "GQCpr9dSp3uQpsOMgJ4xQ"

TUYA_URL = "https://a1.tuyaeu.com"
TUYA_CLIENT_ID = "yx5v9uc3ef9wg3v9atje"
TUYA_APP_SECRET = "s8x78u7xwymasd9kqa7a73pjhxqsedaj"
TUYA_BMP_SECRET = "cepev5pfnhua4dkqkdpmnrdxx378mpjr"
TUYA_SIGN_KEY = f"A_{TUYA_BMP_SECRET}_{TUYA_APP_SECRET}".encode()
# The Tuya account behind an Eufy account has a password derived from its uid.
TUYA_PASSWORD_AES_KEY = bytes.fromhex("244e6d8a56ac879124432d8b6cbca2c4")
TUYA_PASSWORD_AES_IV = bytes.fromhex("772456f2a7664cf3392c3597e93e5747")

SIGNED_PARAMS = frozenset(
    [
        "a",
        "v",
        "lat",
        "lon",
        "lang",
        "deviceId",
        "appVersion",
        "ttid",
        "isH5",
        "h5Token",
        "os",
        "clientId",
        "postData",
        "time",
        "requestId",
        "et",
        "n4h5",
        "sid",
        "sp",
    ]
)
TIMEOUT = 15


class LookupFailed(RuntimeError):
    """A readable failure for the user."""


def _post(url: str, *, json_body: Any = None, form: dict | None = None, headers=None) -> Any:
    if json_body is not None:
        body = json.dumps(json_body).encode()
        content_type = "application/json"
    else:
        body = urllib.parse.urlencode(form or {}).encode()
        content_type = "application/x-www-form-urlencoded"
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": content_type, **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        try:
            return json.load(err)
        except ValueError:
            raise LookupFailed(f"HTTP {err.code} from {url}") from err


def eufy_login(email: str, password: str) -> tuple[str, str]:
    """Return (uid, country code) of the Eufy account."""
    reply = _post(
        EUFY_LOGIN_URL,
        json_body={
            "client_id": EUFY_CLIENT_ID,
            "client_Secret": EUFY_CLIENT_SECRET,
            "email": email,
            "password": password,
        },
        headers={"User-Agent": "EufyHome-Android-2.4.0", "clientType": "2"},
    )
    if not isinstance(reply, dict) or "access_token" not in reply:
        message = reply.get("msg") or reply.get("message") if isinstance(reply, dict) else reply
        raise LookupFailed(f"Eufy login failed: {message}")
    user = reply["user_info"]
    return user["id"], str(user.get("phone_code") or "31")


class TuyaSession:
    def __init__(self) -> None:
        self.url = TUYA_URL
        self.sid: str | None = None
        alphabet = string.ascii_letters + string.digits
        self.device_id = "".join(secrets.choice(alphabet) for _ in range(44))

    @staticmethod
    def _md5_shuffled(text: str) -> str:
        digest = hashlib.md5(text.encode()).hexdigest()
        return digest[8:16] + digest[0:8] + digest[24:32] + digest[16:24]

    def _sign(self, params: dict[str, str]) -> str:
        parts = []
        for key in sorted(k for k in params if k in SIGNED_PARAMS):
            value = params[key]
            if key == "postData":
                value = self._md5_shuffled(value)
            parts.append(f"{key}={value}")
        return hmac.new(TUYA_SIGN_KEY, "||".join(parts).encode(), hashlib.sha256).hexdigest()

    def call(self, action: str, version: str = "1.0", data=None, **query: str) -> Any:
        params = {
            "a": action,
            "v": version,
            "appVersion": "2.4.0",
            "clientId": TUYA_CLIENT_ID,
            "deviceId": self.device_id,
            "et": "0.0.1",
            "lang": "en",
            "os": "Android",
            "osSystem": "12",
            "platform": "sdk_gphone64_arm64",
            "requestId": str(uuid.uuid4()),
            "sdkVersion": "3.0.8cAnker",
            "time": str(int(time.time())),
            "timeZoneId": "Europe/Amsterdam",
            "ttid": "android",
            **query,
        }
        if self.sid:
            params["sid"] = self.sid
        post_data = json.dumps(data, separators=(",", ":")) if data else ""
        signed = {**params, "postData": post_data} if post_data else params
        params["sign"] = self._sign(signed)
        reply = _post(
            f"{self.url}/api.json?{urllib.parse.urlencode(params)}",
            form={"postData": post_data} if post_data else {},
            headers={"User-Agent": "TY-UA=APP/Android/2.4.0/SDK/null"},
        )
        if "result" not in reply:
            raise LookupFailed(f"{action} failed: {reply.get('errorCode')} {reply.get('errorMsg')}")
        return reply["result"]

    def login(self, eufy_uid: str, country: str) -> None:
        tuya_uid = f"eh-{eufy_uid}"
        challenge = self.call(
            "tuya.m.user.uid.token.create", data={"uid": tuya_uid, "countryCode": country}
        )
        modulus, exponent = int(challenge["publicKey"]), int(challenge["exponent"])
        plain = int.from_bytes(_tuya_password(tuya_uid).encode(), "big")
        encrypted = pow(plain, exponent, modulus).to_bytes((modulus.bit_length() + 7) // 8, "big")
        session = self.call(
            "tuya.m.user.uid.password.login.reg",
            data={
                "uid": tuya_uid,
                "countryCode": country,
                "createGroup": True,
                "ifencrypt": 1,
                "passwd": encrypted.hex(),
                "options": '{"group": 1}',
                "token": challenge["token"],
            },
        )
        self.sid = session["sid"]
        self.url = session["domain"]["mobileApiUrl"]

    def devices(self) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for home in self.call("tuya.m.location.list", "2.1") or []:
            gid = str(home.get("groupId") or home.get("locationId") or "")
            if gid:
                for device in self.call("tuya.m.my.group.device.list", gid=gid) or []:
                    found.setdefault(device["devId"], device)
        for device in self.call("tuya.m.my.shared.device.list") or []:
            found.setdefault(device["devId"], device)
        return [d for d in found.values() if d.get("localKey")]


def _tuya_password(tuya_uid: str) -> str:
    padded = tuya_uid.zfill(-(-len(tuya_uid) // 16) * 16).encode()
    encryptor = Cipher(
        algorithms.AES(TUYA_PASSWORD_AES_KEY), modes.CBC(TUYA_PASSWORD_AES_IV)
    ).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return hashlib.md5(encrypted.hex().upper().encode()).hexdigest()


def main() -> int:
    email = input("Eufy e-mail: ").strip()
    password = getpass.getpass("Eufy wachtwoord: ")
    try:
        uid, country = eufy_login(email, password)
        session = TuyaSession()
        session.login(uid, country)
        devices = session.devices()
    except (LookupFailed, OSError) as err:
        print(f"\nMislukt: {err}", file=sys.stderr)
        return 1
    if not devices:
        print("\nGeen apparaten met een local key gevonden.", file=sys.stderr)
        return 1
    for device in devices:
        print(f"\nnaam       {device.get('name')}")
        print(f"product    {device.get('productId')}")
        print(f"device_id  {device['devId']}")
        print(f"local_key  {device['localKey']}")
    print("\nVul device_id en local_key in bij de integratie; het IP-adres zie je in je router.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
