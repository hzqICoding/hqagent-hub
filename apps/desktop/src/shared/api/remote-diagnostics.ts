import { shallowRef } from 'vue'

// Diagnostics only: never retain response bodies, headers, credentials or request inputs.
export const lastRemoteFailureRequestId = shallowRef<string | null>(null)
export const remoteRequestFailure = shallowRef<{
  endpoint: string; method: string; message: string; requestId?: string
} | null>(null)

export function recordRemoteFailure(endpoint: string, method: string, message: string, requestId?: string): void {
  lastRemoteFailureRequestId.value = requestId || null
  remoteRequestFailure.value = { endpoint, method, message, requestId }
}

export function clearRemoteFailureFor(endpoint: string, method: string): void {
  if (remoteRequestFailure.value?.endpoint === endpoint && remoteRequestFailure.value.method === method) {
    remoteRequestFailure.value = null
  }
}
