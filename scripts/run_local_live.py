"""Interactive local launcher: secrets stay in process memory, never written to disk."""
import getpass
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = 'gpt-4.1-mini-2025-04-14'


def main():
    os.chdir(ROOT)
    environment = os.environ.copy()
    key = environment.get('OPENAI_API_KEY', '').strip()
    if not key:
        key = getpass.getpass('OpenAI API key (hidden; not saved): ').strip()
    if not key:
        raise SystemExit('No key entered. Live server was not started.')
    model = input(f'OpenAI model [{DEFAULT_MODEL}]: ').strip() or DEFAULT_MODEL
    environment.update(OPENAI_API_KEY=key, STUDIO_OPENAI_MODEL=model,
                       STUDIO_GENERATION_ENABLED='1', STUDIO_ENV='development',
                       STUDIO_ALLOWED_ORIGINS='http://127.0.0.1:8000,http://localhost:8000')
    # Do not reuse pricing inherited for a different model.
    for name in ('STUDIO_INPUT_USD_PER_MILLION','STUDIO_CACHED_INPUT_USD_PER_MILLION','STUDIO_OUTPUT_USD_PER_MILLION'):
        environment.pop(name, None)
    print('Cost estimates remain unknown until you configure current model rates.')
    print('Starting local server at http://127.0.0.1:8000 — Ctrl+C stops it.')
    print('Generation requests are sent only when you explicitly submit a reviewed job.')
    os.execvpe(sys.executable, [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000'], environment)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('\nLauncher cancelled.')
