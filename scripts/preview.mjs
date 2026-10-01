// Preview adapter for the existing FastAPI application. It does not replace the frontend or API.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
const root = process.cwd();
const args = process.argv.slice(2);
function option(name, fallback) {
  const position = args.indexOf(name);
  return position === -1 ? fallback : args[position + 1];
}
const host = option('--host', '127.0.0.1');
const port = option('--port', '8000');
if (!host || !/^\d+$/.test(port || '')) throw new Error('Valid --host and --port are required');
// Managed preview has a restricted filesystem; use system Python with checkout-local dependencies.
const python = existsSync('/usr/bin/python3') ? '/usr/bin/python3' : 'python3';
const dependencies = path.join(root, '.venv', 'lib', 'python3.12', 'site-packages');
if (!existsSync(dependencies)) throw new Error('Create .venv and install requirements.txt before starting the preview.');
const target = existsSync(path.join(root, '.qa-preview')) ? 'tests.preview_app:app' : 'main:app';
const child = spawn(python, ['-m', 'uvicorn', target, '--host', host, '--port', port], {
  cwd: root, stdio: 'inherit',
  env: { ...process.env, PYTHONPATH: dependencies },
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => process.exit(code ?? 1));
