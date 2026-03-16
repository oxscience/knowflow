import logging
import urllib.request
import langextract as lx
from langextract.data import ExampleData, Extraction
import config
from models import get_contacts, get_tags, get_all_notes

log = logging.getLogger(__name__)


def _ollama_reachable():
    """Check if Ollama server is running."""
    try:
        req = urllib.request.Request(config.LLM_MODEL_URL, method='HEAD')
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def _is_ollama_model():
    """Check if configured model looks like an Ollama model (contains ':')."""
    return ':' in config.LLM_MODEL_ID


def is_configured():
    if _is_ollama_model():
        return _ollama_reachable()
    return bool(config.LLM_API_KEY)


def _extract_kwargs():
    """Build common kwargs for lx.extract() — Ollama or cloud API."""
    kwargs = {'model_id': config.LLM_MODEL_ID}
    if _is_ollama_model():
        kwargs['model_url'] = config.LLM_MODEL_URL
    else:
        kwargs['api_key'] = config.LLM_API_KEY
    return kwargs


def extract_from_note(content, note_id=None):
    if not is_configured() or not content or not content.strip():
        return _empty_suggestions()

    suggestions = _empty_suggestions()

    try:
        suggestions['tasks'] = _extract_tasks(content)
    except Exception as e:
        log.error(f"Task extraction failed: {e}", exc_info=True)

    try:
        suggestions['contacts'] = _extract_contacts(content)
    except Exception as e:
        log.error(f"Contact extraction failed: {e}", exc_info=True)

    try:
        suggestions['tags'] = _extract_tags(content)
    except Exception as e:
        log.error(f"Tag extraction failed: {e}", exc_info=True)

    try:
        suggestions['related_notes'] = _find_related_notes(content, note_id)
    except Exception as e:
        log.error(f"Related notes failed: {e}", exc_info=True)

    return suggestions


def _empty_suggestions():
    return {'tasks': [], 'tags': [], 'contacts': [], 'related_notes': []}


def _get_extractions(result):
    """Get extractions from lx.extract() result, handling both return types."""
    # lx.extract returns AnnotatedDocument directly (has .extractions)
    if hasattr(result, 'extractions'):
        return result.extractions
    # Fallback: list of AnnotatedDocuments
    if isinstance(result, list):
        exts = []
        for doc in result:
            if hasattr(doc, 'extractions'):
                exts.extend(doc.extractions)
        return exts
    return []


def _get_offsets(ext):
    """Extract char offsets from an Extraction, handling different attribute names."""
    start = None
    end = None
    if hasattr(ext, 'char_interval') and ext.char_interval:
        start = getattr(ext.char_interval, 'start_pos', None)
        end = getattr(ext.char_interval, 'end_pos', None)
    if start is None:
        start = getattr(ext, 'start_offset', None)
    if end is None:
        end = getattr(ext, 'end_offset', None)
    return start, end


# --- Task Extraction ---

_TASK_PROMPT = """Extract action items, tasks, and to-dos from this text.
For each task, extract:
- task_title: A concise title for the action item — MUST be in the same language as the input text
- priority: "high", "medium", or "low" based on urgency cues
- due_date: ISO date string (YYYY-MM-DD) if a date is mentioned, otherwise empty
- assignee: Name of the person responsible, if mentioned, otherwise empty
IMPORTANT: Always output task_title in the same language as the source text.
"""

_TASK_EXAMPLES = [
    ExampleData(
        text="We need to finish the API documentation by Friday. Sarah should review the security section urgently. Also remember to update the README eventually.",
        extractions=[
            Extraction(
                extraction_class="task",
                extraction_text="finish the API documentation by Friday",
                attributes={
                    "task_title": "Finish API documentation",
                    "priority": "medium",
                    "due_date": "",
                    "assignee": ""
                }
            ),
            Extraction(
                extraction_class="task",
                extraction_text="Sarah should review the security section urgently",
                attributes={
                    "task_title": "Review security section",
                    "priority": "high",
                    "due_date": "",
                    "assignee": "Sarah"
                }
            ),
            Extraction(
                extraction_class="task",
                extraction_text="update the README eventually",
                attributes={
                    "task_title": "Update README",
                    "priority": "low",
                    "due_date": "",
                    "assignee": ""
                }
            ),
        ]
    ),
]


def _extract_tasks(content):
    result = lx.extract(
        text_or_documents=content,
        prompt_description=_TASK_PROMPT,
        examples=_TASK_EXAMPLES,
        **_extract_kwargs(),
    )
    tasks = []
    for ext in _get_extractions(result):
        if ext.extraction_class == "task":
            start, end = _get_offsets(ext)
            tasks.append({
                'title': ext.attributes.get('task_title', ext.extraction_text),
                'priority': ext.attributes.get('priority', 'medium'),
                'due_date': ext.attributes.get('due_date', ''),
                'assignee': ext.attributes.get('assignee', ''),
                'source_text': ext.extraction_text,
                'source_start': start,
                'source_end': end,
            })
    return tasks


