import json
import logging
import smtplib
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


logger = logging.getLogger(__name__)


class BrevoEmailBackend(BaseEmailBackend):
    api_url = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not settings.BREVO_API_KEY:
            raise smtplib.SMTPException("Falta configurar BREVO_API_KEY.")

        sent_count = 0
        for message in email_messages:
            payload = self._build_payload(message)
            request = Request(
                self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "accept": "application/json",
                    "api-key": settings.BREVO_API_KEY,
                    "content-type": "application/json",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=20) as response:
                    if 200 <= response.status < 300:
                        sent_count += 1
                    else:
                        raise smtplib.SMTPException(
                            f"Brevo API devolvió HTTP {response.status}."
                        )
            except HTTPError as error:
                logger.error(
                    "Brevo API rechazó el correo (HTTP %s): %s",
                    error.code,
                    error.read().decode("utf-8", errors="replace")[:1000],
                )
                raise smtplib.SMTPException(
                    f"Brevo API rechazó el correo (HTTP {error.code})."
                ) from error
            except URLError as error:
                logger.exception("No se pudo conectar con Brevo API.")
                raise smtplib.SMTPException(
                    "No se pudo conectar con la API de Brevo."
                ) from error

        return sent_count

    @staticmethod
    def _build_payload(message):
        sender_name, sender_email = parseaddr(message.from_email)
        if not sender_email:
            raise smtplib.SMTPException("La dirección remitente no es válida.")

        payload = {
            "sender": {"email": sender_email},
            "to": [{"email": address} for address in message.recipients()],
            "subject": message.subject,
            "textContent": message.body,
        }
        if sender_name:
            payload["sender"]["name"] = sender_name

        reply_to = message.extra_headers.get("Reply-To")
        if reply_to:
            reply_name, reply_email = parseaddr(reply_to)
            if reply_email:
                payload["replyTo"] = {"email": reply_email}
                if reply_name:
                    payload["replyTo"]["name"] = reply_name

        html_alternative = next(
            (
                content
                for content, mimetype in getattr(message, "alternatives", [])
                if mimetype == "text/html"
            ),
            None,
        )
        if html_alternative:
            payload["htmlContent"] = html_alternative

        return payload
