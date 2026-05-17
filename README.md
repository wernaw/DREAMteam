# DREAMteam
Intelligent AI system for the optimal selection of project teams based on the analysis of candidates' personalities.

## Requirements

- Python 3.12+
- uv

## Setup (uv)

Create the virtual environment and install dependencies:

```bash
uv venv
uv sync
```

Run the app:

```bash
uv run uvicorn main:app --reload
```

## Model and data

### Chatbot requirements

Before running the chatbot, make sure Ollama is installed and the model is available:

```bash
ollama pull llama3
ollama serve

