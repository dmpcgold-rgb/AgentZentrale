"""Gmail confirmation evidence, tested entirely offline with synthetic mail."""
import unittest
from email.message import EmailMessage
from datetime import date
from unittest.mock import patch
from gmail_ticket_confirmation import match_ticket, confirm_from_gmail


def receipt(*, sender="WESTbahn <service@westbahn.at>", day="Fr 20 Nov",
            time="18:22", train="1009", seat="191D", pdf=True,
            subject="Ihr Westbahn-Ticket"):
    message=EmailMessage()
    message["From"]=sender
    message["Date"]="Thu, 19 Nov 2026 19:26:42 +0100"
    message["Subject"]=subject
    message.set_content(f"""Vielen Dank für Ihre Buchung!
    2+ | Reservierung Comfort Class
    Abfahrt {time} {day}
    Ankunft 18:49
    W. Meidling Wr. Neustadt
    Zug {train}
    Wagen 8
    Sitz {seat}
    Ticket Nummer 136-0000-0000
    Im Anhang finden Sie Ihr Ticket als PDF-Datei.""")
    if pdf:
        message.add_attachment(b"%PDF-1.4 synthetic",maintype="application",
                               subtype="pdf",filename="Westbahn-Ticket.pdf")
    return message


class MailMatchingOffline(unittest.TestCase):
    def match(self, message):
        return match_ticket(message,date(2026,11,20),"191D","1009")
    def test_exact_realistic_receipt(self):
        self.assertTrue(self.match(receipt()))
    def test_wrong_sender_denied(self):
        self.assertFalse(self.match(receipt(sender="WESTbahn <help@fake-westbahn.at>")))
    def test_wrong_date_train_seat_denied(self):
        self.assertFalse(self.match(receipt(day="Fr 27 Nov")))
        self.assertFalse(self.match(receipt(train="1010")))
        self.assertFalse(self.match(receipt(seat="233A")))
    def test_wrong_email_type_denied(self):
        self.assertFalse(self.match(receipt(subject="WESTbahn Angebote")))
    def test_no_credentials_never_confirms(self):
        with patch.dict("os.environ",{},clear=True):
            value=confirm_from_gmail(date(2026,11,20),"191D","1009")
        self.assertEqual(value["status"],"email_not_configured")
        self.assertFalse(value["ticketConfirmed"])
    def test_confirmation_helper_never_writes_mail(self):
        import inspect, gmail_ticket_confirmation as mod
        source=inspect.getsource(mod)
        self.assertIn('readonly=True',source)
        self.assertIn('BODY.PEEK[]',source)
        self.assertNotIn('mail.store(',source)
        self.assertNotIn('mail.expunge(',source)
        self.assertNotIn('mail.uid("STORE"',source)


if __name__=="__main__":
    unittest.main()