# --- Contact Extraction ---

_CONTACT_PROMPT = """Extract people mentioned in this text.
For each person, extract:
- name: The person's full name (keep original spelling from the text)
- email: Their email address if mentioned, otherwise empty
"""

_CONTACT_EXAMPLES = [
    ExampleData(
        text="Meeting with John Smith (john@example.com) and Lisa Chen to discuss the roadmap.",
        extractions=[
            Extraction(
                extraction_class="contact",
                extraction_text="John Smith (john@example.com)",
                attributes={"name": "John Smith", "email": "john@example.com"}
            ),
            Extraction(
                extraction_class="contact",
                extraction_text="Lisa Chen",
                attributes={"name": "Lisa Chen", "email": ""}
            ),
        ]
    ),
]


def _extract_contacts(content):
    result = lx.extract(
        text_or_documents=content,
        prompt_description=_CONTACT_PROMPT,
        examples=_CONTACT_EXAMPLES,
        **_extract_kwargs(),
    )
    existing_contacts = {c['email'].lower(): dict(c) for c in get_contacts() if c['email']}
    contacts = []
    seen_names = set()
    for ext in _get_extractions(result):
        if ext.extraction_class != "contact":
            continue
        name = ext.attributes.get('name', '').strip()
        email = ext.attributes.get('email', '').strip().lower()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        existing = existing_contacts.get(email) if email else None
        start, end = _get_offsets(ext)
        contacts.append({
            'name': name,
            'email': email,
            'source_text': ext.extraction_text,
            'source_start': start,
            'source_end': end,
            'already_exists': existing is not None,
            'existing_id': existing['id'] if existing else None,
        })
    return contacts


# --- Tag Extraction ---

_TAG_PROMPT = """Extract key topics, themes, and tags from this text.
For each tag, extract:
- tag_name: A short lowercase tag (1-3 words) — in the same language as the input text
"""

_TAG_EXAMPLES = [
    ExampleData(
        text="The new authentication system uses OAuth2 with JWT tokens. We need to migrate the database to PostgreSQL and set up CI/CD pipelines for automated testing.",
        extractions=[
            Extraction(
                extraction_class="tag",
                extraction_text="authentication system uses OAuth2",
                attributes={"tag_name": "authentication"}
            ),
            Extraction(
                extraction_class="tag",
                extraction_text="JWT tokens",
                attributes={"tag_name": "jwt"}
            ),
            Extraction(
                extraction_class="tag",
                extraction_text="migrate the database to PostgreSQL",
                attributes={"tag_name": "database"}
            ),
            Extraction(
                extraction_class="tag",
                extraction_text="CI/CD pipelines",
                attributes={"tag_name": "ci/cd"}
            ),
            Extraction(
                extraction_class="tag",
                extraction_text="automated testing",
                attributes={"tag_name": "testing"}
            ),
        ]
    ),
]


def _extract_tags(content):
    result = lx.extract(
        text_or_documents=content,
        prompt_description=_TAG_PROMPT,
        examples=_TAG_EXAMPLES,
        **_extract_kwargs(),
    )
    existing_tags = {t['name'].lower() for t in get_tags()}
    tags = []
    seen = set()
    for ext in _get_extractions(result):
        if ext.extraction_class != "tag":
            continue
        tag_name = ext.attributes.get('tag_name', '').strip().lower()
        if not tag_name or tag_name in seen:
            continue
        if tag_name not in existing_tags:
            continue
        seen.add(tag_name)
        start, end = _get_offsets(ext)
        tags.append({
            'name': tag_name,
            'source_text': ext.extraction_text,
            'source_start': start,
            'source_end': end,
            'already_exists': True,
        })
    return tags


# --- Related Notes (keyword-based, no LLM) ---

def _find_related_notes(content, exclude_note_id=None):
    if not content:
        return []
    words = set(
        w.lower() for w in content.split()
        if len(w) > 4 and w.isalpha()
    )
    all_notes = get_all_notes()
    scored = []
    for note in all_notes:
        if exclude_note_id and note['id'] == exclude_note_id:
            continue
        note_words = set(
            w.lower() for w in (note.get('content', '') + ' ' + note.get('title', '')).split()
            if len(w) > 4 and w.isalpha()
        )
        overlap = len(words & note_words)
        if overlap >= 3:
            scored.append({
                'note_id': note['id'],
                'title': note['title'],
                'overlap_score': overlap,
                'category_name': note.get('category_name', ''),
                'category_color': note.get('category_color', '#6b7280'),
            })
    scored.sort(key=lambda x: x['overlap_score'], reverse=True)
    return scored[:5]
