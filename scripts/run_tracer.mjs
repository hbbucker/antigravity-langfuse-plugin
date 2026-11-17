#!/usr/bin/env node
/**
 * Cross-Platform Runner for Langfuse Tracer (Windows & Linux)
 * 
 * Invoked by Antigravity CLI Stop hook via: `node scripts/run_tracer.mjs`
 * Resolves Python dynamically on Windows (cmd/PowerShell) and Linux (bash/zsh),
 * then pipes stdin/stdout seamlessly to langfuse_tracer.py.
 */

import { spawn, execSync } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const tracerScript = path.join(__dirname, 'langfuse_tracer.py');

function canExecute(cmd, args = ['--version']) {
  try {
    execSync(`${cmd} ${args.join(' ')}`, { stdio: 'ignore', windowsHide: true });
    return true;
  } catch {
    return false;
  }
}

function resolvePython() {
  const isWin = process.platform === 'win32';

  // 1. Prioridade: Virtualenv ativo
  if (process.env.VIRTUAL_ENV) {
    const venvPy = isWin
      ? path.join(process.env.VIRTUAL_ENV, 'Scripts', 'python.exe')
      : path.join(process.env.VIRTUAL_ENV, 'bin', 'python3');
    if (fs.existsSync(venvPy)) {
      return { cmd: venvPy, args: [] };
    }
  }

  // 2. Prioridade: Anaconda / Miniconda ativo
  if (process.env.CONDA_PREFIX) {
    const condaPy = isWin
      ? path.join(process.env.CONDA_PREFIX, 'python.exe')
      : path.join(process.env.CONDA_PREFIX, 'bin', 'python3');
    if (fs.existsSync(condaPy)) {
      return { cmd: condaPy, args: [] };
    }
  }

  // 3. Prioridade: Plugin data virtualenv se existir
  const pluginData = process.env.PLUGIN_DATA;
  if (pluginData) {
    const pluginVenvPy = isWin
      ? path.join(pluginData, 'venv', 'Scripts', 'python.exe')
      : path.join(pluginData, 'venv', 'bin', 'python3');
    if (fs.existsSync(pluginVenvPy)) {
      return { cmd: pluginVenvPy, args: [] };
    }
  }

  // 4. Candidatos do sistema operacional
  const candidates = isWin
    ? [
        { cmd: 'python', args: [] },
        { cmd: 'py', args: ['-3'] },
        { cmd: 'python3', args: [] }
      ]
    : [
        { cmd: 'python3', args: [] },
        { cmd: 'python', args: [] }
      ];

  for (const cand of candidates) {
    if (canExecute(cand.cmd, cand.args.concat(['--version']))) {
      return cand;
    }
  }

  return { cmd: isWin ? 'python' : 'python3', args: [] };
}

function main() {
  const py = resolvePython();

  const child = spawn(py.cmd, [...py.args, tracerScript], {
    stdio: ['pipe', 'pipe', 'inherit'],
    windowsHide: true,
    cwd: path.resolve(__dirname, '..')
  });

  child.on('error', (err) => {
    // Fail-safe: nunca bloqueia ou quebra o Antigravity CLI
    process.stdout.write('{}\n');
    process.exit(0);
  });

  process.stdin.pipe(child.stdin);
  child.stdout.pipe(process.stdout);

  child.on('close', (code) => {
    process.exit(code || 0);
  });
}

main();
