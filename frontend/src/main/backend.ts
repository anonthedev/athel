import { app } from 'electron'
import { spawn, type ChildProcess } from 'child_process'
import { join } from 'path'

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

  const cwd = join(app.getAppPath(), '..', 'backend')
  const python = join(cwd, '.venv', 'bin', 'python')

  backend = spawn(
    python,
    ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'],
    { cwd, stdio: 'inherit' }
  )

  backend.on('error', (error) => {
    console.error(error)
  })

  await waitUntilHealthy()
}

export function stopBackend(): void {
  if (backend && !backend.killed) backend.kill()
  backend = null
}