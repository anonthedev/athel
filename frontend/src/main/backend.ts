import { app } from 'electron'
import { spawn, type ChildProcess } from 'child_process'
import { join } from 'path'

const reportsDir = join(app.getPath('userData'), 'reports')

const HEALTH_URL = 'http://127.0.0.1:8000/health'

let backend: ChildProcess | null = null

async function isHealthy(): Promise<boolean> {
  try {
    const response = await fetch(HEALTH_URL)
    return response.ok
  } catch {
    return false
  }
}

async function waitUntilHealthy(): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt++) {
    if (await isHealthy()) return
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(`Backend did not respond at ${HEALTH_URL}`)
}

export async function startBackend(): Promise<void> {
  if (await isHealthy()) return

  if (app.isPackaged) {
    const binary = process.platform === 'win32' ? 'server.exe' : 'server'
    backend = spawn(join(process.resourcesPath, 'server', binary), [], {
      env: { ...process.env, DEEP_RESEARCH_REPORTS: reportsDir },
      stdio: 'ignore'
    })
  } else {
    const cwd = join(app.getAppPath(), '..', 'backend')
    backend = spawn(join(cwd, '.venv', 'bin', 'python'), [
      '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'
    ], { cwd, stdio: 'inherit' })
  }

  await waitUntilHealthy()
}

export function stopBackend(): void {
  if (backend && !backend.killed) backend.kill()
  backend = null
}