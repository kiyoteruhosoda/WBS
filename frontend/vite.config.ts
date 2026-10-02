import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const PUBLIC_DIR = fileURLToPath(new URL('./public', import.meta.url))
const SERVICE_WORKER_ENTRY = fileURLToPath(new URL('./src/serviceWorker/sw.ts', import.meta.url))

/** Service Worker の束に、殻の一覧と版を書き込む目印（`src/serviceWorker/sw.ts` の宣言と同じ名前）。 */
const SHELL_PLACEHOLDER = '__WBS_SHELL__'

/**
 * Service Worker（`/sw.js`）を焼く（task #192・ADR-0028）。
 *
 * `src/serviceWorker/sw.ts` を 2 つ目の入口として束ね、出来上がった束に
 * **殻（index.html・ハッシュ付きの assets・public の静的ファイル）の一覧と、その中身から作った版**を
 * 書き込んで `sw.js` として出す。中身が 1 バイトでも変われば `sw.js` も変わるので、
 * ブラウザが新しい版に気付く（ADR-0028 の「新しい版の知らせ」）。
 * 依存（vite-plugin-pwa / workbox）を足さないのは、lockfile を作り直さずに済ませるため。
 */
const serviceWorkerShell = (): Plugin => ({
  name: 'wbs-service-worker-shell',
  apply: 'build',
  // index.html は Vite の html の部品が generateBundle で出す。それより後に回る
  enforce: 'post',
  generateBundle(_options, bundle) {
    const entry = Object.values(bundle).find((item) => item.type === 'chunk' && item.isEntry && item.name === 'sw')
    if (!entry || entry.type !== 'chunk') {
      this.error('Service Worker の入口（sw）が束に見当たりません')
      return
    }
    // ⚠ Service Worker は古典的なスクリプトとして登録する。ほかの束を import すると動かない
    if (entry.imports.length > 0 || entry.dynamicImports.length > 0) {
      this.error(`Service Worker が別の束を読んでいます: ${[...entry.imports, ...entry.dynamicImports].join(', ')}`)
      return
    }
    if (!entry.code.includes(SHELL_PLACEHOLDER)) {
      this.error(`Service Worker の束に ${SHELL_PLACEHOLDER} がありません`)
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
    // 念のため。index.html が一覧に無ければ、オフラインで開いたときに殻が出ない
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
