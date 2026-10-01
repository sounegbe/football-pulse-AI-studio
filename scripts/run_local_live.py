"""Interactive local launcher: secrets stay in process memory, never written to disk."""
import getpass
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = 'gpt-4.1-mini-2025-04-14'


def main():
    parser = argparse.ArgumentParser(description='Start local studio with a server-only provider key')
    parser.add_argument('--provider', choices=('openai', 'gemini'), default='openai')
    provider = parser.parse_args().provider
    label = 'Gemini' if provider == 'gemini' else 'OpenAI'
    key_name = 'GEMINI_API_KEY' if provider == 'gemini' else 'OPENAI_API_KEY'
    model_name = 'STUDIO_GEMINI_MODEL' if provider == 'gemini' else 'STUDIO_OPENAI_MODEL'
    default_model = 'gemini-2.5-flash-lite' if provider == 'gemini' else DEFAULT_MODEL
    os.chdir(ROOT)
    environment = os.environ.copy()
    key = environment.get(key_name, '').strip()
    if not key:
        key = getpass.getpass(f'{label} API key (hidden; not saved): ').strip()
    if not key:
        raise SystemExit('No key entered. Live server was not started.')
    model = input(f'{label} model [{default_model}]: ').strip() or default_model
    environment.update({key_name: key, model_name: model})
    environment.pop('OPENAI_API_KEY' if provider == 'gemini' else 'GEMINI_API_KEY', None)
    environment.update(STUDIO_GENERATION_PROVIDER=provider,
                       STUDIO_GENERATION_ENABLED='1', STUDIO_ENV='development',
                       STUDIO_ALLOWED_ORIGINS='http://127.0.0.1:8000,http://localhost:8000')
    # Do not reuse pricing inherited for a different model.
    for name in ('STUDIO_INPUT_USD_PER_MILLION','STUDIO_CACHED_INPUT_USD_PER_MILLION','STUDIO_OUTPUT_USD_PER_MILLION'):
        environment.pop(name, None)
    print('Cost estimates remain unknown until you configure current model rates.')
    if provider == 'gemini':
        print('Confirm this model has free quota in your Google AI Studio account.')
        print('Free-tier inputs and outputs may be used to improve Google products.')
    print('Starting local server at http://127.0.0.1:8000 — Ctrl+C stops it.')
    print('Generation requests are sent only when you explicitly submit a reviewed job.')
    os.execvpe(sys.executable, [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000'], environment)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('\nLauncher cancelled.')
