document.addEventListener('DOMContentLoaded', () => {

    // === Keyboard Shortcuts (global) ===
    document.addEventListener('keydown', (e) => {
        const tag = e.target.tagName;
        const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

        // Cmd+Enter / Ctrl+Enter: submit the closest form
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            // First: try the form the cursor is currently in
            let form = e.target.closest('form');
            // Fallback: if the detail sidebar is open, use its form
            if (!form) {
                const sidebar = document.getElementById('detail-sidebar');
                if (sidebar && sidebar.classList.contains('open')) {
                    form = sidebar.querySelector('form');
                }
            }
            // Fallback: if the modal is open, use the modal's form
            if (!form) {
                const modal = document.getElementById('modal-overlay');
                if (modal && !modal.classList.contains('hidden')) {
                    form = modal.querySelector('form');
                }
            }
            if (form) {
                // requestSubmit() fires a native 'submit' event → HTMX intercepts it
                form.requestSubmit();
            }
            return;
        }

        // Escape: close sidebar / modal
        if (e.key === 'Escape') {
            const sidebar = document.getElementById('detail-sidebar');
            if (sidebar && sidebar.classList.contains('open')) {
                closeDetailSidebar();
            } else {
                document.getElementById('modal-overlay')?.classList.add('hidden');
            }
            if (isInput) e.target.blur();
            return;
        }

        // Don't trigger shortcuts when typing in inputs
        if (isInput) return;

        // N: focus quick capture input
        if (e.key === 'n' || e.key === 'N') {
            e.preventDefault();
            const input = document.querySelector('.quick-capture input[name="title"]');
            if (input) input.focus();
            return;
        }

        // /: focus search
        if (e.key === '/') {
            e.preventDefault();
            const search = document.querySelector('.search-bar input');
            if (search) search.focus();
            return;
        }

        // 1: go to Kanban
        if (e.key === '1') { window.location = '/kanban'; return; }
        // 2: go to List
        if (e.key === '2') { window.location = '/list'; return; }
        // 3: go to Delegation
        if (e.key === '3') { window.location = '/delegation'; return; }
        // 4: go to Notes
        if (e.key === '4') { window.location = '/notes'; return; }
        // 5: go to Team
        if (e.key === '5') { window.location = '/team'; return; }
    });


    // === Kanban Drag and Drop ===
    const board = document.querySelector('.kanban-board');
    if (board) {

    board.addEventListener('dragstart', (e) => {
        const card = e.target.closest('.task-card');
        if (!card) return;
        e.dataTransfer.setData('text/plain', card.dataset.taskId);
        e.dataTransfer.effectAllowed = 'move';
        requestAnimationFrame(() => card.classList.add('dragging'));
    });

    board.addEventListener('dragend', (e) => {
        const card = e.target.closest('.task-card');
        if (card) card.classList.remove('dragging');
        document.querySelectorAll('.kanban-column').forEach(col =>
            col.classList.remove('drag-over')
        );
    });

    document.querySelectorAll('.kanban-column').forEach(column => {
        const cardList = column.querySelector('.card-list');

        column.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            column.classList.add('drag-over');
        });

        column.addEventListener('dragleave', (e) => {
            if (!column.contains(e.relatedTarget)) {
                column.classList.remove('drag-over');
            }
        });

        column.addEventListener('drop', (e) => {
            e.preventDefault();
            column.classList.remove('drag-over');

            const taskId = e.dataTransfer.getData('text/plain');
            const newStatus = column.dataset.status;
            const card = document.querySelector(`.task-card[data-task-id="${taskId}"]`);
            if (!card) return;

            // Remove empty state if present
            const emptyState = cardList.querySelector('.empty-state');
            if (emptyState) emptyState.remove();

            // Determine drop position
            const siblings = [...cardList.querySelectorAll('.task-card:not(.dragging)')];
            let insertBefore = null;
            for (const sibling of siblings) {
                const rect = sibling.getBoundingClientRect();
                if (e.clientY < rect.top + rect.height / 2) {
                    insertBefore = sibling;
                    break;
                }
            }

            // Check if old column will be empty
            const oldCardList = card.parentElement;

            if (insertBefore) {
                cardList.insertBefore(card, insertBefore);
            } else {
                cardList.appendChild(card);
            }

            // Add empty state to old column if needed
            if (oldCardList !== cardList && oldCardList.querySelectorAll('.task-card').length === 0) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = 'No tasks yet';
                oldCardList.appendChild(empty);
            }

            const newPosition = [...cardList.querySelectorAll('.task-card')].indexOf(card);

            fetch(`/tasks/${taskId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus, position: newPosition })
            }).then(response => {
                if (response.ok) {
                    updateColumnCounts();
                }
            });
        });
    });

    function updateColumnCounts() {
        document.querySelectorAll('.kanban-column').forEach(col => {
            const count = col.querySelectorAll('.task-card').length;
            const countEl = col.querySelector('.count');
            if (countEl) countEl.textContent = count;
        });
    }

    } // end kanban guard

    // === Auto-Save on Navigate ===
    const editorForm = document.querySelector('.note-editor-view form');
    const editorTextarea = document.querySelector('.editor-textarea');
    const editorTitle = document.querySelector('.editor-title-input');
    if (editorTextarea && editorForm) {
        let savedContent = editorTextarea.value;
        let savedTitle = editorTitle ? editorTitle.value : '';

        function isDirty() {
            return editorTextarea.value !== savedContent ||
                   (editorTitle && editorTitle.value !== savedTitle);
        }

        function autoSave() {
            if (!isDirty()) return;
            // Only auto-save existing notes (PUT via HTMX) — new notes need explicit save
            if (editorForm.hasAttribute('hx-put')) {
                editorForm.requestSubmit();
            }
        }

        // Reset saved state after HTMX swap
        document.body.addEventListener('htmx:afterSwap', () => {
            const ta = document.querySelector('.editor-textarea');
            const ti = document.querySelector('.editor-title-input');
            if (ta) savedContent = ta.value;
            if (ti) savedTitle = ti.value;
        });

        // Auto-save when clicking nav links
        document.querySelectorAll('.nav-link, .logo').forEach(link => {
            link.addEventListener('click', () => autoSave());
        });

        // Auto-save on tab/window close
        window.addEventListener('beforeunload', () => autoSave());

        // Auto-save when clicking sidebar note links
        document.querySelectorAll('.sidebar-note-link').forEach(link => {
            link.addEventListener('click', () => autoSave());
        });
    }

    // === Wiki Sidebar Filter ===
    const sidebarSearch = document.getElementById('sidebar-search');
    if (sidebarSearch) {
        sidebarSearch.addEventListener('input', () => {
            const q = sidebarSearch.value.toLowerCase().trim();
            document.querySelectorAll('.sidebar-note-link').forEach(link => {
                const title = link.getAttribute('data-title') || '';
                link.style.display = (!q || title.includes(q)) ? '' : 'none';
            });
            // Show/hide empty sections
            document.querySelectorAll('.sidebar-section').forEach(section => {
                const visible = section.querySelectorAll('.sidebar-note-link:not([style*="display: none"])');
                section.style.display = (!q || visible.length > 0) ? '' : 'none';
            });
        });
    }

});


// === Table Sorting ===
function sortTable(header) {
    const table = header.closest('table');
    const tbody = table.querySelector('tbody');
    const col = parseInt(header.dataset.col);
    const rows = Array.from(tbody.querySelectorAll('tr'));

    // Toggle direction
    const isAsc = header.classList.contains('sort-asc');
    table.querySelectorAll('th.sortable').forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
    header.classList.add(isAsc ? 'sort-desc' : 'sort-asc');
    const dir = isAsc ? -1 : 1;

    // Custom sort orders
    const priorityOrder = { 'high': 1, 'medium': 2, 'low': 3 };
    const statusOrder = { 'to do': 1, 'in progress': 2, 'done': 3 };

    rows.sort((a, b) => {
        const aText = (a.cells[col]?.textContent || '').trim().toLowerCase();
        const bText = (b.cells[col]?.textContent || '').trim().toLowerCase();

        // Priority column
        if (priorityOrder[aText] && priorityOrder[bText]) {
            return (priorityOrder[aText] - priorityOrder[bText]) * dir;
        }
        // Status column
        if (statusOrder[aText] && statusOrder[bText]) {
            return (statusOrder[aText] - statusOrder[bText]) * dir;
        }
        // Date column (empty goes last)
        if (col === 4) {
            if (!aText && !bText) return 0;
            if (!aText) return 1;
            if (!bText) return -1;
            return aText.localeCompare(bText) * dir;
        }
        // Default: alphabetical
        return aText.localeCompare(bText) * dir;
    });

    rows.forEach(row => tbody.appendChild(row));
}


// === Markdown Editor ===
class MarkdownEditor {
    constructor(textarea) {
        this.textarea = textarea;
        this.preview = document.getElementById('preview-content');
        this.toolbar = document.querySelector('.editor-toolbar');
        this.noteTitleMap = {};
        this.init();
    }

    async init() {
        await this.loadNoteTitles();
        this.configureMarked();
        this.bindToolbar();
        this.bindKeyboardShortcuts();
        this.bindTabKey();
        this.bindLivePreview();
        this.bindAutocomplete();
        this.updatePreview();
    }

    async loadNoteTitles() {
        try {
            const resp = await fetch('/api/note-titles');
            this.noteTitleMap = await resp.json();
        } catch (e) {
            this.noteTitleMap = {};
        }
    }

    configureMarked() {
        if (typeof marked === 'undefined') return;
        const self = this;
        const wikiLinkExtension = {
            name: 'wikiLink',
            level: 'inline',
            start(src) { return src.indexOf('[['); },
            tokenizer(src) {
                const match = /^\[\[(.+?)\]\]/.exec(src);
                if (match) {
                    return { type: 'wikiLink', raw: match[0], title: match[1].trim() };
                }
            },
            renderer(token) {
                const titleLower = token.title.toLowerCase();
                const entry = self.noteTitleMap[titleLower];
                if (entry) {
                    return `<a href="/notes/${entry.id}" class="wiki-link">${token.title}</a>`;
                }
                return `<a href="/notes/new?title=${encodeURIComponent(token.title)}" class="wiki-link wiki-link-new">${token.title}</a>`;
            }
        };
        marked.use({ extensions: [wikiLinkExtension], breaks: true, gfm: true });
    }

    bindToolbar() {
        if (!this.toolbar) return;
        this.toolbar.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;
            e.preventDefault();
            this.applyAction(btn.dataset.action);
        });
    }

    bindKeyboardShortcuts() {
        this.textarea.addEventListener('keydown', (e) => {
            if (!(e.metaKey || e.ctrlKey)) return;
            const actions = { b: 'bold', i: 'italic', k: 'link' };
            if (actions[e.key]) {
                e.preventDefault();
                e.stopPropagation();
                this.applyAction(actions[e.key]);
            }
        });
    }

    bindTabKey() {
        this.textarea.addEventListener('keydown', (e) => {
            if (e.key !== 'Tab') return;
            e.preventDefault();
            const { selectionStart: start, selectionEnd: end, value } = this.textarea;
            if (e.shiftKey) {
                const lineStart = value.lastIndexOf('\n', start - 1) + 1;
                const linePrefix = value.substring(lineStart, lineStart + 4);
                if (linePrefix.startsWith('    ')) {
                    this.textarea.value = value.substring(0, lineStart) + value.substring(lineStart + 4);
                    this.textarea.selectionStart = this.textarea.selectionEnd = Math.max(start - 4, lineStart);
                }
            } else {
                this.textarea.value = value.substring(0, start) + '    ' + value.substring(end);
                this.textarea.selectionStart = this.textarea.selectionEnd = start + 4;
            }
            this.updatePreview();
        });
    }

    bindLivePreview() {
        let timeout;
        this.textarea.addEventListener('input', () => {
            clearTimeout(timeout);
            timeout = setTimeout(() => this.updatePreview(), 150);
        });
    }

    updatePreview() {
        if (!this.preview || typeof marked === 'undefined') return;
        const content = this.textarea.value;
        if (!content.trim()) {
            this.preview.innerHTML = '<p style="color:var(--color-text-muted)">Preview appears here...</p>';
            return;
        }
        this.preview.innerHTML = marked.parse(content);
    }

    // === Wiki-Link Autocomplete ===
    bindAutocomplete() {
        this.acDropdown = document.createElement('div');
        this.acDropdown.className = 'wikilink-autocomplete';
        this.textarea.parentElement.style.position = 'relative';
        this.textarea.parentElement.appendChild(this.acDropdown);
        this.acVisible = false;
        this.acIndex = -1;
        this.acItems = [];

        this.textarea.addEventListener('input', () => this.checkAutocomplete());
        this.textarea.addEventListener('keydown', (e) => this.handleAcKey(e));
        this.textarea.addEventListener('blur', () => {
            setTimeout(() => this.hideAutocomplete(), 150);
        });
    }

    checkAutocomplete() {
        const pos = this.textarea.selectionStart;
        const text = this.textarea.value.substring(0, pos);
        // Find unclosed [[ before cursor
        const match = text.match(/\[\[([^\]]{0,40})$/);
        if (!match) { this.hideAutocomplete(); return; }

        const query = match[1].toLowerCase();
        const titles = Object.keys(this.noteTitleMap);
        this.acItems = titles
            .filter(t => t.includes(query))
            .sort((a, b) => a.indexOf(query) - b.indexOf(query))
            .slice(0, 6);

        if (!this.acItems.length) { this.hideAutocomplete(); return; }

        this.acIndex = 0;
        this.renderAutocomplete();
    }

    renderAutocomplete() {
        this.acDropdown.innerHTML = this.acItems
            .map((title, i) => `<div class="ac-item${i === this.acIndex ? ' ac-active' : ''}">${title}</div>`)
            .join('');
        this.acDropdown.style.display = 'block';
        this.acVisible = true;

        // Position near cursor
        const coords = this.getCaretCoords();
        this.acDropdown.style.top = coords.top + 'px';
        this.acDropdown.style.left = coords.left + 'px';

        // Click handler
        this.acDropdown.querySelectorAll('.ac-item').forEach((el, i) => {
            el.addEventListener('mousedown', (e) => {
                e.preventDefault();
                this.selectAutocomplete(this.acItems[i]);
            });
        });
    }

    handleAcKey(e) {
        if (!this.acVisible) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.acIndex = (this.acIndex + 1) % this.acItems.length;
            this.renderAutocomplete();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.acIndex = (this.acIndex - 1 + this.acItems.length) % this.acItems.length;
            this.renderAutocomplete();
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            if (this.acIndex >= 0) {
                e.preventDefault();
                this.selectAutocomplete(this.acItems[this.acIndex]);
            }
        } else if (e.key === 'Escape') {
            this.hideAutocomplete();
        }
    }

    selectAutocomplete(title) {
        const pos = this.textarea.selectionStart;
        const text = this.textarea.value;
        const before = text.substring(0, pos);
        const bracketStart = before.lastIndexOf('[[');
        const after = text.substring(pos);
        // Find original-case title from the map
        const entry = this.noteTitleMap[title.toLowerCase()];
        const originalTitle = entry ? entry.title : title;
        // Check if ]] already follows
        const closingExists = after.startsWith(']]');
        const insertion = originalTitle + (closingExists ? '' : ']]');
        this.textarea.value = text.substring(0, bracketStart + 2) + insertion + (closingExists ? after : after);
        const newPos = bracketStart + 2 + originalTitle.length + (closingExists ? 0 : 2);
        this.textarea.selectionStart = this.textarea.selectionEnd = newPos;
        this.textarea.focus();
        this.hideAutocomplete();
        this.updatePreview();
    }

    hideAutocomplete() {
        this.acDropdown.style.display = 'none';
        this.acVisible = false;
        this.acIndex = -1;
    }

    getCaretCoords() {
        // Approximate caret position using a hidden mirror div
        const ta = this.textarea;
        const text = ta.value.substring(0, ta.selectionStart);
        const lines = text.split('\n');
        const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 24;
        const paddingTop = parseFloat(getComputedStyle(ta).paddingTop) || 0;
        const paddingLeft = parseFloat(getComputedStyle(ta).paddingLeft) || 0;
        const top = paddingTop + (lines.length * lineHeight) - ta.scrollTop + 4;
        const lastLine = lines[lines.length - 1];
        const left = paddingLeft + (lastLine.length * 8.4); // approximate char width for monospace
        return {
            top: Math.min(top, ta.offsetHeight - 40),
            left: Math.min(left, ta.offsetWidth - 200)
        };
    }

    applyAction(action) {
        const actions = {
            bold:     { prefix: '**', suffix: '**', placeholder: 'bold text' },
            italic:   { prefix: '_', suffix: '_', placeholder: 'italic text' },
            heading:  { prefix: '## ', suffix: '', placeholder: 'Heading', line: true },
            link:     { prefix: '[', suffix: '](url)', placeholder: 'link text' },
            wikilink: { prefix: '[[', suffix: ']]', placeholder: 'Note Title' },
            list:     { prefix: '- ', suffix: '', placeholder: 'list item', line: true },
            code:     { prefix: '`', suffix: '`', placeholder: 'code' },
            quote:    { prefix: '> ', suffix: '', placeholder: 'quote', line: true },
        };
        const cfg = actions[action];
        if (!cfg) return;

        const { selectionStart: start, selectionEnd: end, value } = this.textarea;
        const selected = value.substring(start, end);
        const text = selected || cfg.placeholder;
        let newValue, cursorStart, cursorEnd;

        if (cfg.line) {
            const lineStart = value.lastIndexOf('\n', start - 1) + 1;
            newValue = value.substring(0, lineStart) + cfg.prefix + value.substring(lineStart);
            cursorStart = start + cfg.prefix.length;
            cursorEnd = end + cfg.prefix.length;
        } else {
            newValue = value.substring(0, start) + cfg.prefix + text + cfg.suffix + value.substring(end);
            cursorStart = start + cfg.prefix.length;
            cursorEnd = cursorStart + text.length;
        }

        this.textarea.value = newValue;
        this.textarea.selectionStart = cursorStart;
        this.textarea.selectionEnd = cursorEnd;
        this.textarea.focus();
        this.updatePreview();
    }
}


// === AI Analyze Button: Loading State ===
document.body.addEventListener('htmx:beforeRequest', function(e) {
    const btn = e.detail.elt;
    if (!btn.classList.contains('ai-analyze-btn')) return;
    btn._origText = btn.innerHTML;
    btn.innerHTML = '&#9733; Analysiere&hellip;';
    btn.classList.add('htmx-request');
});
document.body.addEventListener('htmx:afterRequest', function(e) {
    const btn = e.detail.elt;
    if (!btn.classList.contains('ai-analyze-btn')) return;
    btn.innerHTML = btn._origText || '&#9733; Analyze';
    btn.classList.remove('htmx-request');
    // Scroll AI suggestions into view
    const panel = document.getElementById('ai-suggestions');
    if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});

// === AI Suggestions: Source Grounding Highlight ===
document.addEventListener('mouseover', function(e) {
    const item = e.target.closest('.suggestion-item[data-source-start]');
    if (!item) return;
    const start = parseInt(item.dataset.sourceStart);
    const end = parseInt(item.dataset.sourceEnd);
    if (isNaN(start) || isNaN(end)) return;

    const textarea = document.querySelector('.editor-textarea');
    if (!textarea) return;

    textarea.focus();
    textarea.setSelectionRange(start, end);

    const lineHeight = parseFloat(getComputedStyle(textarea).lineHeight) || 24;
    const textBefore = textarea.value.substring(0, start);
    const lineNumber = textBefore.split('\n').length;
    textarea.scrollTop = Math.max(0, (lineNumber - 3) * lineHeight);
});

document.addEventListener('mouseout', function(e) {
    const item = e.target.closest('.suggestion-item[data-source-start]');
    if (!item) return;
    const textarea = document.querySelector('.editor-textarea');
    if (textarea) {
        textarea.setSelectionRange(textarea.selectionStart, textarea.selectionStart);
    }
});


// === Insert Wiki Link from Related Note Suggestion ===
function insertWikiLink(title) {
    const textarea = document.querySelector('.editor-textarea');
    if (!textarea) return;
    const pos = textarea.selectionStart;
    const before = textarea.value.substring(0, pos);
    const after = textarea.value.substring(pos);
    const link = '[[' + title + ']]';
    textarea.value = before + link + after;
    textarea.selectionStart = textarea.selectionEnd = pos + link.length;
    textarea.focus();
    textarea.dispatchEvent(new Event('input'));
}
