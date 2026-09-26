import base64
import hashlib
import hmac
import secrets

from .common import Fault, canonical, require, stamp, uid

COOKIE = "__Host-hqremote"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class Security:
    def __init__(self, repo, settings):
        self.repo, self.settings = repo, settings
        self.dummy = self.password_hash("invalid-account-placeholder")

    def mac(self, purpose, value):
        return hmac.new(self.settings.key, (purpose + "\0" + value).encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def password_hash(password, salt=None):
        salt = salt or secrets.token_hex(16)
        hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return {"salt": salt, "hash": hashed}

    def create_account(self, name, password, display):
        require(1 <= len(name) <= 128 and 1 <= len(display) <= 120 and 12 <= len(password) <= 1024)
        with self.repo.transaction() as tx:
            key = "account:" + self.mac("login", name)
            require(tx.auth_get(key) is None, "IDEMPOTENCY_MISMATCH")
            account = dict(owner=uid(), loginName=name, displayName=display, password=self.password_hash(password))
            tx.auth_put(key, account, account["owner"])

    def rate(self, bucket):
        # Separate transaction: failed authentication must still consume rate quota.
        with self.repo.transaction() as tx:
            key = "rate:" + self.mac("rate", bucket)
            now = self.settings.clock()
            record = tx.auth_get(key)
            if not record or record["until"] <= now:
                record = dict(until=now + self.settings.rate_window, count=0)
            limited = record["count"] >= self.settings.rate_limit
            record["count"] += 1
            tx.auth_put(key, record)
        require(not limited, "REMOTE_RATE_LIMITED")

    def bearer(self, header):
        require(bool(header) and header.startswith("Bearer "), "REMOTE_DEVICE_AUTH_FAILED")
        token = header[7:]
        try:
            raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
            require(len(raw) >= 32 and len(token) <= 256, "REMOTE_DEVICE_AUTH_FAILED")
        except (ValueError, TypeError):
            raise Fault("REMOTE_DEVICE_AUTH_FAILED") from None
        return token, self.mac("device", token)

    def csrf(self, session_id):
        return self.mac("csrf", session_id)

    def token(self, session_id):
        return session_id + "." + self.mac("session", session_id)

    def session(self, tx, token):
        if not token or "." not in token or len(token) > 256:
            return None
        session_id = token.split(".")[0]
        if not hmac.compare_digest(self.token(session_id), token):
            return None
        value = tx.auth_get("session:" + session_id)
        if not value or value["revoked"] or value["expires"] <= self.settings.clock():
            return None
        return value

    def session_view(self, session):
        return dict(authenticated=True, account=session["account"], expiresAt=stamp(session["expires"]), csrfToken=self.csrf(session["id"]))

    def login(self, tx, body, idem, old_cookie):
        account = tx.auth_get("account:" + self.mac("login", body["loginName"]))
        stored = account["password"] if account else self.dummy
        proof = self.password_hash(body["password"], stored["salt"])
        require(hmac.compare_digest(stored["hash"], proof["hash"]) and account is not None, "REMOTE_AUTH_REQUIRED")
        key = "login:" + self.mac("login-replay", account["owner"] + ":" + idem)
        intent = self.mac("login-content", canonical(body))
        record = tx.auth_get(key)
        if record:
            require(record["intent"] == intent, "IDEMPOTENCY_MISMATCH")
            session = tx.auth_get("session:" + record["session"])
            require(not session["revoked"] and session["expires"] > self.settings.clock(), "REMOTE_AUTH_REQUIRED")
        else:
            old = self.session(tx, old_cookie)
            if old:
                old["revoked"] = True
                tx.auth_put("session:" + old["id"], old, old["owner"])
            session = dict(id=uid(), owner=account["owner"], revoked=False,
                           account={k: account[k] for k in ("loginName", "displayName")},
                           expires=self.settings.clock() + self.settings.session_ttl)
            tx.auth_put("session:" + session["id"], session, account["owner"])
            tx.auth_put(key, dict(intent=intent, session=session["id"]), account["owner"])
        return self.session_view(session), self.token(session["id"])

    def code(self, secret, request_id):
        # Reconstructible ONLY with the device's presented secret, never from the DB.
        material = hmac.new(secret.encode(), ("pair:" + request_id).encode(), hashlib.sha256).digest()
        return "".join(ALPHABET[b % len(ALPHABET)] for b in material[:8])

    def challenge(self, tx, secret, verifier, body, idem):
        require(tx.auth_get("credential:" + verifier) is None, "REMOTE_PAIRING_CONFLICT")
        key = "pair-intent:" + self.mac("pair-intent", verifier + ":" + idem)
        intent = self.mac("pair-content", canonical(body))
        old = tx.auth_get(key)
        if old:
            require(old["intent"] == intent, "IDEMPOTENCY_MISMATCH")
            record = tx.auth_get("challenge:" + old["id"])
            require(record["expires"] > self.settings.clock(), "REMOTE_PAIRING_EXPIRED")
            require(record["status"] == "pending", "REMOTE_PAIRING_CONFLICT")
        else:
            # Explicit new intent expires previous pending challenges for this secret.
            previous = tx.auth_get("pending:" + verifier)
            if previous:
                prior = tx.auth_get("challenge:" + previous["id"])
                if prior["status"] == "pending":
                    prior["expires"] = self.settings.clock()
                    tx.auth_put("challenge:" + previous["id"], prior)
            while True:
                identifier = uid()
                code_hash = self.mac("pair-code", self.code(secret, identifier))
                if tx.auth_get("code:" + code_hash) is None:
                    break
            record = dict(id=identifier, workerId=uid(), verifier=verifier, codeHash=code_hash,
                          expires=self.settings.clock() + 300, status="pending", device=body)
            tx.auth_put("challenge:" + identifier, record)
            tx.auth_put("pending:" + verifier, dict(id=identifier))
            tx.auth_put("code:" + code_hash, dict(id=identifier))
            tx.auth_put(key, dict(id=identifier, intent=intent))
        return dict(pairRequestId=record["id"], workerId=record["workerId"], pairCode=self.code(secret, record["id"]), expiresAt=stamp(record["expires"]), status="pending")

    def pairing_record(self, tx, code, identifier=None):
        lookup = tx.auth_get("code:" + self.mac("pair-code", code))
        require(lookup is not None and (identifier is None or lookup["id"] == identifier), "REMOTE_PAIRING_INVALID")
        record = tx.auth_get("challenge:" + lookup["id"])
        require(record["expires"] > self.settings.clock(), "REMOTE_PAIRING_EXPIRED")
        require(record["status"] == "pending", "REMOTE_PAIRING_CONFLICT")
        return record

    def device_identity(self, tx, verifier):
        identity = tx.auth_get("credential:" + verifier)
        require(identity is not None, "REMOTE_DEVICE_AUTH_FAILED")
        device = tx.get(identity["owner"], "device", identity["worker"])
        require(device is not None, "REMOTE_DEVICE_AUTH_FAILED")
        require(device["status"] != "revoked", "REMOTE_DEVICE_REVOKED")
        return identity["owner"], device
