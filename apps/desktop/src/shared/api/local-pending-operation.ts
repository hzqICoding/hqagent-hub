import { getLocalChatGatewayMode } from './local-chat-provider'

interface PendingOperation {
  id: string
  payload: unknown
}

const cache = new Map<string, Record<string, PendingOperation>>()

function bucket(): [string, Record<string, PendingOperation>] {
  const name = `hqagent_pending_operations_${getLocalChatGatewayMode()}`
  let data = cache.get(name)
  if (!data) {
    try {
      data = JSON.parse(sessionStorage.getItem(name) || '{}')
    } catch {
      data = {}
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) data = {}
    cache.set(name, data)
  }
  return [name, data]
}

function persist(name: string, value: Record<string, PendingOperation>) {
  try { sessionStorage.setItem(name, JSON.stringify(value)) } catch { /* memory fallback */ }
}

export function pendingOperation<T>(identity: string, payload: T): { id: string; payload: T } {
  const [name, data] = bucket()
  if (!data[identity]) {
    data[identity] = { id: crypto.randomUUID(), payload }
    persist(name, data)
  }
  return data[identity] as { id: string; payload: T }
}

export function completeOperation(identity: string): void {
  const [name, data] = bucket()
  delete data[identity]
  persist(name, data)
}

export function definiteRejection(error: unknown): boolean {
  const status = (error as { status?: number })?.status
  return typeof status === 'number' && status >= 400 && status < 500 && status !== 408 && status !== 429
}
