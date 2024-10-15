# Jai

Jai is a webapp that lets users write their journal entries with the help of AI.

# How it works

- **Frontend**: `journal.html` displays an Apple-like note-taking experience with a left sidebar to choose a note, and an editor that autosaves. It includes a Chainlit Copilot embedded via `script.js`.
- **Copilot**: `app.py` contains the logic for the AI assistant, using Chainlit to handle user interactions and LLM responses.
- **Backend**: `backend.py` is a Flask app that serves the frontend and provides an API for the Copilot to use.
- **LLM**: Relies on OpenAI for remote models and Ollama for local models.
- **Data Storage**: All journal entries are stored in markdown files in the `data` folder.

# How to use

With OpenAI
```
bin/dev
```

With Ollama (local llama3.2)
```
bin/dev local
```

# Improvements

- Improve SYSTEM_PROMPT
- Improve JOURNAL_PROMPT
