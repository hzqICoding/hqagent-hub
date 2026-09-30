const fs = require('node:fs');
const { createRequire } = require('node:module');
const { resolve } = require('node:path');
const { gzipSync } = require('node:zlib');
const local = createRequire(resolve('apps/desktop/package.json'));
const { transformSync } = createRequire(local.resolve('vite'))('esbuild');
const source = fs.readFileSync('apps/desktop/src/shared/attachments/sha256.ts', 'utf8');
const { code } = transformSync(source, { loader: 'ts', target: 'es2020', minify: true });
console.log(JSON.stringify({ implementation: 'FIPS 180-4 incremental SHA-256, original TypeScript', newDependencies: 0, sourceBytes: Buffer.byteLength(source), minifiedBytes: Buffer.byteLength(code), gzipBytes: gzipSync(code).length, chunkBytes: 65536 }));
