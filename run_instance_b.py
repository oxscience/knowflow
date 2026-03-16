"""Run a second KnowFlow instance for sync testing."""
import os

# Override config BEFORE importing anything else
os.environ['KNOWFLOW_DB'] = os.path.join(os.path.dirname(__file__), 'knowflow_b.db')
os.environ['KNOWFLOW_PORT'] = '5002'
os.environ['KNOWFLOW_INSTANCE'] = 'instance-b'

from database import init_db
from app import create_app
import config

init_db()
app = create_app()
print(f'KnowFlow [{config.INSTANCE_NAME}] running at http://localhost:{config.PORT}')
print(f'Database: {config.DATABASE}')
app.run(debug=config.DEBUG, port=config.PORT)
