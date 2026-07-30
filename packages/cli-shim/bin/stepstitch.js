#!/usr/bin/env node
/**
 * StepStitch launcher shim: `npx stepstitch <command>`.
 *
 * The engine is the `stepstitch-service` Python package (PyPI); this shim only finds a
 * runner for it. Zero npm dependencies by design — everything here is Node stdlib.
 *
 * Resolution order:
 *   1. `uvx` on PATH (or in uv's default install locations) — run the pinned service
 *      version through it. uv manages the Python; the developer needs nothing else.
 *   2. No uv found — print the exact, copyable commands to proceed. The shim installs
 *      uv itself ONLY with explicit consent (`--install-uv` flag or
 *      STEPSTITCH_AUTO_INSTALL=1), never silently: auto-downloading a package manager
 *      is a decision a developer (or their security team) should get to see.
 *
 * The service version is pinned in package.json (`stepstitch.serviceVersion`) so a shim
 * release always launches the engine it was tested with; STEPSTITCH_SERVICE_VERSION
 * overrides the pinned version, and STEPSTITCH_SERVICE_SPEC overrides the whole
 * `--from` spec (e.g. `./service` in CI, to test unreleased engines).
 *
 * The pin follows the release train: release-please rewrites both this package's
 * version and `stepstitch.serviceVersion` on every release, so the shim on npm and the
 * engine on PyPI always move together. (0.9.0 was the first engine release to ship the
 * `stepstitch` console script; nothing before it is launchable this way.)
 */
'use strict';

const { spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const pkg = require('../package.json');
const SERVICE_VERSION =
  process.env.STEPSTITCH_SERVICE_VERSION || pkg.stepstitch.serviceVersion;
const WINDOWS = process.platform === 'win32';

function findUvx() {
  const exe = WINDOWS ? 'uvx.exe' : 'uvx';
  const onPath = spawnSync(exe, ['--version'], { stdio: 'ignore', shell: false });
  if (!onPath.error && onPath.status === 0) return exe;
  const candidates = [
    path.join(os.homedir(), '.local', 'bin', exe),
    path.join(os.homedir(), '.cargo', 'bin', exe),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

function installUv() {
  // The official uv installers, run as fixed argv (no string interpolation).
  console.error('Installing uv (https://docs.astral.sh/uv/) ...');
  const result = WINDOWS
    ? spawnSync(
        'powershell',
        ['-ExecutionPolicy', 'ByPass', '-NoProfile', '-Command',
         'irm https://astral.sh/uv/install.ps1 | iex'],
        { stdio: 'inherit' })
    : spawnSync(
        'sh',
        ['-c', 'curl -LsSf https://astral.sh/uv/install.sh | sh'],
        { stdio: 'inherit' });
  return result.status === 0;
}

function main() {
  const argv = process.argv.slice(2);
  const wantsUvInstall = argv.includes('--install-uv');
  const args = argv.filter((a) => a !== '--install-uv');
  const autoConsent =
    wantsUvInstall || process.env.STEPSTITCH_AUTO_INSTALL === '1';

  let uvx = findUvx();
  if (!uvx && autoConsent) {
    if (!installUv()) {
      console.error('uv installation failed — see output above.');
      process.exit(1);
    }
    uvx = findUvx();
  }
  if (!uvx) {
    console.error(
      [
        'StepStitch needs uv (a small Python runner) and it is not installed.',
        '',
        'Either install it yourself:',
        WINDOWS
          ? '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
          : '  curl -LsSf https://astral.sh/uv/install.sh | sh',
        '',
        'or let this launcher do it (this downloads uv from astral.sh):',
        `  npx stepstitch ${args.join(' ') || 'start'} --install-uv`,
      ].join('\n'),
    );
    process.exit(1);
  }

  const spec =
    process.env.STEPSTITCH_SERVICE_SPEC || `stepstitch-service==${SERVICE_VERSION}`;
  const child = spawnSync(
    uvx,
    ['--from', spec, 'stepstitch', ...args],
    { stdio: 'inherit', shell: false },
  );
  if (child.error) {
    console.error(`failed to launch uvx: ${child.error.message}`);
    process.exit(1);
  }
  process.exit(child.status === null ? 1 : child.status);
}

main();
