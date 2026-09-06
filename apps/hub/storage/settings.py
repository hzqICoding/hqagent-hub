from __future__ import annotations

import json
import platform
from pathlib import Path

from protocol.generated.python import AppearanceSettings, UserSettingsView

from core.constants import APP_VERSION, PROTOCOL_VERSION
from storage.database import Database, Transaction


DEFAULT_APPEARANCE = {
    "mode": "system",
    "palette": "hq-blue",
    "density": "comfortable",
    "contrast": "normal",
    "reduceMotion": "system",
    "fontScale": 1,
}


class SettingsRepository:
    def __init__(self, database: Database, data_dir: Path, log_dir: Path, hub_url: str = "") -> None:
        self.database = database
        self.data_dir = data_dir
        self.log_dir = log_dir
        self.hub_url = hub_url

    def _get(self, key: str, default: object) -> object:
        with self.database.locked_connection() as connection:
            row = connection.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _put(self, key: str, value: object) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self.database.transaction() as transaction:
            transaction.connection.execute(
                "INSERT INTO settings(key,value_json) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                (key, encoded),
            )

    def get_appearance(self) -> AppearanceSettings:
        return AppearanceSettings.model_validate(self._get("appearance", DEFAULT_APPEARANCE))

    def set_appearance(self, value: AppearanceSettings) -> AppearanceSettings:
        self._put("appearance", value.model_dump(mode="json", by_alias=True))
        return value

    def set_appearance_in_transaction(
        self, transaction: Transaction, value: AppearanceSettings
    ) -> AppearanceSettings:
        encoded = json.dumps(
            value.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        transaction.connection.execute(
            "INSERT INTO settings(key,value_json) VALUES('appearance',?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (encoded,),
        )
        return value

    def get_all(self) -> UserSettingsView:
        appearance = self.get_appearance()
        raw = {
            "appearance": appearance,
            "general": self._get(
                "general",
                {"language": "zh-CN", "launchAtLogin": True, "minimizeToTray": True, "closeToTray": True},
            ),
            "connection": {"hubUrl": self.hub_url, "cloudEnabled": False, "deviceName": platform.node() or "Local PC"},
            "security": self._get(
                "security",
                {"requireApprovalForDangerousActions": True, "allowedPathsOnly": True, "approvalTimeoutMinutes": 30},
            ),
            "updates": self._get(
                "updates", {"channel": "stable", "autoCheck": True, "autoDownload": False, "autoInstall": False}
            ),
            "telemetry": self._get("telemetry", {"anonymousTelemetry": False}),
            "dataDir": str(self.data_dir),
            "logDir": str(self.log_dir),
            "appVersion": APP_VERSION,
            "protocolVersion": PROTOCOL_VERSION,
        }
        return UserSettingsView.model_validate(raw)
