from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from ..paths import PROJECT_ROOT


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
KEYRING_SERVICE = "headmasters-scroll-game-board"
KEYRING_ACCOUNT = "gmail-oauth-token"


class GmailUnavailable(RuntimeError):
    pass


def _libraries():
    try:
        import keyring
        from google.auth.transport.requests import AuthorizedSession, Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise GmailUnavailable(
            "Install the Game Board dependencies with: python -m pip install -e .[game-board]"
        ) from error
    return keyring, Request, Credentials, InstalledAppFlow, AuthorizedSession


class GmailSender:
    def __init__(self, credentials_path: str, sender: str = ""):
        path = Path(credentials_path)
        self.credentials_path = path if path.is_absolute() else PROJECT_ROOT / path
        self.sender = sender.strip()

    def _stored_credentials(self):
        keyring, _request, Credentials, _flow, _build = _libraries()
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        return Credentials.from_authorized_user_info(json.loads(raw), SCOPES) if raw else None

    def _store(self, credentials) -> None:
        keyring, *_rest = _libraries()
        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, credentials.to_json())

    def authorize(self) -> dict[str, Any]:
        _keyring, Request, _credentials, InstalledAppFlow, _build = _libraries()
        credentials = self._stored_credentials()
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if not credentials or not credentials.valid:
            if not self.credentials_path.is_file():
                raise GmailUnavailable(f"Google OAuth credential file not found: {self.credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
            credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True)
        self._store(credentials)
        return {"connected": True, "scopes": list(credentials.scopes or SCOPES)}

    def status(self) -> dict[str, Any]:
        try:
            credentials = self._stored_credentials()
        except GmailUnavailable as error:
            return {"connected": False, "error": str(error)}
        return {
            "connected": bool(credentials and (credentials.valid or credentials.refresh_token)),
            "credentials_file_found": self.credentials_path.is_file(),
            "sender": self.sender,
        }

    def send(self, recipient: str, subject: str, body: str) -> str:
        _keyring, Request, _credentials, _flow, AuthorizedSession = _libraries()
        credentials = self._stored_credentials()
        if not credentials:
            raise GmailUnavailable("Connect a Gmail account before sending invitations")
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._store(credentials)
        if not credentials.valid:
            raise GmailUnavailable("Gmail authorization is no longer valid; connect the account again")
        message = EmailMessage()
        message["To"] = recipient
        if self.sender:
            message["From"] = self.sender
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        payload = {"raw": raw}
        curl = shutil.which("curl.exe") if sys.platform == "win32" else None
        if curl:
            result = self._send_with_windows_curl(curl, credentials.token, payload)
            return str(result.get("id", "sent"))
        transport = AuthorizedSession(credentials)
        response = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = transport.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    json=payload,
                    timeout=(10, 30),
                )
                if response.status_code < 500 and response.status_code != 429:
                    break
            except Exception as error:
                last_error = error
            if attempt < 2:
                time.sleep(attempt + 1)
        if response is None:
            raise GmailUnavailable(f"Gmail could not be reached: {last_error}") from last_error
        if not 200 <= response.status_code < 300:
            try:
                detail = response.json().get("error", {}).get("message")
            except (AttributeError, ValueError):
                detail = None
            raise GmailUnavailable(
                detail or f"Gmail rejected the message with status {response.status_code}"
            )
        result = response.json()
        return str(result.get("id", "sent"))

    @staticmethod
    def _send_with_windows_curl(
        curl: str,
        access_token: str,
        payload: dict[str, str],
    ) -> dict[str, Any]:
        """Use Windows curl when Python socket traffic to Google is filtered.

        The bearer token is supplied through curl's stdin config rather than its
        command line, and the temporary message body is always removed.
        """

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix="headmasters-scroll-gmail-",
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, separators=(",", ":"))
                temporary_path = Path(temporary.name)

            def quoted(value: str) -> str:
                return value.replace("\\", "\\\\").replace('"', '\\"')

            config = "\n".join(
                (
                    "silent",
                    "show-error",
                    "connect-timeout = 10",
                    "max-time = 45",
                    'request = "POST"',
                    'url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"',
                    f'header = "Authorization: Bearer {quoted(access_token)}"',
                    'header = "Content-Type: application/json"',
                    f'data-binary = "@{quoted(str(temporary_path))}"',
                    'write-out = "\\n%{http_code}"',
                    "",
                )
            )
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            completed = subprocess.run(
                [curl, "--config", "-"],
                input=config,
                text=True,
                capture_output=True,
                timeout=50,
                creationflags=creation_flags,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or "Windows curl could not reach Gmail"
                raise GmailUnavailable(detail)
            response_text, separator, status_text = completed.stdout.rpartition("\n")
            if not separator or not status_text.isdigit():
                raise GmailUnavailable("Gmail returned an unreadable response")
            status = int(status_text)
            try:
                result = json.loads(response_text) if response_text else {}
            except json.JSONDecodeError as error:
                raise GmailUnavailable("Gmail returned an unreadable response") from error
            if not 200 <= status < 300:
                detail = result.get("error", {}).get("message") if isinstance(result, dict) else None
                raise GmailUnavailable(detail or f"Gmail rejected the message with status {status}")
            return result
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
