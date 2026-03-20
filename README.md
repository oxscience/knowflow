# KnowFlow

**Knowledge management system with Kanban boards, notes, and email delegation.**

A self-hosted tool for managing tasks, notes, and team coordination — designed around the idea that email is the best delegation channel.

## Features

- **Kanban Board**: Drag-and-drop task management with status columns
- **Task List View**: Filterable, searchable task list with categories and priorities
- **Notes & Wiki**: Markdown-based notes with linking and graph visualization
- **Email Delegation**: Delegate tasks to team members via email (SMTP/IMAP)
- **AI Extraction**: Extract tasks and action items from text using LLM (via langextract)
- **Multi-Instance**: Run multiple instances on different ports for separate workspaces
- **Category System**: Organize tasks and notes with custom categories
- **Search**: Full-text search across tasks and notes

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask 3.1 |
| Frontend | HTMX, Tailwind CSS |
| Database | SQLite |
| Scheduler | schedule (Python) |
| AI | langextract |

## Quick Start

```bash
git clone https://github.com/oxscience/knowflow.git
cd knowflow
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5001`.

## Multi-Instance

Run a second instance with a separate database:

```bash
INSTANCE_NAME=work PORT=5002 python app.py
```

## License

MIT
