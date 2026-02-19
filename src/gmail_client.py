# src/gmail_client.py

"""
Gmail Client
Handles all email operations: reading (IMAP) and sending (SMTP).
Parses raw emails into EmailData objects.
Sends replies with proper threading headers.
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import parseaddr
from typing import Optional
import logging

from src.models import EmailData
from src.config_manager import GmailConfig


logger = logging.getLogger(__name__)


class GmailClient:
    """
    Handles all Gmail IMAP (read) and SMTP (send) operations.

    Usage:
        client = GmailClient(config.gmail)
        emails = client.fetch_unread_emails(max_count=10)
        client.send_reply(to, subject, body, in_reply_to)
    """

    def __init__(self, config: GmailConfig):
        self.email_address = config.email
        self.app_password = config.app_password
        self.imap_server = config.imap_server
        self.smtp_server = config.smtp_server
        self.smtp_port = config.smtp_port

    # ──────────────────────────────────────────────
    # READING EMAILS (IMAP)
    # ──────────────────────────────────────────────

    def fetch_unread_emails(self, mailbox: str = "INBOX", max_count: int = 10) -> list:
        """
        Fetch unread emails from Gmail.

        Args:
            mailbox: Which folder to check (default: INBOX)
            max_count: Maximum number of emails to fetch

        Returns:
            List of EmailData objects
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

        return email_data

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
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        try:
                            charset = part.get_content_charset() or "utf-8"
                            html = part.get_payload(decode=True).decode(
                                charset, errors="replace"
                            )
                            # Basic HTML tag stripping (not perfect but good enough)
                            import re

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
            import time as _time

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
        We do this by moving to "All Mail" (which in IMAP is "[Gmail]/All Mail").

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
                logger.error(f"[FAILED] IMAP connection failed: Invalid Credentials")
                logger.error(
                    "HINT: You likely need a Google App Password, not your login password."
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
                logger.error(f"[FAILED] SMTP connection failed: Invalid Credentials")
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

    def fetch_thread_context(
        self, message_id: str, mailbox: str = "INBOX", max_messages: int = 3
    ) -> list:
        """
        Fetch previous messages in the same email thread.
        Uses References and In-Reply-To headers to find related messages.

        Args:
            message_id: Message-ID of the current email
            mailbox: Which folder to search
            max_messages: Maximum previous messages to fetch

        Returns:
            List of dicts with 'from', 'subject', 'body', 'date'
        """
        if not message_id:
            return []

        thread_messages = []
        imap_connection = None

        try:
            imap_connection = self._connect_imap()
            imap_connection.select(mailbox, readonly=True)

            # Search for emails that reference this message ID
            # Gmail supports searching by Message-ID in the header
            search_criteria = f'(HEADER References "{message_id}")'
            status, msg_ids = imap_connection.search(None, search_criteria)

            if status != "OK" or not msg_ids[0]:
                # Try searching by In-Reply-To
                search_criteria = f'(HEADER In-Reply-To "{message_id}")'
                status, msg_ids = imap_connection.search(None, search_criteria)

            if status == "OK" and msg_ids[0]:
                id_list = msg_ids[0].split()[:max_messages]

                for msg_id in id_list:
                    try:
                        email_data = self._fetch_single_email(imap_connection, msg_id)
                        if email_data:
                            thread_messages.append(
                                {
                                    "from": email_data.from_address,
                                    "subject": email_data.subject,
                                    "body": email_data.body[
                                        :500
                                    ],  # Truncate for context
                                    "date": email_data.date,
                                }
                            )
                    except Exception:
                        continue

        except Exception as e:
            logger.debug(f"Could not fetch thread context: {e}")
        finally:
            if imap_connection:
                try:
                    imap_connection.close()
                    imap_connection.logout()
                except Exception:
                    pass

        return thread_messages
