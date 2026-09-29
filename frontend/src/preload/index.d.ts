import { ElectronAPI } from '@electron-toolkit/preload'

interface DesktopApi {
  openReportsFolder: () => Promise<void>
}

declare global {
  interface Window {
    electron: ElectronAPI
    api: DesktopApi
  }
}
