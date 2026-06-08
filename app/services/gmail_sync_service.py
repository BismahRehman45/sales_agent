"""
Gmail Sync Service

Handles incremental email synchronization using Gmail API's history.list() endpoint.
Supports token refresh, deduplication, and idempotent processing.
"""

import logging
from datetime import datetime, timezone
from email.parser import BytesParser
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.gmail_message import GmailMessage
from app.models.user import User
from app.repositories import gmail_message_repository, user_repository, document_repository
from app.services.gmail_token_service import ensure_token_fresh
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://www.googleapis.com/gmail/v1/users/me"


class GmailSyncService:
    """Service for synchronizing Gmail emails incrementally."""

    @staticmethod
    async def sync_user_emails(db: AsyncSession, user: User) -> dict[str, Any]:
        """
        Sync emails for a user using incremental fetch.

        Returns:
            {
                'fetched_count': int,
                'processed_count': int,
                'synced_messages': list[GmailMessage],
                'errors': list[str]
            }
        """
        try:
            # Ensure token is fresh
            user = await ensure_token_fresh(db, user)
            if not user.gmail_access_token:
                return {
                    "fetched_count": 0,
                    "processed_count": 0,
                    "synced_messages": [],
                    "errors": ["No Gmail access token available"],
                }

            # Fetch new emails
            emails = await GmailSyncService._fetch_incremental_emails(user)
            fetched_count = len(emails)
            logger.info(f"User {user.id}: Fetched {fetched_count} emails from Gmail API")

            processed_messages = []
            errors = []

            async with httpx.AsyncClient() as client:
                for email_data in emails:
                    try:
                        # Check for duplicates
                        gmail_msg = await gmail_message_repository.get_message_by_gmail_id(
                            db, user.id, email_data["message_id"]
                        )
                        if gmail_msg:
                            logger.debug(
                                f"User {user.id}: Skipping duplicate message {email_data['message_id']}"
                            )
                            continue

                        # Create GmailMessage record
                        gmail_msg = GmailMessage(
                            user_id=user.id,
                            gmail_message_id=email_data["message_id"],
                            subject=email_data.get("subject"),
                            sender=email_data.get("from"),
                            received_at=email_data.get("received_at"),
                            status="pending",
                        )
                        gmail_msg = await gmail_message_repository.create_message(db, gmail_msg)

                        # Create Document for processing
                        doc = Document(
                            user_id=user.id,
                            source="gmail",
                            title=email_data.get("subject", "No Subject"),
                            content=email_data.get("body", ""),
                            file_type="email",
                            status="pending",
                            sender_email=email_data.get("from"),  # Set sender email
                        )
                        # print(f"create Document for processing: {email_data.get("body", "")}")
                        logger.info(f"create Document for processing: {email_data.get("body", "")}")
                        doc = await document_repository.create_document(db, doc)

                        # Summarize email content with the LLM
                        try:
                            summary = await LLMService.summarize_text(doc.content)
                            doc.summary = summary
                            doc.status = "processed"
                            gmail_msg.status = "processed"
                        except Exception as e:
                            doc.status = "failed"
                            doc.error_message = f"LLM summary failed: {str(e)}"
                            gmail_msg.status = "failed"
                            logger.error(
                                f"User {user.id}: Failed to summarize document {doc.id}: {str(e)}"
                            )

                        doc = await document_repository.update_document(db, doc)

                        # Link document to Gmail message
                        gmail_msg.document_id = doc.id
                        await gmail_message_repository.update_message(db, gmail_msg)

                        # Enqueue project matching task if document was processed successfully
                        if doc.status == "processed":
                            try:
                                from app.tasks.project_matching_task import match_document_to_project
                                match_document_to_project.delay(str(doc.id))
                            except Exception as e:
                                logger.error(
                                    f"User {user.id}: Failed to enqueue project matching for document {doc.id}: {str(e)}"
                                )

                        processed_messages.append(gmail_msg)
                        logger.debug(
                            f"User {user.id}: Created document {doc.id} for email {email_data['message_id']}"
                        )

                    except Exception as e:
                        error_msg = f"Error processing email {email_data.get('message_id')}: {str(e)}"
                        logger.error(error_msg)
                        errors.append(error_msg)

            # Update sync metadata
            if emails:
                latest_history_id = emails[-1].get("history_id")
                if latest_history_id:
                    user.gmail_history_id = latest_history_id
                    await user_repository.update_user(db, user)
            elif user.gmail_history_id is None:
                # Fallback path cleared the expired history_id — persist the reset
                await user_repository.update_user(db, user)

            user.last_email_sync_at = datetime.now(timezone.utc)
            await user_repository.update_user(db, user)

            return {
                "fetched_count": fetched_count,
                "processed_count": len(processed_messages),
                "synced_messages": processed_messages,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"Error syncing emails for user {user.id}: {str(e)}")
            return {
                "fetched_count": 0,
                "processed_count": 0,
                "synced_messages": [],
                "errors": [str(e)],
            }

    @staticmethod
    async def _fetch_incremental_emails(user: User) -> list[dict[str, Any]]:
        """
        Fetch emails using incremental sync via history.list().
        Falls back to full INBOX sync if history_id is expired (404).

        Returns:
            List of email dicts with: message_id, subject, from, body, received_at, history_id
        """
        headers = {"Authorization": f"Bearer {user.gmail_access_token}"}
        emails = []
        history_reset_needed = False

        async with httpx.AsyncClient() as client:
            try:
                if user.gmail_history_id:
                    # Incremental sync: fetch only new messages
                    logger.info(
                        f"User {user.id}: Fetching incremental emails from history_id {user.gmail_history_id}"
                    )
                    try:
                        email_list = await GmailSyncService._fetch_from_history(
                            client, headers, user.gmail_history_id
                        )
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 404:
                            logger.warning(
                                f"User {user.id}: history_id {user.gmail_history_id} expired or invalid (404). "
                                f"Falling back to full INBOX sync."
                            )
                            email_list = await GmailSyncService._fetch_all_inbox(client, headers)
                            history_reset_needed = True
                        else:
                            raise
                else:
                    # First-time sync: fetch all INBOX emails
                    logger.info(f"User {user.id}: First-time sync - fetching all INBOX emails")
                    email_list = await GmailSyncService._fetch_all_inbox(client, headers)

                # Fetch full details for each message
                for msg_id in email_list:
                    try:
                        full_email = await GmailSyncService._fetch_full_email(
                            client, headers, msg_id
                        )
                        if full_email:
                            emails.append(full_email)
                    except Exception as e:
                        logger.warning(f"Failed to fetch email {msg_id}: {str(e)}")

            except Exception as e:
                logger.error(f"Error fetching emails for user {user.id}: {str(e)}")

        if history_reset_needed:
            user.gmail_history_id = None

        return emails

    @staticmethod
    async def _fetch_from_history(
        client: httpx.AsyncClient, headers: dict, start_history_id: str
    ) -> list[str]:
        """Fetch message IDs from history.list() starting from history_id."""
        message_ids = []
        history_id = start_history_id
        page_token = None

        while history_id:
            params = {
                "startHistoryId": history_id,
                "pageToken": page_token,
                "historyTypes": "messageAdded",
            }

            try:
                response = await client.get(
                    f"{GMAIL_API_BASE}/history", headers=headers, params=params
                )
                response.raise_for_status()
                data = response.json()

                # Extract message IDs from history records
                for record in data.get("history", []):
                    if "messagesAdded" in record:
                        for msg in record["messagesAdded"]:
                            message_ids.append(msg["message"]["id"])

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            except httpx.HTTPStatusError:
                # 404 = history_id expired. Bubble up so caller can fall back to inbox.
                # Other HTTP errors (401, 403, 429) also bubble up.
                raise
            except Exception as e:
                # Network / decode errors only — log and stop pagination.
                logger.error(f"Error fetching history page: {str(e)}")
                break

        return message_ids

    @staticmethod
    async def _fetch_all_inbox(client: httpx.AsyncClient, headers: dict) -> list[str]:
        """Fetch all message IDs from INBOX (first-time sync)."""
        message_ids = []
        page_token = None

        while True:
            params = {
                "q": "in:inbox",
                "pageToken": page_token,
                "fields": "messages(id),nextPageToken",
            }

            try:
                response = await client.get(
                    f"{GMAIL_API_BASE}/messages", headers=headers, params=params
                )
                response.raise_for_status()
                data = response.json()

                for msg in data.get("messages", []):
                    message_ids.append(msg["id"])

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            except Exception as e:
                logger.error(f"Error fetching INBOX: {str(e)}")
                break

        return message_ids

    @staticmethod
    async def _fetch_full_email(
        client: httpx.AsyncClient, headers: dict, message_id: str
    ) -> dict[str, Any] | None:
        """Fetch full email details including subject, sender, and body."""
        try:
            response = await client.get(
                f"{GMAIL_API_BASE}/messages/{message_id}",
                headers=headers,
                params={"format": "full", "fields": "payload,internalDate,historyId"},
            )
            response.raise_for_status()
            msg_data = response.json()

            headers_list = msg_data.get("payload", {}).get("headers", [])
            headers_dict = {h["name"]: h["value"] for h in headers_list}

            subject = headers_dict.get("Subject", "")
            from_addr = headers_dict.get("From", "")

            # Extract body
            body = GmailSyncService._extract_body(msg_data.get("payload", {}))

            # Parse received timestamp
            received_at = None
            date_str = headers_dict.get("Date")
            if date_str:
                try:
                    from email.utils import parsedate_to_datetime
                    received_at = parsedate_to_datetime(date_str)
                except Exception:
                    pass

            return {
                "message_id": message_id,
                "subject": subject,
                "from": from_addr,
                "body": body,
                "received_at": received_at,
                "history_id": msg_data.get("historyId"),
            }

        except Exception as e:
            logger.error(f"Error fetching full email {message_id}: {str(e)}")
            return None

    @staticmethod
    def _extract_body(payload: dict) -> str:
        """Extract email body from MIME payload."""
        body = ""

        # Try to get body from parts
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        import base64
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break

            # Fallback to HTML if plain text not found
            if not body:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/html":
                        data = part.get("body", {}).get("data", "")
                        if data:
                            import base64
                            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                            break
        else:
            # Single part message
            data = payload.get("body", {}).get("data", "")
            if data:
                import base64
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        return body[:5000]  # Limit body to 5000 chars to prevent huge documents
