import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import { mkdir, writeFile } from 'node:fs/promises'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const desktop = path.join(root, 'apps/desktop')
const { build } = await import(pathToFileURL(path.join(desktop, 'node_modules/vite/dist/node/index.js')).href)
const outDir = path.join(root, '.tmp/qr-freeze-browser')
await mkdir(outDir, { recursive: true })
await build({
  root: desktop, configFile: path.join(desktop, 'vite.config.ts'), mode: 'production',
  define: { 'import.meta.env.VITE_GATEWAY_MODE': JSON.stringify('mock') },
  plugins: [{ name: 'frozen-module-audit', generateBundle() {
    const modules = [...this.getModuleIds()].map(id=>id.replaceAll('\\','/'))
    const forbidden = modules.filter(id=>/[/]node_modules[/](?:\.pnpm[/][^/]+[/]node_modules[/])?qrcode[/]/.test(id))
    if (forbidden.length) this.error('Legacy QR dependency entered the frozen production graph')
    this.emitFile({type:'asset',fileName:'module-audit.json',source:JSON.stringify({legacyQrModules:forbidden.length,moduleCount:modules.length,uqrIncluded:modules.some(id=>/[/]uqr[/]/.test(id))},null,2)})
  }}],
  build: { outDir, emptyOutDir: true, sourcemap: false, rollupOptions: {
    input: path.join(desktop, 'src/shared/testing/frozen-prototypes.browser.ts'),
    preserveEntrySignatures: 'strict', output: { entryFileNames: 'frozen-smoke.js' },
  } },
})
// Freeze before any module dependencies (including bundler-hoisted imports) evaluate.
await writeFile(path.join(outDir, 'index.html'), `<!doctype html><meta charset="utf-8"><title>Frozen prototype regression</title>
<script>Object.freeze(Object.prototype);Object.freeze(Function.prototype);Object.freeze(Array.prototype);</script>
<script type="module">
try { const {runFrozenPrototypeRegression}=await import('./frozen-smoke.js');window.__freezeResult={ok:true,result:await runFrozenPrototypeRegression()}; }
catch(error){window.__freezeResult={ok:false,error:String(error),stack:error?.stack};}
</script>`, 'utf8')
console.log('Frozen production fixture prepared in worktree .tmp')
