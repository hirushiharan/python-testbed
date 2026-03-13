"""Retrieve Outlook mailbox data through Microsoft Graph.

This script uses Azure AD application credentials (client credentials flow)
to fetch mailbox folders and messages from Inbox, Sent Items, and optionally
all folders for a target mailbox.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
DEFAULT_FOLDER_NAMES = ["inbox", "sentitems"]
REQUEST_TIMEOUT_SECONDS = 60

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Retrieve Outlook mailbox folders and messages via Microsoft Graph"
    )
    parser.add_argument(
        "--all-folders",
        action="store_true",
        help="Fetch messages from all mail folders (not only Inbox and Sent Items)",
    )
    parser.add_argument(
        "--folder",
        action="append",
        default=[],
        metavar="FOLDER_NAME",
        help="Additional mail folder names to fetch, e.g. drafts, archive",
    )
    parser.add_argument(
        "--max-per-folder",
        type=int,
        default=25,
        help="Maximum number of messages to fetch per folder (default: 25)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Pretty-print JSON output (default output is also JSON)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def _request_json(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
) -> dict[str, Any]:
    """Make an HTTP request and decode a JSON response payload."""
    request = urllib.request.Request(url=url, data=body, method=method)
    for key, value in headers.items():
        request.add_header(key, value)

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content = response.read().decode("utf-8")
            logger.debug("Response received from %s with %d bytes", url, len(content))
            if not content:
                return {}
            return json.loads(content)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code}: {error_body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Request a Microsoft Graph access token using client credentials flow."""
    token_url = TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
    form_data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")

    token_payload = _request_json(
        url=token_url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=form_data,
    )

    access_token = str(token_payload.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("Failed to obtain Microsoft Graph access token")
    return access_token


def graph_get(access_token: str, url: str) -> dict[str, Any]:
    """Call Microsoft Graph GET endpoint and decode JSON response."""
    return _request_json(
        url=url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )


def list_mail_folders(access_token: str, mailbox: str) -> list[dict[str, Any]]:
    """List all mail folders for a mailbox, including nested child folders."""
    encoded_mailbox = urllib.parse.quote(mailbox)
    root_url = f"{GRAPH_BASE_URL}/users/{encoded_mailbox}/mailFolders?$top=200"
    pending_urls = [root_url]
    folders_by_id: dict[str, dict[str, Any]] = {}

    while pending_urls:
        url = pending_urls.pop(0)
        while url:
            payload = graph_get(access_token=access_token, url=url)
            page_folders = payload.get("value") or []
            if isinstance(page_folders, list):
                for item in page_folders:
                    if not isinstance(item, dict):
                        continue

                    folder_id = str(item.get("id", "")).strip()
                    if not folder_id:
                        continue

                    if folder_id not in folders_by_id:
                        folders_by_id[folder_id] = item

                    child_count = int(item.get("childFolderCount", 0) or 0)
                    if child_count > 0:
                        encoded_folder_id = urllib.parse.quote(folder_id)
                        child_url = (
                            f"{GRAPH_BASE_URL}/users/{encoded_mailbox}/mailFolders/"
                            f"{encoded_folder_id}/childFolders?$top=200"
                        )
                        pending_urls.append(child_url)

            url = str(payload.get("@odata.nextLink", "")).strip() or ""

    return list(folders_by_id.values())


def build_folder_name_to_id_map(folders: list[dict[str, Any]]) -> dict[str, str]:
    """Build a case-insensitive map from folder display name to folder id."""
    name_to_id: dict[str, str] = {}
    for folder in folders:
        folder_name = str(folder.get("displayName", "")).strip()
        folder_id = str(folder.get("id", "")).strip()
        if folder_name and folder_id:
            name_to_id[folder_name.casefold()] = folder_id
    return name_to_id


def fetch_messages_for_folder(
    access_token: str,
    mailbox: str,
    folder_id: str,
    max_messages: int,
) -> list[dict[str, Any]]:
    """Fetch messages for a folder, following pagination until max_messages."""
    if max_messages <= 0:
        return []

    encoded_mailbox = urllib.parse.quote(mailbox)
    encoded_folder = urllib.parse.quote(folder_id)
    select_fields = (
        "id,subject,from,toRecipients,ccRecipients,bccRecipients,"
        "receivedDateTime,sentDateTime,isRead,importance,hasAttachments,"
        "bodyPreview,webLink,parentFolderId"
    )
    page_size = min(max_messages, 100)
    url = (
        f"{GRAPH_BASE_URL}/users/{encoded_mailbox}/mailFolders/{encoded_folder}/messages"
        f"?$top={page_size}&$orderby=receivedDateTime desc&$select={select_fields}"
    )

    messages: list[dict[str, Any]] = []
    while url and len(messages) < max_messages:
        payload = graph_get(access_token=access_token, url=url)
        page_messages = payload.get("value") or []
        if isinstance(page_messages, list):
            for item in page_messages:
                if isinstance(item, dict):
                    messages.append(item)
                    if len(messages) >= max_messages:
                        break
        url = str(payload.get("@odata.nextLink", "")).strip() or ""

    return messages


def build_output(
    mailbox: str,
    folders: list[dict[str, Any]],
    messages_by_folder: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Create serializable output payload."""
    return {
        "mailbox": mailbox,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "folders": folders,
        "messages_by_folder": messages_by_folder,
    }


def main() -> int:
    """Run Outlook mailbox retrieval command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)
    load_dotenv()

    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "").strip()
    client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "").strip()
    mailbox = os.getenv("OUTLOOK_MAILBOX", "").strip()

    if not tenant_id or not client_id or not client_secret or not mailbox:
        logger.error(
            "Missing one or more required environment variables: "
            "OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_MAILBOX"
        )
        return 1

    if args.max_per_folder < 0:
        logger.error("--max-per-folder must be >= 0")
        return 1

    try:
        access_token = get_access_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        all_folders = list_mail_folders(access_token=access_token, mailbox=mailbox)
        folder_name_to_id = build_folder_name_to_id_map(all_folders)

        requested_folders = [name.casefold() for name in DEFAULT_FOLDER_NAMES]
        requested_folders.extend(item.strip().casefold() for item in args.folder if item.strip())

        if args.all_folders:
            target_names = sorted(folder_name_to_id.keys())
        else:
            # Keep order and remove duplicates.
            seen: set[str] = set()
            target_names = []
            for name in requested_folders:
                if name in seen:
                    continue
                seen.add(name)
                target_names.append(name)

        messages_by_folder: dict[str, list[dict[str, Any]]] = {}
        missing_folders: list[str] = []

        for folder_name in target_names:
            folder_id = folder_name_to_id.get(folder_name)
            if not folder_id:
                missing_folders.append(folder_name)
                continue

            messages = fetch_messages_for_folder(
                access_token=access_token,
                mailbox=mailbox,
                folder_id=folder_id,
                max_messages=args.max_per_folder,
            )
            messages_by_folder[folder_name] = messages

        if missing_folders:
            logger.warning("Some requested folders were not found: %s", ", ".join(missing_folders))

        output_payload = build_output(
            mailbox=mailbox,
            folders=all_folders,
            messages_by_folder=messages_by_folder,
        )

        if args.json:
            print(json.dumps(output_payload, indent=2))
        else:
            print(json.dumps(output_payload))
    except Exception as exc:
        logger.error("Failed to retrieve Outlook mailbox data: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
