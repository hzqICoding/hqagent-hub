export const REMOTE_LINK_ERROR_MESSAGES: Record<string, string> = {
  // Remote Link and Pairing Errors
  REMOTE_SERVER_ORIGIN_INVALID: '服务器地址格式不正确，必须为 HTTPS 地址（本地测试可用 localhost 或 127.0.0.1）',
  REMOTE_SERVER_UNREACHABLE: '无法连接到远程服务器，请检查网络或地址是否正确',
  REMOTE_PAIRING_IN_PROGRESS: '已有配对请求正在进行中，请先取消或等待过期',
  REMOTE_PAIRING_EXPIRED: '配对短码已过期，请重新发起配对',
  REMOTE_PAIRING_CONFLICT: '该短码已被使用或设备已被绑定',
  REMOTE_PAIRING_INVALID: '配对短码无效，请检查后重新输入',
  REMOTE_DEVICE_OFFLINE: '电脑与云端服务器连接断开，当前处于离线状态',
  REMOTE_DEVICE_REVOKED: '该电脑设备已在服务器端被撤销',
  REMOTE_DEVICE_AUTH_FAILED: '电脑设备认证失败，请重新配对',
  REMOTE_EPOCH_STALE: '存储世代需要核对（状态已冻结），请联系管理员',
  REMOTE_STORE_CHANGED: 'Worker 本地存储已变更，请核对状态',
  REMOTE_PROTOCOL_UNSUPPORTED: '远程协议版本不兼容',
  CONVERSATION_AUTHORITY_MISMATCH: '这是手机远程对话，无法在电脑上进行写操作，请在手机上继续',
  REMOTE_APPROVAL_FORBIDDEN: '当前操作需要更高权限或需在电脑端确认',
  REMOTE_RATE_LIMITED: '请求过于频繁，请稍后重试',
  REMOTE_AUTH_REQUIRED: '需要登录认证',
  REMOTE_CSRF_REJECTED: '跨站请求凭据校验失败',

  // Common Hub Errors
  HUB_NOT_READY: '本地服务正在启动或尚未就绪',
  HUB_MAINTENANCE: '服务维护中',
  NOT_FOUND: '请求的资源不存在',
  CONFLICT: '操作冲突，请刷新后重试',
  BAD_REQUEST: '请求参数错误',
  VALIDATION_FAILED: '表单校验失败',
  UNAUTHORIZED: '未获得授权，请先登录',
  INTERNAL: '服务内部错误，请稍后重试',
}

export function getRemoteLinkErrorMessage(code?: string): string {
  if (!code) return '未知错误'
  return REMOTE_LINK_ERROR_MESSAGES[code] || `系统异常 (${code})`
}
