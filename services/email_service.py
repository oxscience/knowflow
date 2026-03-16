import imaplib
import smtplib
import email
import json
import base64
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import make_msgid, formatdate, parseaddr

import config

# Markers for embedded KnowFlow data in emails
KNOWFLOW_DATA_START = '<!-- KNOWFLOW_DATA:'
KNOWFLOW_DATA_END = ':KNOWFLOW_DATA -->'


def is_configured():
    return bool(config.EMAIL_ADDRESS and config.EMAIL_PASSWORD)


def _connect_smtp():
    try:
        server = smtplib.SMTP(config.EMAIL_SMTP_HOST, config.EMAIL_SMTP_PORT, timeout=10)
        server.starttls()
        server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        return server
    except smtplib.SMTPAuthenticationError:
        raise ConnectionError('SMTP login failed. Check EMAIL_ADDRESS and EMAIL_PASSWORD (Gmail needs an App Password).')
    except (smtplib.SMTPConnectError, OSError) as e:
        raise ConnectionError(f'Cannot reach SMTP server {config.EMAIL_SMTP_HOST}:{config.EMAIL_SMTP_PORT} - {e}')


def _connect_imap():
    try:
        mail = imaplib.IMAP4_SSL(config.EMAIL_IMAP_HOST, config.EMAIL_IMAP_PORT)
        mail.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        return mail
    except imaplib.IMAP4.error:
        raise ConnectionError('IMAP login failed. Check EMAIL_ADDRESS and EMAIL_PASSWORD.')
    except OSError as e:
        raise ConnectionError(f'Cannot reach IMAP server {config.EMAIL_IMAP_HOST}:{config.EMAIL_IMAP_PORT} - {e}')


def test_connection():
    """Test both SMTP and IMAP connections. Returns dict with results."""
    results = {'smtp': None, 'imap': None}

    try:
        server = _connect_smtp()
        server.quit()
        results['smtp'] = 'ok'
    except ConnectionError as e:
        results['smtp'] = str(e)

    try:
        mail = _connect_imap()
        mail.logout()
        results['imap'] = 'ok'
    except ConnectionError as e:
        results['imap'] = str(e)

    return results


def _encode_knowflow_data(data):
    """Encode a dict as base64 JSON for embedding in emails."""
    json_str = json.dumps(data, ensure_ascii=True)
    return base64.b64encode(json_str.encode()).decode()


def _decode_knowflow_data(encoded):
    """Decode base64 JSON from an email."""
    try:
        json_str = base64.b64decode(encoded).decode()
        return json.loads(json_str)
    except Exception:
        return None


def _extract_knowflow_data(html_body):
    """Extract embedded KnowFlow data from an HTML email body."""
    start = html_body.find(KNOWFLOW_DATA_START)
    end = html_body.find(KNOWFLOW_DATA_END)
    if start == -1 or end == -1:
        return None
    encoded = html_body[start + len(KNOWFLOW_DATA_START):end].strip()
    return _decode_knowflow_data(encoded)


