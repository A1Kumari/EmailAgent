# src/clients/gmail_client.py

"""
Gmail Client (Enhanced)

Handles all email operations: reading (IMAP) and sending (SMTP).
Parses raw emails into EmailData objects.
Sends replies with proper threading headers.

Enhanced with:
  - R2: Full email thread context reconstruction
        Uses In-Reply-To, References, and subject-based fallback
        to build complete conversation history
  - R8: Graceful error handling for thread fetching
  - R9: Detailed logging for thread operations
  - R6: Full backward compatibility
"""

import imaplib
import smtplib
import email
import re
import time as _time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional
from datetime import datetime
import logging

from src.core.models import EmailData
from src.utils.config_manager import GmailConfig

logger = logging.getLogger(__name__)


class GmailClient:
    """
    Handles all Gmail IMAP (read) and SMTP (send) operations.

    Enhanced with R2 thread context awareness:
      - Reconstructs email threads using message headers
      - Provides conversation history for AI classification and replies

    Usage:
        client = GmailClient(config.gmail, thread_context_depth=5)
        emails = client.fetch_unread_emails(max_count=10)
        # Each email now has thread_messages populated automatically
    """

    def __init__(self, config: GmailConfig, thread_context_depth: int = 5):
        self.email_address = config.email
        self.app_password = config.app_password
        self.imap_server = config.imap_server
        self.smtp_server = config.smtp_server
        self.smtp_port = config.smtp_port

        # R2: Configurable thread context depth
        self.thread_context_depth = thread_context_depth

        logger.debug(
            f"GmailClient initialized | "
            f"email={self.email_address} | "
            f"thread_depth={self.thread_context_depth}"
        )

    # ──────────────────────────────────────────────
    # READING EMAILS (IMAP)
    # ──────────────────────────────────────────────

    def fetch_unread_emails(
        self,
        mailbox: str = "INBOX",
        max_count: int = 10,
        include_thread_context: bool = True,
    ) -> list:
        """
        Fetch unread emails from Gmail.

        Args:
            mailbox: Which folder to check (default: INBOX)
            max_count: Maximum number of emails to fetch
            include_thread_context: R2 — whether to fetch thread history
                                   for each email

        Returns:
            List of EmailData objects (with thread_messages populated if R2 enabled)
        """
        emails = []
        imap_connection = None

        try:
            # Step 1: Connect and login
            imap_connection = self._connect_imap()

            # Step 2: Select the mailbox folder
            status, messages = imap_connection.select(mailbox, readonly=False)
            if status != "OK":
                logger.error(f"Failed to select mailbox: {mailbox}")
                return emails

            # Step 3: Search for unread emails
            status, message_ids = imap_connection.search(None, "UNSEEN")
            if status != "OK":
                logger.error("Failed to search for unread emails")
                return emails

            # Step 4: Get the list of message IDs
            id_list = message_ids[0].split()
            if not id_list:
                logger.info("No unread emails found")
                return emails

            # Limit the number of emails we process
            id_list = id_list[:max_count]
            logger.info(f"Found {len(id_list)} unread email(s) to process")

            # Step 5: Fetch and parse each email
            for msg_id in id_list:
                try:
                    email_data = self._fetch_single_email(imap_connection, msg_id)
                    if email_data:
                        # R2: Populate thread context if enabled
                        if (
                            include_thread_context
                            and self.thread_context_depth > 0
                            and email_data.is_part_of_thread
                        ):
                            self._populate_thread_context(
                                imap_connection, email_data, mailbox
                            )

                        emails.append(email_data)
                except Exception as e:
                    # One bad email shouldn't stop us from processing others
                    logger.warning(f"Failed to parse email ID {msg_id}: {e}")
                    continue

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
        except ConnectionError as e:
            logger.error(f"Connection error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching emails: {e}")
        finally:
            # Always close the connection
            if imap_connection:
                try:
                    imap_connection.close()
                    imap_connection.logout()
                except Exception:
                    pass

        return emails

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        """Establish IMAP connection to Gmail."""
        logger.debug(f"Connecting to IMAP: {self.imap_server}")
        connection = imaplib.IMAP4_SSL(self.imap_server)
        connection.login(self.email_address, self.app_password)
        logger.debug("IMAP login successful")
        return connection

    def _fetch_single_email(
        self, connection: imaplib.IMAP4_SSL, msg_id: bytes
    ) -> Optional[EmailData]:
        """
        Fetch and parse a single email by its IMAP message ID.

        Args:
            connection: Active IMAP connection
            msg_id: IMAP message ID (bytes)

        Returns:
            EmailData object or None if parsing fails
        """
        # Fetch the full email (RFC822 = complete raw email)
        status, data = connection.fetch(msg_id, "(RFC822)")
        if status != "OK":
            logger.warning(f"Failed to fetch email ID {msg_id}")
            return None

        # Parse raw bytes into email message object
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Extract all fields
        email_data = EmailData(
            id=msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
            from_address=self._decode_header_value(msg.get("From", "")),
            to_address=self._decode_header_value(msg.get("To", "")),
            subject=self._decode_header_value(msg.get("Subject", "(No Subject)")),
            body=self._extract_body(msg),
            date=msg.get("Date", ""),
            message_id=msg.get("Message-ID", None),
            in_reply_to=msg.get("In-Reply-To", None),
            references=msg.get("References", None),
        )

        # R9: Log threading info
        if email_data.is_part_of_thread:
            logger.debug(
                f"[R2] Email {email_data.id} is part of thread | "
                f"in_reply_to={email_data.in_reply_to is not None} | "
                f"references={len(email_data.reference_chain)} refs"
            )

        return email_data

    # ──────────────────────────────────────────────
    # R2: THREAD CONTEXT AWARENESS
    # ──────────────────────────────────────────────

    def _populate_thread_context(
        self,
        connection: imaplib.IMAP4_SSL,
        email_data: EmailData,
        mailbox: str,
    ):
        """
        R2: Populate an email's thread_messages with previous conversation history.

        Strategy (in order of reliability):
          1. Search by References header chain (most reliable)
          2. Search by In-Reply-To header
          3. Fallback: Search by subject line

        Args:
            connection: Active IMAP connection
            email_data: The email to populate with thread context
            mailbox: Current mailbox
        """
        try:
            thread_messages = []
            seen_message_ids = set()

            # Track the current email's message_id to avoid including it
            if email_data.message_id:
                seen_message_ids.add(email_data.message_id.strip())

            # ── Strategy 1: Search by References chain ──
            if email_data.references:
                ref_results = self._fetch_thread_by_references(
                    connection, email_data.reference_chain, seen_message_ids
                )
                thread_messages.extend(ref_results)

                # Update seen set
                for msg in ref_results:
                    mid = msg.get("message_id", "")
                    if mid:
                        seen_message_ids.add(mid.strip())

            # ── Strategy 2: Search by In-Reply-To ───────
            if email_data.in_reply_to and len(thread_messages) == 0:
                reply_results = self._search_by_header(
                    connection,
                    "Message-ID",
                    email_data.in_reply_to.strip(),
                    seen_message_ids,
                )
                thread_messages.extend(reply_results)

                for msg in reply_results:
                    mid = msg.get("message_id", "")
                    if mid:
                        seen_message_ids.add(mid.strip())

            # ── Strategy 3: Fallback — search by subject ─
            if len(thread_messages) == 0 and email_data.subject:
                subject_results = self._fetch_thread_by_subject(
                    connection, email_data, seen_message_ids
                )
                thread_messages.extend(subject_results)

            # ── Sort by date and limit to configured depth ──
            thread_messages = self._sort_and_limit_thread(thread_messages)

            # ── Assign to email data ──
            email_data.thread_messages = thread_messages

            # R9: Log thread fetch results
            logger.info(
                f"[R2] Thread context for email {email_data.id}: "
                f"{len(thread_messages)} previous messages found"
            )
            if thread_messages:
                participants = set(m.get("from", "") for m in thread_messages)
                logger.debug(f"[R2] Thread participants: {participants}")

        except Exception as e:
            # R8: Thread fetching failure should not block email processing
            logger.warning(
                f"[R8] Thread context fetch failed for email {email_data.id}: {e}. "
                f"Proceeding without thread context."
            )
            email_data.thread_messages = []

    def _fetch_thread_by_references(
        self,
        connection: imaplib.IMAP4_SSL,
        reference_chain: list[str],
        seen_ids: set,
    ) -> list[dict]:
        """
        R2 (AC4): Fetch thread messages by walking the References header chain.

        The References header contains a space-separated list of Message-IDs
        representing the full conversation history.

        Args:
            connection: Active IMAP connection
            reference_chain: List of Message-IDs from References header
            seen_ids: Message-IDs we've already fetched (to avoid duplicates)

        Returns:
            List of thread message dicts
        """
        thread_messages = []

        if not reference_chain:
            return thread_messages

        logger.debug(
            f"[R2] Searching References chain: {len(reference_chain)} message IDs"
        )

        for ref_id in reference_chain:
            ref_id = ref_id.strip()
            if not ref_id or ref_id in seen_ids:
                continue

            try:
                results = self._search_by_header(
                    connection, "Message-ID", ref_id, seen_ids
                )
                thread_messages.extend(results)

                # Mark as seen
                for msg in results:
                    mid = msg.get("message_id", "")
                    if mid:
                        seen_ids.add(mid.strip())

            except Exception as e:
                logger.debug(f"[R2] Could not fetch reference {ref_id}: {e}")
                continue

            # Stop if we have enough messages
            if len(thread_messages) >= self.thread_context_depth:
                break

        return thread_messages

    def _fetch_thread_by_subject(
        self,
        connection: imaplib.IMAP4_SSL,
        email_data: EmailData,
        seen_ids: set,
    ) -> list[dict]:
        """
        R2: Fallback thread search by subject line.
        Less reliable than header-based search, but catches threads
        where headers are missing or stripped.

        Args:
            connection: Active IMAP connection
            email_data: The current email
            seen_ids: Message-IDs already fetched

        Returns:
            List of thread message dicts
        """
        thread_messages = []

        # Clean subject (remove "Re:", "Fwd:", etc.)
        clean_subject = email_data.subject
        for prefix in ["Re:", "RE:", "re:", "Fwd:", "FWD:", "fwd:", "Fw:", "FW:"]:
            clean_subject = clean_subject.replace(prefix, "").strip()

        if not clean_subject or len(clean_subject) < 5:
            return thread_messages

        logger.debug(f"[R2] Fallback: searching by subject '{clean_subject[:50]}...'")

        try:
            # IMAP subject search
            search_criteria = f'(SUBJECT "{clean_subject[:100]}")'
            status, msg_ids = connection.search(None, search_criteria)

            if status != "OK" or not msg_ids[0]:
                return thread_messages

            id_list = msg_ids[0].split()

            # Fetch and filter
            for msg_id in id_list:
                if len(thread_messages) >= self.thread_context_depth:
                    break

                try:
                    email_msg = self._fetch_single_email(connection, msg_id)
                    if email_msg is None:
                        continue

                    # Skip the current email
                    if (
                        email_msg.message_id
                        and email_msg.message_id.strip() in seen_ids
                    ):
                        continue

                    # Skip if subject doesn't actually match well enough
                    msg_clean_subject = email_msg.subject
                    for prefix in [
                        "Re:",
                        "RE:",
                        "re:",
                        "Fwd:",
                        "FWD:",
                        "fwd:",
                        "Fw:",
                        "FW:",
                    ]:
                        msg_clean_subject = msg_clean_subject.replace(
                            prefix, ""
                        ).strip()

                    if msg_clean_subject.lower() != clean_subject.lower():
                        continue

                    thread_msg = self._email_data_to_thread_dict(email_msg)
                    thread_messages.append(thread_msg)

                    if email_msg.message_id:
                        seen_ids.add(email_msg.message_id.strip())

                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"[R2] Subject-based thread search failed: {e}")

        return thread_messages

    def _search_by_header(
        self,
        connection: imaplib.IMAP4_SSL,
        header_name: str,
        header_value: str,
        seen_ids: set,
    ) -> list[dict]:
        """
        R2: Search for emails by a specific header value.
        Reusable helper for searching by Message-ID, In-Reply-To, etc.

        Args:
            connection: Active IMAP connection
            header_name: Header to search (e.g., "Message-ID", "In-Reply-To")
            header_value: Value to search for
            seen_ids: Message-IDs already fetched

        Returns:
            List of thread message dicts
        """
        results = []

        try:
            # Clean the header value (remove angle brackets for search)
            search_value = header_value.strip().strip("<>")

            search_criteria = f'(HEADER {header_name} "{search_value}")'
            status, msg_ids = connection.search(None, search_criteria)

            if status != "OK" or not msg_ids[0]:
                # Try with angle brackets
                search_criteria = f'(HEADER {header_name} "<{search_value}>")'
                status, msg_ids = connection.search(None, search_criteria)

            if status != "OK" or not msg_ids[0]:
                return results

            for msg_id in msg_ids[0].split():
                try:
                    email_data = self._fetch_single_email(connection, msg_id)
                    if email_data is None:
                        continue

                    # Skip if already seen
                    if (
                        email_data.message_id
                        and email_data.message_id.strip() in seen_ids
                    ):
                        continue

                    thread_msg = self._email_data_to_thread_dict(email_data)
                    results.append(thread_msg)

                except Exception:
                    continue

        except Exception as e:
            logger.debug(
                f"[R2] Header search failed ({header_name}={header_value}): {e}"
            )

        return results

    def _sort_and_limit_thread(self, thread_messages: list[dict]) -> list[dict]:
        """
        R2 (AC5): Sort thread messages by date and limit to configured depth.
        When a thread has more than the configured depth, include only the
        most recent messages.

        Args:
            thread_messages: Unsorted list of thread message dicts

        Returns:
            Sorted and limited list
        """
        if not thread_messages:
            return []

        # De-duplicate by message_id
        seen = set()
        unique = []
        for msg in thread_messages:
            mid = msg.get("message_id", "")
            if mid and mid in seen:
                continue
            if mid:
                seen.add(mid)
            unique.append(msg)

        # Sort by date (oldest first)
        def parse_date_safe(msg: dict) -> datetime:
            """Parse date string, return epoch on failure."""
            date_str = msg.get("date", "")
            if not date_str:
                return datetime.min
            try:
                return parsedate_to_datetime(date_str)
            except Exception:
                return datetime.min

        unique.sort(key=parse_date_safe)

        # R2 (AC5): Limit to most recent N messages
        if len(unique) > self.thread_context_depth:
            logger.debug(
                f"[R2] Thread has {len(unique)} messages, "
                f"limiting to {self.thread_context_depth} most recent"
            )
            unique = unique[-self.thread_context_depth :]

        return unique

    @staticmethod
    def _email_data_to_thread_dict(email_data: EmailData) -> dict:
        """
        Convert an EmailData to a thread context dict.
        This is the format expected by GeminiAgent._build_thread_context().
        """
        return {
            "from": email_data.from_address,
            "subject": email_data.subject,
            "body": email_data.body[:500],  # Truncate for context
            "date": email_data.date,
            "message_id": email_data.message_id or "",
        }

    # ──────────────────────────────────────────────
    # R2: PUBLIC THREAD FETCHING
    # ──────────────────────────────────────────────

    def fetch_thread_context(
        self,
        message_id: str,
        references: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        subject: Optional[str] = None,
        mailbox: str = "INBOX",
        max_messages: Optional[int] = None,
    ) -> list:
        """
        R2: Fetch previous messages in the same email thread.
        Enhanced version — uses References chain, In-Reply-To, and
        subject-based fallback.

        This method opens its own IMAP connection, so it can be called
        independently of fetch_unread_emails.

        Args:
            message_id: Message-ID of the current email
            references: References header value (space-separated Message-IDs)
            in_reply_to: In-Reply-To header value
            subject: Subject line (for fallback search)
            mailbox: Which folder to search
            max_messages: Override for thread_context_depth

        Returns:
            List of dicts with 'from', 'subject', 'body', 'date', 'message_id'
        """
        if not message_id and not references and not in_reply_to:
            return []

        effective_depth = max_messages or self.thread_context_depth
        thread_messages = []
        seen_ids = set()
        imap_connection = None

        if message_id:
            seen_ids.add(message_id.strip())

        try:
            imap_connection = self._connect_imap()
            imap_connection.select(mailbox, readonly=True)

            # ── Strategy 1: References chain ──────
            if references:
                ref_chain = [ref.strip() for ref in references.split() if ref.strip()]
                logger.debug(f"[R2] fetch_thread_context: {len(ref_chain)} references")

                # Temporarily override depth for this search
                original_depth = self.thread_context_depth
                self.thread_context_depth = effective_depth

                ref_results = self._fetch_thread_by_references(
                    imap_connection, ref_chain, seen_ids
                )
                thread_messages.extend(ref_results)

                self.thread_context_depth = original_depth

                for msg in ref_results:
                    mid = msg.get("message_id", "")
                    if mid:
                        seen_ids.add(mid.strip())

            # ── Strategy 2: In-Reply-To ───────────
            if in_reply_to and len(thread_messages) == 0:
                reply_results = self._search_by_header(
                    imap_connection, "Message-ID", in_reply_to.strip(), seen_ids
                )
                thread_messages.extend(reply_results)

                for msg in reply_results:
                    mid = msg.get("message_id", "")
                    if mid:
                        seen_ids.add(mid.strip())

            # ── Strategy 3: Subject fallback ──────
            if len(thread_messages) == 0 and subject:
                # Build a minimal EmailData for the subject search
                dummy = EmailData(
                    id="search",
                    from_address="",
                    to_address="",
                    subject=subject,
                    body="",
                    date="",
                    message_id=message_id,
                )
                subject_results = self._fetch_thread_by_subject(
                    imap_connection, dummy, seen_ids
                )
                thread_messages.extend(subject_results)

            # Sort and limit
            original_depth = self.thread_context_depth
            self.thread_context_depth = effective_depth
            thread_messages = self._sort_and_limit_thread(thread_messages)
            self.thread_context_depth = original_depth

            logger.info(
                f"[R2] fetch_thread_context: found {len(thread_messages)} "
                f"thread messages"
            )

        except Exception as e:
            # R8: Thread fetching failure is non-fatal
            logger.warning(
                f"[R8] Thread context fetch failed: {e}. Returning empty thread."
            )
        finally:
            if imap_connection:
                try:
                    imap_connection.close()
                    imap_connection.logout()
                except Exception:
                    pass

        return thread_messages

    # ──────────────────────────────────────────────
    # EMAIL BODY EXTRACTION
    # ──────────────────────────────────────────────

    def _extract_body(self, msg: email.message.Message) -> str:
        """
        Extract plain text body from email.
        Handles both simple and multipart emails.

        Priority: text/plain > text/html (stripped) > empty string
        """
        body = ""

        if msg.is_multipart():
            # Walk through all parts, find text/plain
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                # Prefer plain text
                if content_type == "text/plain":
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        body = part.get_payload(decode=True).decode(
                            charset, errors="replace"
                        )
                        break  # Found plain text, stop looking
                    except Exception as e:
                        logger.warning(f"Failed to decode text/plain part: {e}")
                        continue

            # If no plain text found, try HTML as fallback
            # If no plain text found, try HTML as fallback
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        try:
                            charset = part.get_content_charset() or "utf-8"
                            html = part.get_payload(decode=True).decode(
                                charset, errors="replace"
                            )
                            # Basic HTML tag stripping
                            body = re.sub(r"<[^>]+>", "", html)
                            body = body.strip()
                            break
                        except Exception:
                            continue

        else:
            # Simple single-part email
            try:
                charset = msg.get_content_charset() or "utf-8"
                body = msg.get_payload(decode=True).decode(charset, errors="replace")
            except Exception as e:
                logger.warning(f"Failed to decode email body: {e}")
                body = "(Could not decode email body)"

        # Clean up the body text
        body = body.strip()
        if not body:
            body = "(Empty email body)"

        return body

    def _decode_header_value(self, header_value: str) -> str:
        """
        Decode email header value.
        Handles encoded headers like: =?UTF-8?Q?Hello_World?=
        """
        if not header_value:
            return ""

        try:
            decoded_parts = decode_header(header_value)
            decoded_string = ""
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    decoded_string += part.decode(charset or "utf-8", errors="replace")
                else:
                    decoded_string += part
            return decoded_string.strip()
        except Exception:
            # If decoding fails, return as-is
            return str(header_value).strip()

    # ──────────────────────────────────────────────
    # SENDING EMAILS (SMTP)
    # ──────────────────────────────────────────────

    def send_reply(
        self,
        to_address: str,
        subject: str,
        body: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> bool:
        """
        Send an email reply via SMTP.

        Args:
            to_address: Recipient email address
            subject: Email subject (should start with "Re: " for replies)
            body: Plain text email body
            in_reply_to: Message-ID of the email we're replying to
            references: References header for thread chain

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Build the email message
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to_address
            msg["Subject"] = subject

            # Add threading headers (crucial for Gmail to show in same thread)
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                # References should include the full chain
                if references:
                    msg["References"] = f"{references} {in_reply_to}"
                else:
                    msg["References"] = in_reply_to

            # Attach the body
            msg.attach(MIMEText(body, "plain"))

            # Connect and send
            logger.debug(f"Connecting to SMTP: {self.smtp_server}:{self.smtp_port}")
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.email_address, self.app_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_address}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed. Check email and app password.")
            return False
        except smtplib.SMTPRecipientsRefused:
            logger.error(f"Recipient refused: {to_address}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return False

    def save_draft(
        self,
        to_address: str,
        subject: str,
        body: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> bool:
        """
        Save an email as a draft in Gmail's Drafts folder.
        Uses IMAP APPEND to add the message to [Gmail]/Drafts.

        Args:
            to_address: Recipient email
            subject: Email subject
            body: Email body text
            in_reply_to: Message-ID for threading
            references: References header for threading

        Returns:
            True if draft saved successfully
        """
        imap_connection = None
        try:
            # Build the email message
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to_address
            msg["Subject"] = subject

            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                if references:
                    msg["References"] = f"{references} {in_reply_to}"
                else:
                    msg["References"] = in_reply_to

            msg.attach(MIMEText(body, "plain"))

            # Connect and save to Drafts
            imap_connection = self._connect_imap()

            # Gmail's draft folder
            draft_folder = "[Gmail]/Drafts"

            # APPEND the message to drafts
            date_time = imaplib.Time2Internaldate(_time.time())

            result = imap_connection.append(
                draft_folder,
                "",  # No flags
                date_time,
                msg.as_bytes(),
            )

            if result[0] == "OK":
                logger.info("Draft saved to Gmail Drafts folder")
                return True
            else:
                logger.warning(f"Failed to save draft: {result}")
                return False

        except Exception as e:
            logger.error(f"Error saving draft: {e}")
            return False
        finally:
            if imap_connection:
                try:
                    imap_connection.logout()
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # ARCHIVE EMAILS (IMAP)
    # ──────────────────────────────────────────────

    def archive_email(self, email_id: str, mailbox: str = "INBOX") -> bool:
        """
        Archive an email by removing it from inbox.
        In Gmail, archiving = removing the INBOX label.
        Simpler approach: just mark as read, which is good enough for demo.

        Args:
            email_id: IMAP message ID
            mailbox: Current mailbox of the email

        Returns:
            True if archived successfully, False otherwise
        """
        imap_connection = None
        try:
            imap_connection = self._connect_imap()
            imap_connection.select(mailbox)

            # Mark the email as read (removes from "unread" count)
            status, _ = imap_connection.store(email_id.encode(), "+FLAGS", "\\Seen")
            if status == "OK":
                logger.info(f"Email {email_id} marked as read (archived)")
                return True
            else:
                logger.warning(f"Failed to archive email {email_id}")
                return False

        except Exception as e:
            logger.error(f"Error archiving email: {e}")
            return False
        finally:
            if imap_connection:
                try:
                    imap_connection.close()
                    imap_connection.logout()
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # FLAG EMAILS (IMAP)
    # ──────────────────────────────────────────────

    def flag_email(self, email_id: str, mailbox: str = "INBOX") -> bool:
        """
        Flag/star an email in Gmail.

        Args:
            email_id: IMAP message ID
            mailbox: Current mailbox of the email

        Returns:
            True if flagged successfully, False otherwise
        """
        imap_connection = None
        try:
            imap_connection = self._connect_imap()
            imap_connection.select(mailbox)

            status, _ = imap_connection.store(email_id.encode(), "+FLAGS", "\\Flagged")
            if status == "OK":
                logger.info(f"Email {email_id} flagged/starred")
                return True
            else:
                logger.warning(f"Failed to flag email {email_id}")
                return False

        except Exception as e:
            logger.error(f"Error flagging email: {e}")
            return False
        finally:
            if imap_connection:
                try:
                    imap_connection.close()
                    imap_connection.logout()
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # UTILITY METHODS
    # ──────────────────────────────────────────────

    def test_connection(self) -> dict:
        """
        Test both IMAP and SMTP connections.
        Useful for verifying credentials during setup.

        Returns:
            dict with "imap" and "smtp" status (True/False)
        """
        result = {"imap": False, "smtp": False}

        # Test IMAP
        try:
            connection = self._connect_imap()
            connection.select("INBOX")
            connection.close()
            connection.logout()
            result["imap"] = True
            logger.info("[OK] IMAP connection successful")

        except Exception as e:
            error_msg = str(e)
            if (
                "[AUTHENTICATIONFAILED]" in error_msg
                or "Invalid credentials" in error_msg
            ):
                logger.error("[FAILED] IMAP connection failed: Invalid Credentials")
                logger.error(
                    "HINT: You likely need a Google App Password, "
                    "not your login password."
                )
                logger.error("See: https://myaccount.google.com/apppasswords")
            else:
                logger.error(f"[FAILED] IMAP connection failed: {e}")

        # Test SMTP
        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.email_address, self.app_password)
            result["smtp"] = True
            logger.info("[OK] SMTP connection successful")

        except Exception as e:
            error_msg = str(e)
            if (
                "Username and Password not accepted" in error_msg
                or "5.7.8" in error_msg
            ):
                logger.error("[FAILED] SMTP connection failed: Invalid Credentials")
            else:
                logger.error(f"[FAILED] SMTP connection failed: {e}")

        return result

    @staticmethod
    def extract_email_address(from_field: str) -> str:
        """
        Extract clean email address from the From field.

        "John Doe <john@company.com>" -> "john@company.com"
        "john@company.com" -> "john@company.com"
        """
        _, email_addr = parseaddr(from_field)
        return email_addr if email_addr else from_field

    @staticmethod
    def make_reply_subject(original_subject: str) -> str:
        """
        Create a reply subject line.

        "Meeting Friday" -> "Re: Meeting Friday"
        "Re: Meeting Friday" -> "Re: Meeting Friday" (don't double up)
        """
        if original_subject.lower().startswith("re:"):
            return original_subject
        return f"Re: {original_subject}"
