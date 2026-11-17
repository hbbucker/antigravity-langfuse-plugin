#!/usr/bin/env node
/**
 * Setup Wizard for Antigravity & StartupOS Langfuse Observability Plugin
 * 
 * Cross-platform (Windows & Linux).
 * Configures Remote (Cloud / Self-hosted) or Local (Docker) telemetry.
 * Saves configuration to ~/.gemini/antigravity-cli/langfuse.json
 */

import readline from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import https from 'node:https';
import { execSync } from 'node:child_process';

const CONFIG_DIR = path.join(os.homedir(), '.gemini', 'antigravity-cli');
const CONFIG_FILE = path.join(CONFIG_DIR, 'langfuse.json');

// ANSI Colors for cross-platform terminals
const cyan = (text) => `\x1b[36m${text}\x1b[0m`;
const green = (text) => `\x1b[32m${text}\x1b[0m`;
const yellow = (text) => `\x1b[33m${text}\x1b[0m`;
const red = (text) => `\x1b[31m${text}\x1b[0m`;
const bold = (text) => `\x1b[1m${text}\x1b[0m`;

function checkHealth(host) {
  return new Promise((resolve) => {
    try {
      const url = new URL(host.endsWith('/') ? `${host}api/public/health` : `${host}/api/public/health`);
      const client = url.protocol === 'https:' ? https : http;
      
      const req = client.get(url, { timeout: 3000 }, (res) => {
        resolve(res.statusCode === 200 || res.statusCode === 204);
      });
      req.on('error', () => {
        // If it's cloud.langfuse.com, health might require auth or return 404, assume reachable
        if (url.hostname.includes('cloud.langfuse.com')) {
          resolve(true);
        } else {
          resolve(false);
        }
      });
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    } catch {
      resolve(false);
    }
  });
}

function checkPythonLangfuse() {
  const isWin = process.platform === 'win32';
  const pyCmds = isWin ? ['python', 'py -3', 'python3'] : ['python3', 'python'];
  
  for (const py of pyCmds) {
    try {
      execSync(`${py} -c "import langfuse"`, { stdio: 'ignore', windowsHide: true });
      return { ok: true, py };
    } catch {
      // try next
    }
  }
  return { ok: false };
}

function parseArgs() {
  const args = process.argv.slice(2);
  const options = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--remote') options.mode = 'remote';
    else if (args[i] === '--local') options.mode = 'local';
    else if (args[i] === '--status') options.status = true;
    else if (args[i] === '--host' && args[i + 1]) options.host = args[++i];
    else if (args[i] === '--public-key' && args[i + 1]) options.publicKey = args[++i];
    else if (args[i] === '--secret-key' && args[i + 1]) options.secretKey = args[++i];
  }
  return options;
}

function saveConfig(config) {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf-8');
}

function loadConfig() {
  if (fs.existsSync(CONFIG_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
    } catch {
      return null;
    }
  }
  return null;
}

