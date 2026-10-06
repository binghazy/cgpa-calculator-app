import json
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

from gemini_client import DEFAULT_MODEL, GeminiError, generate_content, explain_error
from cgpa_calculator import generate_ai_reply, normalize_api_key


class GeminiTests(unittest.TestCase):
    def response(self, body):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(body).encode()
        return response

    def test_native_request_keeps_key_out_of_url_and_reads_text(self):
        response = self.response({"candidates": [{"content": {"parts": [
            {"text": "internal", "thought": True}, {"text": "Hello"}, {"text": "world"}]}, "finishReason": "STOP"}]})
        contents = [{"role": "user", "parts": [{"text": "Hi"}]}]
        with patch("gemini_client.urllib.request.urlopen", return_value=response) as call:
            self.assertEqual(generate_content("test-key", DEFAULT_MODEL, contents, "Be helpful"), "Hello\nworld")
        request = call.call_args.args[0]
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertNotIn("test-key", request.full_url)
        self.assertIn(":generateContent", request.full_url)
        payload = json.loads(request.data)
        self.assertEqual(payload["contents"], contents)
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "Be helpful")

    def test_followup_includes_conversation_and_latest_record(self):
        history = [{"user": "First", "assistant": "Reply"},
                   {"user": "Failed", "assistant": "", "error": "network"}]
        with patch("cgpa_calculator.generate_content", return_value="Next") as call:
            self.assertEqual(generate_ai_reply("Follow up", [], "test-key", history=history), "Next")
        contents = call.call_args.args[2]
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[-1]["parts"][0]["text"], "Follow up")
        self.assertIn("CURRENT academic record", call.call_args.args[3])

    def test_history_is_bounded(self):
        history = [{"user": str(i), "assistant": "reply"} for i in range(20)]
        with patch("cgpa_calculator.generate_content", return_value="OK") as call:
            generate_ai_reply("Now", [], "test-key", history=history)
        self.assertEqual(len(call.call_args.args[2]), 25)

    def test_bad_key_and_model_fail_before_network(self):
        with patch("gemini_client.urllib.request.urlopen") as call:
            for key, model in [("bad\nkey", DEFAULT_MODEL), ("key", "unknown")]:
                with self.assertRaises(GeminiError):
                    generate_content(key, model, [])
            call.assert_not_called()

    def test_errors_are_actionable_without_raw_body_or_retry(self):
        for status, expected in [(400, "rejected"), (401, "authenticate"), (403, "denied"),
                                 (404, "unavailable"), (429, "quota"), (503, "temporarily")]:
            error = urllib.error.HTTPError("https://example.com", status, "error", {}, BytesIO(b"secret"))
            with patch("gemini_client.urllib.request.urlopen", side_effect=error) as call:
                with self.assertRaises(GeminiError) as captured:
                    generate_content("key", DEFAULT_MODEL, [])
            message = explain_error(captured.exception, DEFAULT_MODEL)
            self.assertIn(expected, message)
            self.assertNotIn("secret", message)
            self.assertEqual(call.call_count, 1)

    def test_invalid_api_key_reason_from_google(self):
        body = {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}
        error = urllib.error.HTTPError("https://example.com", 400, "error", {}, BytesIO(json.dumps(body).encode()))
        with patch("gemini_client.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(GeminiError) as captured:
                generate_content("key", DEFAULT_MODEL, [])
        self.assertIn("authenticate", explain_error(captured.exception, DEFAULT_MODEL))

    def test_empty_blocked_and_malformed_responses(self):
        for body in [None, {}, {"candidates": []}, {"promptFeedback": {"blockReason": "SAFETY"}},
                     {"candidates": [{"finishReason": "SAFETY"}]}]:
            with patch("gemini_client.urllib.request.urlopen", return_value=self.response(body)):
                with self.assertRaises(GeminiError):
                    generate_content("key", DEFAULT_MODEL, [])

    def test_truncated_response_is_labeled(self):
        body = {"candidates": [{"content": {"parts": [{"text": "Partial"}]}, "finishReason": "MAX_TOKENS"}]}
        with patch("gemini_client.urllib.request.urlopen", return_value=self.response(body)):
            self.assertIn("length limit", generate_content("key", DEFAULT_MODEL, []))

    def test_pasted_env_assignment(self):
        self.assertEqual(normalize_api_key('GEMINI_API_KEY="test-key"'), "test-key")

    def test_authorization_key_with_period_is_sent_unchanged(self):
        key = "AQ.synthetic.authorization-key_for_test"
        response = self.response({"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
        with patch("gemini_client.urllib.request.urlopen", return_value=response) as call:
            self.assertEqual(generate_content(key, DEFAULT_MODEL, []), "OK")
        self.assertEqual(call.call_args.args[0].get_header("X-goog-api-key"), key)

    def test_local_format_errors_do_not_blame_google(self):
        with patch("gemini_client.urllib.request.urlopen") as call:
            for key in ["bad\nkey", "two keys", "bad\x00key"]:
                with self.assertRaises(GeminiError) as captured:
                    generate_content(key, DEFAULT_MODEL, [])
                self.assertEqual(captured.exception.code, "local_key_format")
                self.assertIn("No request was sent", explain_error(captured.exception, DEFAULT_MODEL))
            call.assert_not_called()

    def test_paste_cleanup_preserves_credential_characters(self):
        for value in ['  “AQ.test-key_123”  ', '\ufeffGEMINI_API_KEY="AQ.test-key_123"',
                      "export GOOGLE_API_KEY='AQ.test-key_123'", '$env:GEMINI_API_KEY = "AQ.test-key_123"',
                      r'`AQ.test-key\_123`']:
            self.assertEqual(normalize_api_key(value), "AQ.test-key_123")

    def test_expired_and_restricted_keys_get_specific_guidance(self):
        for code, expected in [("API_KEY_EXPIRED", "expired"), ("API_KEY_SERVICE_BLOCKED", "API restrictions"),
                               ("API_KEY_HTTP_REFERRER_BLOCKED", "server")]:
            error = GeminiError("rejected", 403, code)
            self.assertIn(expected, explain_error(error, DEFAULT_MODEL))

    def test_windows_network_block_is_not_key_failure(self):
        error = urllib.error.URLError("[WinError 10013] Socket access forbidden")
        with patch("gemini_client.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(GeminiError) as captured:
                generate_content("test-key", DEFAULT_MODEL, [])
        self.assertEqual(captured.exception.code, "network_blocked")
        self.assertIn("key was not checked", explain_error(captured.exception, DEFAULT_MODEL))


if __name__ == "__main__":
    unittest.main()
