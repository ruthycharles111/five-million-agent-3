import os
import json
import logging
from typing import List, Dict
from mistralai import Mistral
from tools import ToolHandler

logger = logging.getLogger("uvicorn")

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
        self.primary_key = os.getenv("MISTRAL_API_KEY")
        self.backup_keys = [k.strip() for k in os.getenv("MISTRAL_BACKUP_KEYS","").split(",") if k.strip()]
        self.all_keys = [self.primary_key] + [k for k in self.backup_keys if k != self.primary_key]
        self.current_key_index = 0
        self.client = Mistral(api_key=self.all_keys[self.current_key_index])

    def _rotate_key(self):
        if self.current_key_index + 1 < len(self.all_keys):
            self.current_key_index += 1
            self.client = Mistral(api_key=self.all_keys[self.current_key_index])
        else:
            raise RuntimeError("All API keys exhausted")

    def _call_mistral(self, messages, temperature, max_tokens):
        for _ in range(len(self.all_keys)):
            try:
                return self.client.chat.complete(
                    model="mistral-large-latest",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=self._tool_definitions(),
                    tool_choice="auto"
                )
            except Exception as e:
                if any(x in str(e) for x in ("401","403","429")):
                    self._rotate_key()
                else:
                    raise

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
