import time

from imapclient import IMAPClient
from mailbender.llm.provider import Email
from mailbender.util.retry import retry
import email as email_lib


class ImapClient:
    def __init__(self, host, port, user, password, use_ssl=True,
                 drafts_folder="Drafts", sent_folder="Sent"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        self.drafts_folder = drafts_folder
        self.sent_folder = sent_folder

    @staticmethod
    def can_connect(host, port, user, password, use_ssl=False) -> bool:
        try:
            with IMAPClient(host, port=port, ssl=use_ssl) as c:
                c.login(user, password)
            return True
        except Exception:
            return False

    def _connect(self) -> IMAPClient:
        def do():
            client = IMAPClient(self.host, port=self.port, ssl=self.use_ssl)
            client.login(self.user, self.password)
            return client
        return retry(do, sleep=time.sleep)

    def fetch_inbox(self) -> list[Email]:
        return self.fetch_folder("INBOX")

    def fetch_folder(self, folder: str) -> list[Email]:
        out = []
        with self._connect() as c:
            c.select_folder(folder)
            uids = c.search(["ALL"])
            if not uids:
                return out
            for uid, data in c.fetch(uids, ["RFC822"]).items():
                msg = email_lib.message_from_bytes(data[b"RFC822"])
                out.append(self._to_email(uid, msg))
        return out

    def _to_email(self, uid, msg) -> Email:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="replace")
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors="replace")
        return Email(
            uid=str(uid),
            subject=msg.get("Subject", ""),
            sender=msg.get("From", ""),
            body=body,
            message_id=msg.get("Message-ID", ""),
            in_reply_to=msg.get("In-Reply-To", ""),
        )

    def append_draft(self, subject: str, body: str, folder: str | None = None):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.user
        msg.set_content(body)
        target = folder or self.drafts_folder
        with self._connect() as c:
            retry(lambda: c.append(target, msg.as_bytes()), sleep=time.sleep)

    def move(self, uid: str, target_folder: str, source_folder="INBOX"):
        with self._connect() as c:
            c.select_folder(source_folder)
            retry(lambda: c.move([int(uid)], target_folder), sleep=time.sleep)
