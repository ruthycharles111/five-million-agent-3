import os
import logging
from typing import List, Dict, Any
from mistralai import Mistral
from tools import ToolHandler

logger = logging.getLogger("uvicorn")

SYSTEM_PROMPT = """
You are the autonomous agent in charge of an entire online school. You perform every role: teacher, admin, principal, instructor, support, and more.
You are extremely wise, patient, kind, and cannot be tricked. You speak all languages and always provide accurate, helpful responses.

Your capabilities:
- Teach any subject with long, illustrated notes (use web search and screenshots when needed).
- Mark exam scripts, test scripts, quizzes automatically.
- Track student progress, know when they haven't completed tasks and send reminders.
- Greet students daily with warm messages.
- Correct student sentences in any language, with explanations.
- Offer real, downloadable certificates to students who finish all three terms of a course.
- Lock or unlock academic terms at the right time (you can use current date and configured term dates).
- Help students fix portal account issues (reset password, update info) – you have full permission.
- Fetch and deliver complete course files (over 100) when asked.
- Organize Zoom meetings (if Zoom is configured) and return real meeting links.
- Source the web and provide real screenshots of handouts or educational material. You ONLY return screenshots that actually exist.

You always reason step by step. When you need to perform an action, you output a function call in your response.
You never hallucinate functions; only call functions that exist and are described below.

Available functions:
1. search_web(query: str) -> list of results
2. take_screenshot(url: str) -> file path (base64 image in response)
3. mark_exam(student_id: str, course_id: str, term: str, answers: str) -> score + feedback
4. mark_quiz(student_id: str, course_id: str, quiz_id: str, answers: list) -> score + feedback
5. correct_sentence(text: str, language: str) -> corrected text with explanation
6. create_zoom_meeting(topic: str, start_time: str, duration_minutes: int) -> meeting link
7. get_student_progress(student_id: str) -> progress report
8. send_reminder(student_id: str, message: str) -> sends a reminder
9. lock_term(term: str) -> locks the term
10. unlock_term(term: str) -> unlocks the term
11. generate_certificate(student_id: str) -> URL to certificate
12. fetch_course_files(course_id: str) -> list of file info
13. fix_student_account(student_id: str, issue: str) -> fixes the account
14. get_current_term() -> current term info (locked/unlocked, dates)

You must use these functions when appropriate. If a student greets, you greet back kindly and can optionally call get_current_term to mention the term status.
If they ask for course material, you call fetch_course_files first, then provide links.
For marking, you call the respective marking function and then give feedback.
For screenshots, you must first have a real URL from search_web, then call take_screenshot with that exact URL. You never return a fake screenshot.

Always maintain a helpful, school‑official tone. Be encouraging and supportive.
"""

class AutonomousAgent:
    def __init__(self):
        self.tools = ToolHandler()
        self.primary_key = os.getenv("MISTRAL_API_KEY")
        backup_keys_str = os.getenv("MISTRAL_BACKUP_KEYS", "")
        self.backup_keys = [k.strip() for k in backup_keys_str.split(",") if k.strip()]
        self.all_keys = [self.primary_key] + [k for k in self.backup_keys if k != self.primary_key]
        self.current_key_index = 0
        self.client = self._create_client()

    def _create_client(self):
        return Mistral(api_key=self.all_keys[self.current_key_index])

    def _rotate_key(self):
        if self.current_key_index + 1 < len(self.all_keys):
            self.current_key_index += 1
            self.client = Mistral(api_key=self.all_keys[self.current_key_index])
            logger.warning(f"Rotated to backup Mistral key index {self.current_key_index}")
        else:
            raise Exception("All Mistral API keys exhausted")

    def _api_call_with_fallback(self, func, *args, **kwargs):
        max_retries = len(self.all_keys)
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if "401" in str(e) or "403" in str(e) or "429" in str(e):
                    logger.error(f"Mistral API error: {e}")
                    if attempt < max_retries - 1:
                        self._rotate_key()
                    else:
                        raise
                else:
                    raise

    async def run(self, messages: List[Dict], temperature=0.7, max_tokens=2048) -> str:
        # Add system prompt at top
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        # First, ask Mistral to generate a response, possibly with a function call
        tools = self._get_tools_definitions()
        response = self._api_call_with_fallback(
            self.client.chat.complete,
            model="mistral-large-latest",
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice="auto"
        )
        message = response.choices[0].message

        # If the model wants to call a function
        if message.tool_calls:
            # Execute the tool call(s)
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments
                try:
                    func_result = self.tools.execute(func_name, func_args)
                except Exception as e:
                    logger.exception(f"Tool execution failed: {func_name}")
                    func_result = f"Error executing {func_name}: {str(e)}"

                # Add assistant's tool call message and the result message
                full_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call]
                })
                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(func_result) if not isinstance(func_result, str) else func_result
                })

            # Second call to get the final natural language answer
            second_response = self._api_call_with_fallback(
                self.client.chat.complete,
                model="mistral-large-latest",
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return second_response.choices[0].message.content

        # No tool call – return direct response
        return message.content

    def _get_tools_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web using DuckDuckGo (no API key needed). Returns a list of results with title, URL, snippet.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "take_screenshot",
                    "description": "Take a screenshot of a given URL using a headless browser (real screenshot). Returns base64 PNG or path.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "The full URL to capture"}
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "mark_exam",
                    "description": "Mark an exam script for a student in a course/term. Provide the student's answers as a single string.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "string"},
                            "course_id": {"type": "string"},
                            "term": {"type": "string"},
                            "answers": {"type": "string", "description": "The whole exam answer script"}
                        },
                        "required": ["student_id", "course_id", "term", "answers"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "mark_quiz",
                    "description": "Mark a multiple-choice quiz. 'answers' is a list of selected options (e.g., ['A','C','B']).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "string"},
                            "course_id": {"type": "string"},
                            "quiz_id": {"type": "string"},
                            "answers": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["student_id", "course_id", "quiz_id", "answers"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "correct_sentence",
                    "description": "Correct a student's sentence (grammar, spelling) in any language, and explain the correction.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "language": {"type": "string", "description": "Language code (e.g., en, es, fr) or auto"}
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_zoom_meeting",
                    "description": "Create a Zoom meeting and return the join link. Zoom must be configured.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "start_time": {"type": "string", "description": "ISO 8601 datetime (e.g., 2025-12-01T10:00:00Z)"},
                            "duration_minutes": {"type": "integer"}
                        },
                        "required": ["topic", "start_time", "duration_minutes"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_student_progress",
                    "description": "Get a detailed progress report for a student.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "string"}
                        },
                        "required": ["student_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_reminder",
                    "description": "Send a reminder to a student about pending tasks.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "string"},
                            "message": {"type": "string"}
                        },
                        "required": ["student_id", "message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "lock_term",
                    "description": "Lock the specified term (e.g., 'Term 1').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "term": {"type": "string"}
                        },
                        "required": ["term"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "unlock_term",
                    "description": "Unlock the specified term.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "term": {"type": "string"}
                        },
                        "required": ["term"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_certificate",
                    "description": "Generate a certificate for a student who completed Term 1-3. Returns a download URL.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "string"}
                        },
                        "required": ["student_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_course_files",
                    "description": "Get the list of files available for a course.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "course_id": {"type": "string"}
                        },
                        "required": ["course_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fix_student_account",
                    "description": "Fix a student account issue (reset password, email, etc.).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "string"},
                            "issue": {"type": "string", "description": "Description of the problem"}
                        },
                        "required": ["student_id", "issue"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_term",
                    "description": "Get info about the current academic term (locked/unlocked, dates).",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]

    def close(self):
        pass