def _build_delegation_email(task, recipient_email, recipient_name):
    """Build a delegation email message with embedded KnowFlow sync data."""
    msg = MIMEMultipart('alternative')
    msg['From'] = config.EMAIL_ADDRESS
    msg['To'] = recipient_email
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f'[KnowFlow #{task["id"]}] Task: {task["title"]}'
    msg['Message-ID'] = make_msgid(domain=config.EMAIL_ADDRESS.split('@')[1])
    msg['X-KnowFlow-Version'] = '1.0'

    priority_label = {'high': 'HIGH', 'medium': 'MEDIUM', 'low': 'LOW'}.get(task['priority'], '')

    # Build KnowFlow sync payload
    knowflow_payload = {
        'version': '1.0',
        'type': 'task_delegation',
        'task_id': task['id'],
        'title': task['title'],
        'description': task.get('description', ''),
        'priority': task.get('priority', 'medium'),
        'due_date': task.get('due_date'),
        'category_name': task.get('category_name', ''),
        'tags': task.get('tags', []),
        'sender_email': config.EMAIL_ADDRESS,
        'sender_instance': config.INSTANCE_NAME,
    }
    encoded_data = _encode_knowflow_data(knowflow_payload)

    text_body = f"""Hi {recipient_name},

you have been assigned a task in KnowFlow:

  Task:     {task['title']}
  Priority: {priority_label}
  {f"Details:  {task['description']}" if task.get('description') else ''}

When you're done, simply reply to this email with one of these words:
  done, erledigt, fertig, completed, finished

That's it - the task will be marked as completed automatically.

---
KnowFlow Task #{task['id']}
"""

    html_body = f"""
<div style="font-family: -apple-system, system-ui, sans-serif; max-width: 560px; margin: 0 auto;">
  <div style="background: #4f46e5; color: #fff; padding: 12px 20px; border-radius: 8px 8px 0 0;">
    <strong>KnowFlow</strong> - Task Delegation
  </div>
  <div style="border: 1px solid #e5e7eb; border-top: none; padding: 20px; border-radius: 0 0 8px 8px;">
    <p>Hi {recipient_name},</p>
    <p>you have been assigned a task:</p>
    <div style="background: #f9fafb; border-left: 3px solid {'#ef4444' if task['priority'] == 'high' else '#f59e0b' if task['priority'] == 'medium' else '#22c55e'}; padding: 12px 16px; border-radius: 4px; margin: 16px 0;">
      <strong style="font-size: 1.05em;">{task['title']}</strong><br>
      <span style="color: #6b7280; font-size: 0.85em;">Priority: {priority_label}</span>
      {f'<p style="margin-top: 8px; color: #374151;">{task["description"]}</p>' if task.get('description') else ''}
    </div>
    <p style="background: #f0fdf4; padding: 10px 14px; border-radius: 6px; font-size: 0.9em;">
      When done, just reply with: <strong>done</strong>, <strong>erledigt</strong>, or <strong>fertig</strong>
    </p>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 16px 0;">
    <p style="color: #9ca3af; font-size: 0.75em;">KnowFlow Task #{task['id']}</p>
  </div>
</div>
{KNOWFLOW_DATA_START}{encoded_data}{KNOWFLOW_DATA_END}
"""

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    return msg


def _build_status_update_email(task, recipient_email):
    """Build a status update email to notify the sender of a status change."""
    msg = MIMEMultipart('alternative')
    msg['From'] = config.EMAIL_ADDRESS
    msg['To'] = recipient_email
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f'[KnowFlow #{task["remote_id"]}] Status: {task["status"]}'
    msg['Message-ID'] = make_msgid(domain=config.EMAIL_ADDRESS.split('@')[1])
    msg['X-KnowFlow-Version'] = '1.0'

    status_label = {'todo': 'To Do', 'in_progress': 'In Progress', 'done': 'Done'}.get(task['status'], task['status'])

    knowflow_payload = {
        'version': '1.0',
        'type': 'status_update',
        'remote_task_id': task['remote_id'],
        'new_status': task['status'],
        'sender_email': config.EMAIL_ADDRESS,
        'sender_instance': config.INSTANCE_NAME,
    }
    encoded_data = _encode_knowflow_data(knowflow_payload)

    text_body = f"""KnowFlow Status Update

Task: {task['title']}
New Status: {status_label}

---
KnowFlow Task #{task['remote_id']}
"""

    html_body = f"""
<div style="font-family: -apple-system, system-ui, sans-serif; max-width: 560px; margin: 0 auto;">
  <div style="background: #4f46e5; color: #fff; padding: 12px 20px; border-radius: 8px 8px 0 0;">
    <strong>KnowFlow</strong> - Status Update
  </div>
  <div style="border: 1px solid #e5e7eb; border-top: none; padding: 20px; border-radius: 0 0 8px 8px;">
    <p>Task <strong>{task['title']}</strong> was updated to:</p>
    <div style="background: #f0fdf4; padding: 12px 16px; border-radius: 6px; text-align: center; font-size: 1.1em;">
      <strong>{status_label}</strong>
    </div>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 16px 0;">
    <p style="color: #9ca3af; font-size: 0.75em;">KnowFlow Task #{task['remote_id']}</p>
  </div>
</div>
{KNOWFLOW_DATA_START}{encoded_data}{KNOWFLOW_DATA_END}
"""

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    return msg


