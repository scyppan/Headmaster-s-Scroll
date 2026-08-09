from __future__ import annotations

import base64
import json
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
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as error:
        raise GmailUnavailable(
            "Install the Game Board dependencies with: python -m pip install -e .[game-board]"
        ) from error
    return keyring, Request, Credentials, InstalledAppFlow, build


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
        _keyring, Request, _credentials, _flow, build = _libraries()
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
        result = build("gmail", "v1", credentials=credentials, cache_discovery=False).users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return str(result.get("id", "sent"))