async function main() {
  console.log(`\n${bold(cyan('╔════════════════════════════════════════════════════════════════╗'))}`);
  console.log(`${bold(cyan('║   StartupOS & Antigravity - Langfuse Telemetry Setup Wizard    ║'))}`);
  console.log(`${bold(cyan('╚════════════════════════════════════════════════════════════════╝'))}\n`);

  const opts = parseArgs();

  // Status check flag
  if (opts.status) {
    const current = loadConfig();
    if (current) {
      console.log(green('✔ Configuração ativa encontrada:'));
      console.log(`  Arquivo: ${CONFIG_FILE}`);
      console.log(`  Host:    ${current.host}`);
      console.log(`  PubKey:  ${current.public_key ? current.public_key.substring(0, 10) + '...' : 'não definido'}`);
    } else {
      console.log(yellow('Nenhuma configuração salva em ' + CONFIG_FILE));
    }
    const pyCheck = checkPythonLangfuse();
    if (pyCheck.ok) {
      console.log(green(`✔ Biblioteca Python 'langfuse' detectada via: ${pyCheck.py}`));
    } else {
      console.log(yellow('⚠ Biblioteca Python \'langfuse\' não encontrada no ambiente atual.'));
      console.log(`  Execute: ${cyan('pip install "langfuse>=2.50.0,<3.0.0"')}`);
    }
    process.exit(0);
  }

  // Automated non-interactive mode
  if (opts.mode) {
    let targetConfig = {};
    if (opts.mode === 'remote') {
      const host = opts.host || 'https://cloud.langfuse.com';
      if (!opts.publicKey || !opts.secretKey) {
        console.error(red('Erro: Modo --remote requer --public-key e --secret-key'));
        process.exit(1);
      }
      targetConfig = {
        host: host.replace(/\/$/, ''),
        public_key: opts.publicKey,
        secret_key: opts.secretKey
      };
    } else {
      targetConfig = {
        host: opts.host || 'http://localhost:3000',
        public_key: opts.publicKey || 'pk-lf-antigravity-cli-public',
        secret_key: opts.secretKey || 'sk-lf-antigravity-cli-secret'
      };
    }
    saveConfig(targetConfig);
    console.log(green(`✔ Configuração gravada com sucesso em ${CONFIG_FILE}`));
    process.exit(0);
  }

  // Interactive mode
  const rl = readline.createInterface({ input, output });

  try {
    const currentConfig = loadConfig();
    if (currentConfig) {
      console.log(`${yellow('ℹ Configuração existente detectada:')}`);
      console.log(`  Host: ${currentConfig.host}`);
      console.log(`  Public Key: ${currentConfig.public_key?.slice(0, 12)}...`);
      const overwrite = await rl.question(`\nDeseja reconfigurar? (S/n): `);
      if (overwrite.trim().toLowerCase() === 'n') {
        console.log(green('\nConfiguração mantida. Até logo!\n'));
        rl.close();
        return;
      }
    }

    console.log(`\nSelecione o modo de observabilidade:`);
    console.log(`  ${bold('1)')} ${cyan('Langfuse Remoto / Cloud')} (cloud.langfuse.com ou self-hosted corporativo)`);
    console.log(`  ${bold('2)')} ${cyan('Langfuse Local')} (Docker Compose local na porta 3000)\n`);

    const modeChoice = await rl.question(`Escolha uma opção (1 ou 2) [1]: `);
    const isLocal = modeChoice.trim() === '2';

    let config = {};

    if (isLocal) {
      console.log(`\n${bold('--- Configuração do Modo Local (Docker) ---')}`);
      const host = await rl.question(`Host do Langfuse Local [http://localhost:3000]: `);
      const publicKey = await rl.question(`Public Key [pk-lf-antigravity-cli-public]: `);
      const secretKey = await rl.question(`Secret Key [sk-lf-antigravity-cli-secret]: `);

      config = {
        host: (host.trim() || 'http://localhost:3000').replace(/\/$/, ''),
        public_key: publicKey.trim() || 'pk-lf-antigravity-cli-public',
        secret_key: secretKey.trim() || 'sk-lf-antigravity-cli-secret'
      };

      console.log(`\nVerificando saúde do serviço local em ${config.host}...`);
      const healthy = await checkHealth(config.host);
      if (healthy) {
        console.log(green(`✔ Langfuse Local respondendo com sucesso!`));
      } else {
        console.log(yellow(`⚠ Não foi possível conectar a ${config.host}/api/public/health`));
        console.log(`  Lembre-se de iniciar seus containers com: ${cyan('docker compose up -d')}`);
      }
    } else {
      console.log(`\n${bold('--- Configuração do Modo Remoto (Cloud ou Servidor Privado) ---')}`);
      const host = await rl.question(`URL do Langfuse [https://cloud.langfuse.com]: `);
      const finalHost = (host.trim() || 'https://cloud.langfuse.com').replace(/\/$/, '');

      let publicKey = '';
      while (!publicKey) {
        publicKey = (await rl.question(`Informe a Public Key (pk-lf-...): `)).trim();
        if (!publicKey) console.log(red('Public Key é obrigatória.'));
      }

      let secretKey = '';
      while (!secretKey) {
        secretKey = (await rl.question(`Informe a Secret Key (sk-lf-...): `)).trim();
        if (!secretKey) console.log(red('Secret Key é obrigatória.'));
      }

      config = {
        host: finalHost,
        public_key: publicKey,
        secret_key: secretKey
      };

      console.log(`\nTestando conectividade com ${config.host}...`);
      const healthy = await checkHealth(config.host);
      if (healthy) {
        console.log(green(`✔ Conexão estabelecida com sucesso!`));
      } else {
        console.log(yellow(`⚠ Não foi possível verificar o endpoint de healthcheck, mas a configuração será salva.`));
      }
    }

    // Salva configuração
    saveConfig(config);
    console.log(`\n${green('✔ Configuração salva com sucesso em:')} ${CONFIG_FILE}`);

    // Verifica dependências Python
    console.log(`\nVerificando dependências Python no sistema...`);
    const py = checkPythonLangfuse();
    if (py.ok) {
      console.log(green(`✔ Python com 'langfuse' encontrado via: ${py.py}`));
    } else {
      console.log(yellow(`⚠ Biblioteca 'langfuse' não encontrada no interpretador padrão.`));
      console.log(`  Instale com: ${cyan('pip install "langfuse>=2.50.0"')}`);
    }

    console.log(`\n${bold(green('🎉 Instalação e configuração concluídas com sucesso!'))}`);
    console.log(`O plugin coletará métricas agregadas por Feature e subagentes a cada comando.\n`);

  } finally {
    rl.close();
  }
}

main().catch((err) => {
  console.error(red(`\nErro durante o setup: ${err.message}`));
  process.exit(1);
});