def send_delegation_email(task, recipient_email, recipient_name):
    """Send a single delegation email for a task."""
    msg = _build_delegation_email(task, recipient_email, recipient_name)
    server = _connect_smtp()
    try:
        server.sendmail(config.EMAIL_ADDRESS, recipient_email, msg.as_string())
    finally:
        server.quit()
    return msg['Message-ID']


def send_digest(tasks):
    """Send delegation emails for a list of tasks. Reuses one SMTP connection."""
    # Filter tasks that can be sent
    sendable = []
    results = []
    for task in tasks:
        if not task.get('assignee_email'):
            results.append({'task_id': task['id'], 'status': 'skipped', 'reason': 'no email'})
        else:
            sendable.append(task)

    if not sendable:
        return results

    # Open one connection for all emails
    try:
        server = _connect_smtp()
    except ConnectionError as e:
        for task in sendable:
            results.append({'task_id': task['id'], 'status': 'error', 'reason': str(e)})
        return results

    try:
        for task in sendable:
            try:
                msg = _build_delegation_email(
                    task, task['assignee_email'], task['assignee_name'] or 'Team Member'
                )
                server.sendmail(config.EMAIL_ADDRESS, task['assignee_email'], msg.as_string())
                results.append({
                    'task_id': task['id'],
                    'status': 'sent',
                    'message_id': msg['Message-ID']
                })
            except Exception as e:
                results.append({'task_id': task['id'], 'status': 'error', 'reason': str(e)})
    finally:
        server.quit()

    return results


def check_replies():
    """Check IMAP inbox for replies to delegation emails.

    Returns list of dicts: {'task_id': int, 'completed': bool, 'snippet': str, 'from': str}
    """
    if not is_configured():
        return []

    mail = _connect_imap()
    results = []

    try:
        mail.select('INBOX')
        # Use simple search term - Gmail IMAP chokes on special chars like [ and #
        _, message_numbers = mail.search(None, '(UNSEEN SUBJECT "KnowFlow")')

        if not message_numbers[0]:
            return results

        for num in message_numbers[0].split():
            try:
                _, msg_data = mail.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])

                subject = _decode_subject(msg.get('Subject', ''))
                match = re.search(r'\[KnowFlow #(\d+)\]', subject)
                if not match:
                    continue

                task_id = int(match.group(1))

                # Use parseaddr for reliable From extraction
                _, from_email = parseaddr(msg.get('From', ''))

                # Skip our own outgoing delegation emails (not replies).
                # A reply has Re:/AW:/Antwort: prefix — those we DO process.
                if from_email.lower() == config.EMAIL_ADDRESS.lower():
                    subject_stripped = subject.strip().lower()
                    is_reply = (subject_stripped.startswith('re:')
                                or subject_stripped.startswith('aw:')
                                or subject_stripped.startswith('antwort:'))
                    if not is_reply:
                        continue

                body = _get_email_body(msg)
                if not body:
                    continue

                if _contains_completion_keyword(body):
                    results.append({
                        'task_id': task_id,
                        'completed': True,
                        'snippet': body[:200],
                        'from': msg.get('From', ''),
                    })
            except Exception:
                continue
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return results


def _decode_subject(raw_subject):
    """Decode email subject that may be MIME-encoded (e.g. =?UTF-8?Q?...?=)."""
    if not raw_subject:
        return ''
    parts = decode_header(raw_subject)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded.append(data)
    return ' '.join(decoded)


def _get_email_body(msg):
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    return payload.decode(charset, errors='replace')
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            return payload.decode(charset, errors='replace')
    return ''


