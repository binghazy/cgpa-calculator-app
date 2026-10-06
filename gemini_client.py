"""Google AI Studio text chat, using the native Gemini REST API."""
import json
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemini-3.1-flash-lite"
MODELS = {
    DEFAULT_MODEL: "Gemini 3.1 Flash-Lite",
    "gemini-3-flash-preview": "Gemini 3 Flash Preview",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash-Lite",
}


class GeminiError(RuntimeError):
    def __init__(self, message, status=None, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


def generate_content(api_key, model, contents, system_instruction=""):
    # Keys are opaque credentials, not a fixed alphabet or prefix. In particular,
    # authorization keys may contain periods. Reject only unsafe header values.
    if not api_key or any(ord(char) < 33 or ord(char) > 126 for char in api_key):
        raise GeminiError(
            "The key contains spaces, line breaks, or unsupported characters. "
            "Copy the complete key again. No request was sent to Google.", code="local_key_format")
    if model not in MODELS:
        raise GeminiError("Choose a supported Gemini model.", code="invalid_model")
    payload = {"contents": contents, "generationConfig": {"maxOutputTokens": 4096}}
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": "GhazyCGPAPlanner/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        code = ""
        try:
            error = json.loads(body).get("error", {})
            if isinstance(error, dict):
                code = str(error.get("status") or "")
                for detail in error.get("details", []):
                    if isinstance(detail, dict) and detail.get("reason") in {
                            "API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_SERVICE_BLOCKED",
                            "API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED", "SERVICE_DISABLED"}:
                        code = detail["reason"]
        except (ValueError, AttributeError, TypeError):
            pass
        raise GeminiError("Google rejected the request.", exc.code, code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if getattr(reason, "winerror", None) == 10013 or "WinError 10013" in str(reason):
            raise GeminiError(
                "Windows blocked this app's internet access. Your API key was not checked. "
                "Run the app from a normal terminal with network access, or allow Python through your firewall.",
                code="network_blocked") from exc
        raise GeminiError("Could not reach Gemini. Check your connection and try again.", code="network") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise GeminiError("Gemini returned an unreadable response. Please try again.") from exc
    try:
        if data.get("promptFeedback", {}).get("blockReason"):
            raise GeminiError("Gemini could not answer this question. Try rephrasing it.", code="blocked")
        candidate = data["candidates"][0]
        if candidate.get("finishReason") not in {None, "STOP", "MAX_TOKENS"}:
            raise GeminiError("Gemini could not complete this answer. Try rephrasing your question.", code="blocked")
        answer = "\n".join(part["text"] for part in candidate["content"]["parts"]
                           if isinstance(part.get("text"), str) and not part.get("thought")).strip()
        if not answer:
            raise ValueError("No text")
        if candidate.get("finishReason") == "MAX_TOKENS":
            answer += "\n\n_This answer reached the length limit. Ask me to continue._"
        return answer
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise GeminiError("Gemini returned no answer. Try again or select another model.") from exc


def explain_error(error, model):
    if not isinstance(error, GeminiError):
        return "The Gemini request failed. Please try again."
    if error.code == "local_key_format":
        return str(error)
    if error.code == "API_KEY_EXPIRED":
        return "Google reports that this key expired (API_KEY_EXPIRED). Create a replacement in Google AI Studio and paste it into Gemini settings."
    if error.code == "API_KEY_INVALID":
        return "Google could not authenticate the supplied key (API_KEY_INVALID). Copy the complete key from Google AI Studio, not its name or project ID, and test again."
    if error.code in {"API_KEY_SERVICE_BLOCKED", "SERVICE_DISABLED"}:
        return "Google blocked access to the Gemini API for this project/key. Check that the Generative Language API is enabled and allowed in the key's API restrictions."
    if error.code in {"API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED"}:
        return "Google blocked this app's request origin. This app calls Gemini from Python on the server; check that the key's application restrictions allow that server."
    if error.status == 401:
        return "Google could not authenticate the request (HTTP 401). Check the key's status and associated project in Google AI Studio, then test again."
    if error.status == 403:
        return "Google denied access. Check your API key restrictions, project permissions, and regional availability in AI Studio."
    if error.status == 429:
        return "Your Gemini quota or rate limit was reached. Check your free-tier limits in AI Studio, wait, then try again."
    if error.status == 404 or error.code == "invalid_model":
        return f"{model} is unavailable for this project. Select another Gemini model in the sidebar."
    if error.status == 400:
        return "Google rejected the request. Check your API key and whether the selected model's free tier is available for your project and region."
    if error.status and error.status >= 500:
        return "Gemini is temporarily unavailable. Please try again shortly."
    if error.status:
        return f"Google rejected the request (HTTP {error.status}). Check AI Studio and try again."
    return str(error)
