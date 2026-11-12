import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const PUBLIC_DIR = fileURLToPath(new URL('./public', import.meta.url))
const SERVICE_WORKER_ENTRY = fileURLToPath(new URL('./src/serviceWorker/sw.ts', import.meta.url))

/** Placeholder in the Service Worker bundle where the shell list and version are written (same name as declared in `src/serviceWorker/sw.ts`). */
const SHELL_PLACEHOLDER = '__WBS_SHELL__'

/**
 * Builds the Service Worker (`/sw.js`) (task #192, ADR-0028).
 *
 * Bundles `src/serviceWorker/sw.ts` as a second entry, writes into the resulting bundle
 * **the list of shell files (index.html, hashed assets, static files from public) and a version derived from their contents**,
 * and emits it as `sw.js`. If the contents change by even one byte, `sw.js` changes too,
 * so the browser notices the new version (the "new version notice" of ADR-0028).
 * No dependency (vite-plugin-pwa / workbox) is added, to avoid regenerating the lockfile.
 */
const serviceWorkerShell = (): Plugin => ({
  name: 'wbs-service-worker-shell',
  apply: 'build',
  // index.html is emitted by Vite's html plugin in generateBundle; run after it
  enforce: 'post',
  generateBundle(_options, bundle) {
    const entry = Object.values(bundle).find((item) => item.type === 'chunk' && item.isEntry && item.name === 'sw')
    if (!entry || entry.type !== 'chunk') {
      this.error('Service Worker entry (sw) not found in the bundle')
      return
    }
    // ⚠ The Service Worker is registered as a classic script; importing other chunks breaks it
    if (entry.imports.length > 0 || entry.dynamicImports.length > 0) {
      this.error(`Service Worker imports other chunks: ${[...entry.imports, ...entry.dynamicImports].join(', ')}`)
      return
    }
    if (!entry.code.includes(SHELL_PLACEHOLDER)) {
      this.error(`${SHELL_PLACEHOLDER} not found in the Service Worker bundle`)
      return
    }

    const hash = createHash('sha256')
    const urls: string[] = []
    for (const [fileName, item] of Object.entries(bundle).sort(([a], [b]) => a.localeCompare(b))) {
      if (item === entry || fileName.endsWith('.map')) continue
      urls.push(`/${fileName}`)
      hash.update(fileName)
      hash.update(item.type === 'chunk' ? item.code : item.source)
    }
    // Just in case. Without index.html in the list, the shell won't show when opened offline
    if (!urls.includes('/index.html')) urls.push('/index.html')
    for (const fileName of readdirSync(PUBLIC_DIR).sort()) {
      urls.push(`/${fileName}`)
      hash.update(fileName)
      hash.update(readFileSync(`${PUBLIC_DIR}/${fileName}`))
    }
    const shell = JSON.stringify({ version: hash.digest('hex').slice(0, 16), urls })

    delete bundle[entry.fileName]
    this.emitFile({
      type: 'asset',
      fileName: 'sw.js',
      source: entry.code.split(SHELL_PLACEHOLDER).join(`(${shell})`),
    })
  },
})

export default defineConfig({
  plugins: [react(), serviceWorkerShell()],
  build: {
    rolldownOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        sw: SERVICE_WORKER_ENTRY,
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
