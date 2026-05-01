import sys, os, logging
from dotenv import load_dotenv
load_dotenv()

# Add logging to file for debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('/tmp/agent.log'), logging.StreamHandler(sys.stderr)]
)

try:
    from main import app_fastapi
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app_fastapi, host="0.0.0.0", port=port, log_level="debug")
except Exception as e:
    logging.exception("Failed to start agent")
    sys.exit(1)