def _contains_completion_keyword(text):
    """Check if text contains any completion keyword in the reply portion only."""
    text_lower = text.lower()
    lines = text_lower.split('\n')
    reply_text = ''
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('>'):
            break
        if stripped.startswith('on ') and 'wrote:' in stripped:
            break
        if stripped.startswith('am ') and 'schrieb' in stripped:
            break
        reply_text += line + ' '

    for keyword in config.DELEGATION_KEYWORDS:
        if keyword in reply_text:
            return True
    return False


# --- Federated Sync ---

def check_incoming_tasks():
    """Check IMAP inbox for KnowFlow task delegation emails from other instances.

    Looks for emails with X-KnowFlow-Version header or embedded KNOWFLOW_DATA.
    Returns list of dicts with task data ready for import.
    """
    if not is_configured():
        return []

    mail = _connect_imap()
    results = []

    try:
        mail.select('INBOX')
        # Search for unread emails with KnowFlow in the subject
        _, message_numbers = mail.search(None, '(UNSEEN SUBJECT "KnowFlow")')

        if not message_numbers[0]:
            return results

        for num in message_numbers[0].split():
            try:
                _, msg_data = mail.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])

                _, from_email = parseaddr(msg.get('From', ''))

                # Try to extract KnowFlow data from HTML body
                knowflow_data = None
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == 'text/html':
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or 'utf-8'
                                html = payload.decode(charset, errors='replace')
                                knowflow_data = _extract_knowflow_data(html)
                                break
                else:
                    if msg.get_content_type() == 'text/html':
                        payload = msg.get_payload(decode=True)
                        if payload:
                            charset = msg.get_content_charset() or 'utf-8'
                            html = payload.decode(charset, errors='replace')
                            knowflow_data = _extract_knowflow_data(html)

                if not knowflow_data or knowflow_data.get('version') != '1.0':
                    # Not a KnowFlow-formatted email, skip (leave unread for check_replies)
                    mail.store(num, '-FLAGS', '\\Seen')
                    continue

                # Skip emails from the same instance (allows same email with different instances)
                sender_instance = knowflow_data.get('sender_instance', 'default')
                if (from_email.lower() == config.EMAIL_ADDRESS.lower()
                        and sender_instance == config.INSTANCE_NAME):
                    mail.store(num, '-FLAGS', '\\Seen')
                    continue

                msg_type = knowflow_data.get('type')

                if msg_type == 'task_delegation':
                    results.append({
                        'type': 'task_delegation',
                        'remote_id': knowflow_data['task_id'],
                        'remote_source': knowflow_data['sender_email'],
                        'title': knowflow_data['title'],
                        'description': knowflow_data.get('description', ''),
                        'priority': knowflow_data.get('priority', 'medium'),
                        'due_date': knowflow_data.get('due_date'),
                        'category_name': knowflow_data.get('category_name', ''),
                        'tags': knowflow_data.get('tags', []),
                    })

                elif msg_type == 'status_update':
                    results.append({
                        'type': 'status_update',
                        'remote_task_id': knowflow_data['remote_task_id'],
                        'new_status': knowflow_data['new_status'],
                        'sender_email': knowflow_data['sender_email'],
                    })

            except Exception:
                continue
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return results


