import { ref } from 'vue'

export type ToastType = 'success' | 'warning' | 'danger' | 'info'

export interface ToastItem {
  id: string
  title?: string
  message: string
  type: ToastType
  duration?: number
}

const toasts = ref<ToastItem[]>([])

export function useToast() {
  function show(toast: Omit<ToastItem, 'id'>) {
    const id = 'toast_' + Math.random().toString(36).substring(2, 9)
    const item: ToastItem = {
      id,
      duration: 3500,
      ...toast,
    }
    toasts.value.push(item)

    if (item.duration && item.duration > 0) {
      setTimeout(() => {
        dismiss(id)
      }, item.duration)
    }

    return id
  }

  function success(message: string, title?: string) {
    return show({ message, title, type: 'success' })
  }

  function warning(message: string, title?: string) {
    return show({ message, title, type: 'warning' })
  }

  function danger(message: string, title?: string) {
    return show({ message, title, type: 'danger' })
  }

  function info(message: string, title?: string) {
    return show({ message, title, type: 'info' })
  }

  function dismiss(id: string) {
    const idx = toasts.value.findIndex((t) => t.id === id)
    if (idx !== -1) {
      toasts.value.splice(idx, 1)
    }
  }

  function clearAll() {
    toasts.value = []
  }

  return {
    toasts,
    show,
    success,
    warning,
    danger,
    info,
    dismiss,
    clearAll,
  }
}
