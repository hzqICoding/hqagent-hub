import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises'
import path from 'node:path'
const root = process.cwd()
const security = JSON.parse(await readFile(path.join(root,'apps/desktop/src-tauri/tauri.conf.json'),'utf8')).app.security
if (security.freezePrototype !== true) throw new Error('freezePrototype must remain enabled')
const assets = path.join(root, 'apps/desktop/dist/assets')
const files = (await readdir(assets)).filter(file=>file.endsWith('.js'))
const findings = []
for (const file of files) {
  const text = await readFile(path.join(assets,file),'utf8')
  if (/exports\.toString\s*=|Invalid mode:|Unknown mode:/.test(text)) findings.push(file)
}
const sourceFiles = []
async function scan(dir) { for(const entry of await readdir(dir,{withFileTypes:true})){const full=path.join(dir,entry.name);if(entry.isDirectory())await scan(full);else if(/\.(?:ts|vue)$/.test(entry.name)){const text=await readFile(full,'utf8');if(/(?:from\s*|import\s*\()["']qrcode["']/.test(text))sourceFiles.push(path.relative(root,full))}} }
await scan(path.join(root,'apps/desktop/src'))
const linkChunks = files.filter(file=>file.startsWith('RemoteLinkPage-'))
if (!linkChunks.length || findings.length || sourceFiles.length) throw new Error(JSON.stringify({findings,sourceFiles,linkChunks}))
const report = { freezePrototypeEnabled:security.freezePrototype, jsChunks:files.length,legacyModeAssignmentOrDiagnosticMatches:findings.length,legacyRuntimeSourceImports:sourceFiles.length,remoteLinkChunks:linkChunks }
const output = path.join(root,'.hqagent/handoffs/qr-freeze-validation')
await mkdir(output,{recursive:true});await writeFile(path.join(output,'production-audit.json'),JSON.stringify(report,null,2)+'\n')
console.log(JSON.stringify(report))
