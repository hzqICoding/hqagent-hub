// Synthetic PI RPC runtime. Never contacts a provider or loads user configuration.
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const args = process.argv.slice(2);
if (args.includes('--version')) { console.log('1.0.1'); process.exit(0); }
const flag = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const mode = process.env.PI_FAKE_MODE || '';
if (!args.includes('--no-extensions') || flag('--mode') !== 'rpc' || args.filter(v => v === '-e').length !== 1) process.exit(2);
const names = ['bash', 'edit', 'find', 'grep', 'ls', 'powershell', 'read', 'write'];
const handlers = new Map(), ui = new Map();
let active = names.slice(), tools = names.map(name => ({ name, description: name, parameters: { type: 'object' }, sourceInfo: { source: 'builtin', path: 'builtin:' + name } }));
let sessionId = randomUUID(), sessionFile = path.join(flag('--session-dir'), sessionId + '.jsonl');
let last = '', context, turn = 0;
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
let model = { provider: flag('--provider') || 'synthetic', id: flag('--model') || process.env.PI_FAKE_DEFAULT || 'family/model', input: ['text', 'image'] };
const models = [{ provider: 'synthetic', id: 'family/model', input: ['text', 'image'] }, { provider: 'synthetic', id: 'other', input: ['text'] }];
const api = { on: (name, callback) => handlers.set(name, callback), getAllTools: () => tools, getSettings: () => mode === 'unsafe-shell' ? { shellCommandPrefix: 'synthetic-untrusted-prefix' } : {},
  getActiveTools: () => active, setActiveTools: names => { active = names.slice(); } };
context = { mode: 'rpc', hasUI: true, cwd: process.cwd(), ui: { editor: (title, prefill) => new Promise(resolve => {
  const id = randomUUID();
  ui.set(id, resolve);
  let body = JSON.parse(prefill);
  if (mode === 'bad-handshake' && title.endsWith('handshake.v1')) body.policyRevision = 'wrong';
  if (mode !== 'no-handshake') emit({ type: 'extension_ui_request', id, method: 'editor', title, prefill: JSON.stringify(body) });
}) } };
const guard = await import(pathToFileURL(flag('-e')).href);
guard.default(api);
// Deliberately run the hook before registering stdin, like PI 1.0.1.
await handlers.get('session_start')({}, context);
async function handleLine(line) {
  const request = JSON.parse(line);
  if (request.type === 'extension_ui_response') { ui.get(request.id)?.(request.value); ui.delete(request.id); return; }
  const respond = data => emit({ type: 'response', id: request.id, command: request.type, success: true, data });
  if (request.type === 'get_state') return respond({ sessionId, sessionFile, model, isStreaming: false, isCompacting: false, pendingMessageCount: 0 });
  if (request.type === 'get_available_models') return respond({ models });
  if (request.type === 'switch_session') {
    sessionFile = request.sessionPath;
    const saved = JSON.parse(fs.readFileSync(sessionFile, 'utf8'));
    sessionId = saved.id; turn = saved.turn || 0;
    if (mode === 'switch-model') model = models[1];
    await handlers.get('session_start')({}, context);
    return respond({ cancelled: false });
  }
  if (request.type === 'get_last_assistant_text') return respond({ text: last });
  if (request.type === 'abort') {
    respond({});
    emit({ type: 'agent_end' });
    if (mode !== 'no-settle') setTimeout(() => emit({ type: 'agent_settled' }), 40);
    return;
  }
  if (request.type !== 'prompt') return respond({});
  turn += 1;
  fs.writeFileSync(sessionFile, JSON.stringify({ id: sessionId, turn }));
  emit({ type: 'agent_start' });
  respond({ disposition: 'started' });
  if (mode === 'hold' || mode === 'no-settle' || mode === 'probe' && request.message.includes('long detailed visual analysis')) return;
  let decision;
  if (mode === 'dynamic-tool') tools.push({ name: 'new_tool' });
  if (process.env.PI_FAKE_TOOL) {
    const call = { toolName: process.env.PI_FAKE_TOOL, toolCallId: 'synthetic-call', input: JSON.parse(process.env.PI_FAKE_ARGS || '{}') };
    const pending = handlers.get('tool_call')(call, context);
    if (mode === 'tamper-arguments') call.input.path = '../outside';
    if (mode === 'nested-call') await handlers.get('tool_call')({toolName: 'read', toolCallId: 'nested-call', input: {path: '../outside'}}, context);
    decision = await pending;
  }
  const answers = JSON.parse(process.env.PI_FAKE_ANSWERS || '[]');
  const summary = decision?.block ? 'blocked' : answers[turn - 1] || 'synthetic final';
  last = JSON.stringify({ status: 'done', summary, changedFiles: [] });
  emit({ type: 'message_update', assistantMessageEvent: { type: 'text_delta', delta: 'synthetic progress' } });
  emit({ type: 'agent_end' });
  setTimeout(() => emit({ type: 'agent_settled' }), 40);
}
let buffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buffer += chunk;
  let end;
  while ((end = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, end).replace(/\r$/, ''); buffer = buffer.slice(end + 1);
    void handleLine(line);
  }
});
process.stdin.on('end', () => process.exit(0));
