import { createHash, randomUUID } from 'node:crypto';
import { realpathSync } from 'node:fs';

const revision = 'hub-guard-v1';
const known = ['bash', 'edit', 'find', 'grep', 'ls', 'powershell', 'read', 'write'];
const readonly = ['find', 'grep', 'ls', 'read'];
const hash = value => createHash('sha256').update(value, 'utf8').digest('hex');
const stable = value => JSON.stringify(value, (_k, v) => v && !Array.isArray(v) && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const block = () => ({ block: true, reason: 'PI_TOOL_CALL_BLOCKED' });
const finite = v => typeof v === 'number' ? Number.isFinite(v) : (!v || typeof v !== 'object' || Object.values(v).every(finite));

export default function (pi) {
  let context;
  try { context = JSON.parse(process.env.HQAGENT_PI_GUARD_CONTEXT || '{}'); } catch { context = {}; }
  let ready = false, inventory = '', cwd = '', startKey = '', starting;
  const consumed = new Set();
  const safeShell = () => { const settings = pi.getSettings(); return !settings.shellPath && !settings.shellCommandPrefix; };
  const tools = () => stable({ all: pi.getAllTools(), active: [...pi.getActiveTools()].sort(), safeShell: safeShell() });
  const expected = context.readOnly ? readonly : known;
  async function dialog(ctx, title, payload, milliseconds) {
    let timer;
    try {
      return await Promise.race([
        ctx.ui.editor(title, JSON.stringify(payload)),
        new Promise(resolve => { timer = setTimeout(() => resolve(undefined), milliseconds); }),
      ]);
    } catch { return undefined; }
    finally { clearTimeout(timer); }
  }
  async function handshake(ctx) {
    ready = false;
    consumed.clear();
    if (ctx.mode !== 'rpc' || !ctx.hasUI || !context.sessionId || !context.nodeId || !context.policyRevision) return;
    if (!safeShell() || pi.getAllTools().some(t => t.sourceInfo?.source !== 'builtin' || t.sourceInfo?.path !== `builtin:${t.name}`)) return;
    const names = pi.getAllTools().map(t => t.name).sort();
    if (stable(names) !== stable(known)) return;
    pi.setActiveTools(expected);
    if (stable([...pi.getActiveTools()].sort()) !== stable(expected)) return;
    cwd = ctx.cwd;
    const normalize = p => process.platform === 'win32' ? realpathSync(p).toLowerCase() : realpathSync(p);
    if (normalize(cwd) !== normalize(context.cwd)) return;
    inventory = hash(tools());
    // RPC get_available_models reads a snapshot, unlike CLI --list-models.
    // Await PI's own local metadata refresh; never fetch keys or prompt here.
    await ctx.modelRegistry.refresh({ allowNetwork: false, signal: AbortSignal.timeout(5000) });
    const reply = await dialog(ctx, 'hqagent.guard.handshake.v1', {
      version: 1, sessionId: context.sessionId, guardRevision: revision,
      policyRevision: context.policyRevision, toolInventorySha256: inventory,
      isolation: 'hub_extension_only', activeTools: expected,
    }, 10000);
    ready = reply === 'ready' && inventory === hash(tools()) && cwd === ctx.cwd;
  }
  // PI binds session_start before it attaches its stdin line reader. Waiting
  // in that hook deadlocks editor responses; leave tools closed while it runs.
  pi.on('session_start', (_event, ctx) => {
    try {
      // PI 1.0.1 binds the replacement runtime inside switchSession and once
      // more in rpc-mode. Same extension + native binding is one handshake;
      // a replacement loads a fresh closure and must handshake again.
      const key = stable([ctx.sessionManager.getSessionId(), ctx.sessionManager.getSessionFile(), ctx.cwd]);
      if (starting && key === startKey && inventory === hash(tools())) return;
      startKey = key;
      starting = handshake(ctx).catch(() => { ready = false; });
    } catch { ready = false; }
  });
  async function checkTool(event, ctx) {
    if (!ready || cwd !== ctx.cwd) return block();
    let argumentsJson;
    try { if (!finite(event.input)) return block(); argumentsJson = JSON.stringify(event.input); } catch { return block(); }
    if (!event.input || Array.isArray(event.input) || typeof event.input !== 'object' || Buffer.byteLength(argumentsJson, 'utf8') > 65536) return block();
    const requestId = randomUUID();
    const payload = { version: 1, requestId, sessionId: context.sessionId, nodeId: context.nodeId,
      toolCallId: event.toolCallId, toolName: event.toolName, policyRevision: context.policyRevision,
      toolInventorySha256: hash(tools()), argumentsJson, argumentsSha256: hash(argumentsJson),
      expiresAt: new Date(Date.now() + 300000).toISOString() };
    const reply = await dialog(ctx, 'hqagent.guard.check.v1', payload, 300000);
    let decision;
    try { decision = JSON.parse(reply); } catch { return block(); }
    if (consumed.has(requestId)) return block();
    consumed.add(requestId);
    if (!ready || cwd !== ctx.cwd || inventory !== hash(tools()) || JSON.stringify(event.input) !== argumentsJson) return block();
    for (const key of ['requestId', 'sessionId', 'toolCallId', 'argumentsSha256', 'policyRevision']) {
      if (decision[key] !== payload[key]) return block();
    }
    const expiry = Date.parse(decision.expiresAt);
    if (!Number.isFinite(expiry) || expiry <= Date.now() || expiry > Date.parse(payload.expiresAt)) return block();
    return decision.decision === 'allow' && expected.includes(event.toolName) ? undefined : block();
  }
  pi.on('tool_call', async (event, ctx) => {
    try { return await checkTool(event, ctx); } catch { return block(); }
  });
}
