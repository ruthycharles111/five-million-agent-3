# School Autonomous Agent

A fully autonomous AI agent that runs your entire online school: teaching, marking, reminders, certificates, Zoom meetings, screenshots, and more.

## Setup

1. Clone the repo.
2. Create a `.env` file from `.env.example` and fill in your Mistral API keys and (optionally) Zoom credentials.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
Run: uvicorn main:app --reload

Call the API at POST /v1/chat/completions with messages.

Course Files
Place your course materials in course_files/<course_id>/. Over 100 files supported.

Deployment to Render
Use the included render.yaml or connect your repo. Set environment variables as shown.

text

---

## How the School Platform Calls It

Your school website just sends a **POST request** to `https://your-agent.onrender.com/v1/chat/completions` with a JSON body like:

```json
{
  "messages": [
    {"role": "system", "content": "The student id is student123"},
    {"role": "user", "content": "I need help with my account login."}
  ]
}
The agent responds in the OpenAI chat format. It will automatically use the Mistral API, decide if it needs to call any tool (like fix_student_account), execute it, and return the final helpful response.

The agent is fully autonomous – it can:

Teach with long notes and real screenshots (search_web + take_screenshot)

Mark exams and quizzes

Send daily greetings and pending-work reminders (via your configured webhook)

Lock/unlock terms when you ask or on schedule

Generate real PDF certificates for students who complete all three terms

Create Zoom meetings (if you provide Zoom API keys, otherwise returns a placeholder)

Fix student account issues

Everything is self-contained: no external API keys are needed beyond your Mistral keys (the screenshots use Playwright, web search uses DuckDuckGo). The whole repository is ready to deploy.

