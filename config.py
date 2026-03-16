import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get('SECRET_KEY', 'knowflow-dev-key-change-in-production')
DATABASE = os.environ.get('KNOWFLOW_DB', os.path.join(BASE_DIR, 'knowflow.db'))
PORT = int(os.environ.get('KNOWFLOW_PORT', 5001))
INSTANCE_NAME = os.environ.get('KNOWFLOW_INSTANCE', 'default')
DEBUG = True

# Email configuration (Gmail)
EMAIL_IMAP_HOST = 'imap.gmail.com'
EMAIL_IMAP_PORT = 993
EMAIL_SMTP_HOST = 'smtp.gmail.com'
EMAIL_SMTP_PORT = 587
EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')

# Keywords that mark a delegated task as completed
DELEGATION_KEYWORDS = ['erledigt', 'done', 'fertig', 'completed', 'finished', 'abgeschlossen']

# Keywords in email subject that trigger task creation (case-insensitive)
TASK_KEYWORDS = ['[TASK]', '[TODO]']

# Schedule: automatic digest on Mondays at 09:00
DIGEST_DAY = 'monday'
DIGEST_TIME = '09:00'

# LLM / langextract configuration
# For Ollama (local): set LLM_MODEL_ID to an Ollama model (e.g. qwen2.5:7b)
# For Cloud API: set LLM_MODEL_ID to a cloud model + LLM_API_KEY
LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
LLM_MODEL_ID = os.environ.get('LLM_MODEL_ID', 'qwen2.5:7b')
LLM_MODEL_URL = os.environ.get('LLM_MODEL_URL', 'http://localhost:11434')
