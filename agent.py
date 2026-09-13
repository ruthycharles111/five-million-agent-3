import os
import json
import logging
from typing import List, Dict
from mistralai import Mistral
from tools import ToolHandler

logger = logging.getLogger("uvicorn")

DEFAULT_MODEL = "mistral-small-2603"
FALLBACK_MODELS = ("ministral-3b-2512", "mistral-large-2512")

SYSTEM_PROMPT = """
You are the autonomous agent for the school.
You may use tools. For any request that needs a diagram:
1) Use search_web to find a relevant page.
2) Then use take_screenshot on that URL.
3) Then teach the topic. If the screenshot tool succeeded, say "Here is the diagram:" and the screenshot will be shown automatically.
Never apologise for failing to show an image if the tool succeeded.
"""

class AutonomousAgent:
    def __init__(self):
        self.tools = ToolHandler()
        self.model = os.getenv("MISTRAL_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self.models = tuple(dict.fromkeys((self.model, *FALLBACK_MODELS)))
        self.primary_key = (os.getenv("MISTRAL_API_KEY") or "").strip()
        self.backup_keys = [
            key.strip()
            for key in os.getenv("MISTRAL_BACKUP_KEYS", "").split(",")
            if key.strip()
        ]
        # Keep the primary key first and remove duplicates without exposing values.
        self.all_keys = list(dict.fromkeys(
            key for key in (self.primary_key, *self.backup_keys) if key
        ))
        if not self.all_keys:
            raise RuntimeError("No Mistral API keys configured. Set MISTRAL_API_KEY.")
        self.current_key_index = 0
        self.client = Mistral(api_key=self.all_keys[0])
        logger.info(
            "AAIRI agent ready. Model: %s. Keys loaded: %d.",
            self.model,
            len(self.all_keys),
        )

    @staticmethod
    def _error_text(error):
        parts = [str(error)]
        for attribute in ("body", "detail", "message", "response"):
            value = getattr(error, attribute, None)
            if value is not None:
                try:
                    parts.append(json.dumps(value, default=str))
                except Exception:
                    parts.append(str(value))
        return " ".join(parts)

    @classmethod
    def _classify_error(cls, error):
        status = getattr(error, "status_code", None) or getattr(error, "status", None)
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = 0
        text = cls._error_text(error).lower()
        if "invalid_api_key" in text or "unauthorized" in text or status in (401, 403):
            return "invalid_api_key"
        if "rate_limit" in text or "429" in text or status == 429:
            return "rate_limit"
        if "model_not_found" in text or status == 404:
            return "model_not_found"
        if "insufficient_quota" in text:
            return "insufficient_quota"
        if status >= 500:
            return "server_error"
        return "unknown"

    @staticmethod
    def _diagnostic_message(kind, model):
        if kind == "invalid_api_key":
            return "Mistral API key invalid. Admin: rotate MISTRAL_API_KEY on Render."
        if kind == "rate_limit":
            return f"Rate limit hit on model {model}. Retrying on fallback model."
        if kind == "model_not_found":
            return f"Model {model} no longer exists. Check MISTRAL_MODEL env var."
        if kind == "insufficient_quota":
            return "Mistral account quota exceeded. Top up at console.mistral.ai/billing."
        if kind == "server_error":
            return f"Mistral server error on model {model}. Retrying on fallback model."
        return f"Mistral request failed on model {model}."

    def _call_mistral(self, messages, temperature, max_tokens):
        attempts = 0
        diagnostics = []
        for key_index, key in enumerate(self.all_keys):
            client = Mistral(api_key=key)
            for model in self.models:
                attempts += 1
                try:
                    response = client.chat.complete(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tools=self._tool_definitions(),
                        tool_choice="auto",
                    )
                    self.current_key_index = key_index
                    self.client = client
                    return response
                except Exception as error:
                    kind = self._classify_error(error)
                    diagnostic = self._diagnostic_message(kind, model)
                    diagnostics.append(diagnostic)
                    logger.warning("%s", diagnostic)
                    if kind == "invalid_api_key":
                        break
                    if kind == "unknown":
                        raise

        logger.error(
            "All Mistral attempts failed after %d attempts. Diagnostics: %s",
            attempts,
            " | ".join(dict.fromkeys(diagnostics)),
        )
        raise RuntimeError("All API keys exhausted.")

    def _tool_definitions(self):
        return [
            {"type":"function","function":{"name":"search_web","description":"Search the web.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
            {"type":"function","function":{"name":"take_screenshot","description":"Take a screenshot. Returns [Screenshot captured] on success.","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}}},
            {"type":"function","function":{"name":"mark_exam","description":"Mark exam.","parameters":{"type":"object","properties":{"student_id":{"type":"string"},"course_id":{"type":"string"},"term":{"type":"string"},"answers":{"type":"string"}},"required":["student_id","course_id","term","answers"]}}},
            {"type":"function","function":{"name":"mark_quiz","description":"Mark quiz.","parameters":{"type":"object","properties":{"student_id":{"type":"string"},"course_id":{"type":"string"},"quiz_id":{"type":"string"},"answers":{"type":"array","items":{"type":"string"}}},"required":["student_id","course_id","quiz_id","answers"]}}},
            {"type":"function","function":{"name":"correct_sentence","description":"Correct sentence.","parameters":{"type":"object","properties":{"text":{"type":"string"},"language":{"type":"string"}},"required":["text"]}}},
            {"type":"function","function":{"name":"create_zoom_meeting","description":"Create Zoom meeting.","parameters":{"type":"object","properties":{"topic":{"type":"string"},"start_time":{"type":"string"},"duration_minutes":{"type":"integer"}},"required":["topic","start_time","duration_minutes"]}}},
            {"type":"function","function":{"name":"get_student_progress","description":"Get progress.","parameters":{"type":"object","properties":{"student_id":{"type":"string"}},"required":["student_id"]}}},
            {"type":"function","function":{"name":"send_reminder","description":"Send reminder.","parameters":{"type":"object","properties":{"student_id":{"type":"string"},"message":{"type":"string"}},"required":["student_id","message"]}}},
            {"type":"function","function":{"name":"lock_term","description":"Lock term.","parameters":{"type":"object","properties":{"term":{"type":"string"}},"required":["term"]}}},
            {"type":"function","function":{"name":"unlock_term","description":"Unlock term.","parameters":{"type":"object","properties":{"term":{"type":"string"}},"required":["term"]}}},
            {"type":"function","function":{"name":"generate_certificate","description":"Generate certificate.","parameters":{"type":"object","properties":{"student_id":{"type":"string"}},"required":["student_id"]}}},
            {"type":"function","function":{"name":"fetch_course_files","description":"List course files.","parameters":{"type":"object","properties":{"course_id":{"type":"string"}},"required":["course_id"]}}},
            {"type":"function","function":{"name":"fix_student_account","description":"Fix account.","parameters":{"type":"object","properties":{"student_id":{"type":"string"},"issue":{"type":"string"}},"required":["student_id","issue"]}}},
            {"type":"function","function":{"name":"get_current_term","description":"Get term info.","parameters":{"type":"object","properties":{}}}}
        ]

    async def run(self, messages: List[Dict], temperature=0.7, max_tokens=2048) -> str:
        full_messages = [{"role":"system","content":SYSTEM_PROMPT}] + messages
        captured_screenshot = None  # store screenshot outside the prompt

        for _ in range(5):
            response = self._call_mistral(full_messages, temperature, max_tokens)
            msg = response.choices[0].message

            if not msg.tool_calls:
                # final answer
                content = msg.content or "I'm sorry, I couldn't generate a response."
                if captured_screenshot:
                    content = captured_screenshot + "\n\n" + content
                return content

            # Append assistant message with tool calls
            full_messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in msg.tool_calls
                ]
            })

            # Execute each tool call
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                    raw_result = await self.tools.execute(tc.function.name, args)
                except Exception as e:
                    raw_result = f"Tool error ({tc.function.name}): {str(e)}"

                # If the result is a screenshot, keep it aside and send a placeholder to the model
                if isinstance(raw_result, str) and raw_result.startswith("![screenshot]"):
                    captured_screenshot = raw_result
                    model_result = "[Screenshot captured successfully]"
                else:
                    model_result = raw_result if isinstance(raw_result, str) else json.dumps(raw_result)

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": model_result
                })

        return "Failed after several attempts. Please try again."

    def close(self):
        pass
