use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ShellError {
    #[error("本机数据目录不可用")]
    DataDirectoryUnavailable,
    #[error("桌面壳配置无效: {0}")]
    InvalidConfig(String),
    #[error("Hub 尚未就绪: {0}")]
    HubUnavailable(String),
    #[error("Hub 运行时描述符无效: {0}")]
    InvalidDescriptor(String),
    #[error("Hub 运行时描述符 ACL 不安全: {0}")]
    InsecureDescriptorAcl(String),
    #[error("本机凭据操作失败: {0}")]
    Credential(String),
    #[error("开机自启操作失败: {0}")]
    Autostart(String),
    #[error("窗口状态操作失败: {0}")]
    WindowState(String),
    #[error("内部错误: {0}")]
    Internal(String),
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CommandError {
    pub code: &'static str,
    pub message: String,
}

impl From<ShellError> for CommandError {
    fn from(value: ShellError) -> Self {
        let code = match &value {
            ShellError::DataDirectoryUnavailable => "DATA_DIRECTORY_UNAVAILABLE",
            ShellError::InvalidConfig(_) => "INVALID_SHELL_CONFIG",
            ShellError::HubUnavailable(_) => "HUB_UNAVAILABLE",
            ShellError::InvalidDescriptor(_) => "INVALID_RUNTIME_DESCRIPTOR",
            ShellError::InsecureDescriptorAcl(_) => "INSECURE_RUNTIME_DESCRIPTOR_ACL",
            ShellError::Credential(_) => "CREDENTIAL_STORE_ERROR",
            ShellError::Autostart(_) => "AUTOSTART_ERROR",
            ShellError::WindowState(_) => "WINDOW_STATE_ERROR",
            ShellError::Internal(_) => "SHELL_INTERNAL_ERROR",
        };
        Self {
            code,
            message: value.to_string(),
        }
    }
}

