import unittest
import json
import logging
import io
from core.logging import redact_text, redact_data, StructuredLogFormatter, get_logger


class TestStructuredLogging(unittest.TestCase):
    def test_redact_tokens_and_secrets(self):
        text = "Bearer ya29.a0AfH6SMDh1234567890abcdef and api_key=AIzaSyD1234567890abcdef"
        redacted = redact_text(text)
        self.assertNotIn("ya29.a0AfH6SMDh1234567890abcdef", redacted)
        self.assertNotIn("AIzaSyD1234567890abcdef", redacted)
        self.assertIn("[REDACTED_TOKEN]", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)

    def test_redact_emails(self):
        text = "Contact founder at founder@example.com for private details."
        redacted = redact_text(text)
        self.assertNotIn("founder@example.com", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)

    def test_redact_structured_dict(self):
        data = {
            "user_id": "123",
            "email": "user@example.com",
            "cv_body": "Full private CV content with work history",
            "token": "secret_token_1234567890",
            "metadata": {
                "password": "supersecretpassword",
                "notes": "safe public note"
            }
        }
        redacted = redact_data(data)
        self.assertEqual(redacted["user_id"], "123")
        self.assertEqual(redacted["email"], "[REDACTED_EMAIL]")
        self.assertEqual(redacted["cv_body"], "[REDACTED_SENSITIVE_CONTENT]")
        self.assertEqual(redacted["token"], "[REDACTED_SENSITIVE_CONTENT]")
        self.assertEqual(redacted["metadata"]["password"], "[REDACTED_SENSITIVE_CONTENT]")
        self.assertEqual(redacted["metadata"]["notes"], "safe public note")

    def test_structured_log_formatter_output(self):
        formatter = StructuredLogFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="User login token=abcdef1234567890",
            args=(),
            exc_info=None
        )
        record.run_id = "RUN-1001"
        record.component = "AUTH"
        record.extra_data = {"email": "test@domain.com"}
        
        output = formatter.format(record)
        log_json = json.loads(output)
        
        self.assertEqual(log_json["level"], "INFO")
        self.assertEqual(log_json["logger"], "test_logger")
        self.assertEqual(log_json["run_id"], "RUN-1001")
        self.assertEqual(log_json["component"], "AUTH")
        self.assertIn("[REDACTED_TOKEN]", log_json["message"])
        self.assertEqual(log_json["data"]["email"], "[REDACTED_EMAIL]")


if __name__ == "__main__":
    unittest.main()