def check_email_to_tasks():
    """Check IMAP inbox for emails that should become tasks.

    Handles two cases:
    1. Keyword emails: Anyone sends an email with [TASK] or [TODO] in the subject
    2. Forwarded emails: The user forwards an email to themselves (Fwd:/WG:/Fw: prefix)

    Returns list of dicts ready for task creation.
    """
    if not is_configured():
        return []

    mail = _connect_imap()
    results = []
    seen_nums = set()

    try:
        mail.select('INBOX')

        # Search 1: Keyword emails from anyone
        for keyword in config.TASK_KEYWORDS:
            try:
                _, nums = mail.search(None, f'(UNSEEN SUBJECT "{keyword}")')
                if nums[0]:
                    for num in nums[0].split():
                        seen_nums.add(num)
            except Exception:
                continue

        # Search 2: Forwarded emails from self
        if config.EMAIL_ADDRESS:
            try:
                _, nums = mail.search(None, f'(UNSEEN FROM "{config.EMAIL_ADDRESS}")')
                if nums[0]:
                    for num in nums[0].split():
                        seen_nums.add(num)
            except Exception:
                pass

        # Process all found emails
        for num in seen_nums:
            try:
                _, msg_data = mail.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])

                # Skip KnowFlow sync emails (handled by check_incoming_tasks)
                html_body = _get_html_body(msg)
                if html_body and KNOWFLOW_DATA_START in html_body:
                    mail.store(num, '-FLAGS', '\\Seen')
                    continue

                subject = _decode_subject(msg.get('Subject', ''))

                # Skip KnowFlow reply emails (handled by check_replies)
                if re.search(r'\[KnowFlow #\d+\]', subject):
                    mail.store(num, '-FLAGS', '\\Seen')
                    continue

                _, from_email = parseaddr(msg.get('From', ''))
                from_name = _decode_subject(msg.get('From', '').split('<')[0].strip().strip('"'))

                # Determine type: keyword or forwarded
                subject_upper = subject.upper()
                is_keyword = any(kw.upper() in subject_upper for kw in config.TASK_KEYWORDS)
                is_forwarded = (
                    from_email.lower() == config.EMAIL_ADDRESS.lower()
                    and _is_forward_subject(subject)
                )

                if not is_keyword and not is_forwarded:
                    # Self-sent email without forward prefix and no keyword — skip
                    mail.store(num, '-FLAGS', '\\Seen')
                    continue

                # Clean up subject → task title
                title = _clean_task_subject(subject)
                if not title:
                    mail.store(num, '-FLAGS', '\\Seen')
                    continue

                # Extract body → task description
                body = _get_email_body(msg)
                description = _clean_email_body(body) if body else ''

                results.append({
                    'type': 'email_task',
                    'title': title,
                    'description': description[:2000],
                    'sender_name': from_name or from_email,
                    'sender_email': from_email,
                    'is_forwarded': is_forwarded,
                })

            except Exception:
                continue
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return results


def _get_html_body(msg):
    """Extract HTML body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    return payload.decode(charset, errors='replace')
    elif msg.get_content_type() == 'text/html':
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            return payload.decode(charset, errors='replace')
    return ''


def _is_forward_subject(subject):
    """Check if subject indicates a forwarded email."""
    s = subject.strip().lower()
    return s.startswith('fwd:') or s.startswith('fw:') or s.startswith('wg:')


def _clean_task_subject(subject):
    """Remove keywords and forward prefixes from subject to get a clean task title."""
    title = subject.strip()
    # Remove task keywords (case-insensitive)
    for kw in config.TASK_KEYWORDS:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        title = pattern.sub('', title)
    # Remove forward prefixes
    title = re.sub(r'^(?:Fwd|Fw|WG)\s*:\s*', '', title, flags=re.IGNORECASE)
    return title.strip()


def _clean_email_body(text):
    """Clean email body for use as task description: remove quoted lines and signatures."""
    lines = text.split('\n')
    clean = []
    for line in lines:
        stripped = line.strip()
        # Stop at quoted text
        if stripped.startswith('>'):
            break
        # Stop at common reply/forward headers
        if stripped.startswith('On ') and 'wrote:' in stripped:
            break
        if stripped.startswith('Am ') and 'schrieb' in stripped:
            break
        # Stop at forwarded message header
        if stripped.startswith('---------- Forwarded message'):
            break
        if stripped == '-- ':
            break
        clean.append(line)
    return '\n'.join(clean).strip()


def send_status_update(task):
    """Send a status update email back to the original sender of a remote task."""
    if not is_configured():
        return None
    if not task.get('is_remote') or not task.get('remote_source'):
        return None

    msg = _build_status_update_email(task, task['remote_source'])
    server = _connect_smtp()
    try:
        server.sendmail(config.EMAIL_ADDRESS, task['remote_source'], msg.as_string())
    finally:
        server.quit()
    return msg['Message-ID']
