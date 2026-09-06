use crate::error::ShellError;

const TARGET_PREFIX: &str = "HQAgent-Hub/";
const MAX_SECRET_BYTES: usize = 2_560;

pub struct CredentialStore;

impl CredentialStore {
    pub const fn new() -> Self {
        Self
    }

    pub fn set(&self, name: &str, secret: &str) -> Result<(), ShellError> {
        validate_name(name)?;
        if secret.is_empty() || secret.len() > MAX_SECRET_BYTES {
            return Err(ShellError::Credential(
                "凭据必须为 1 到 2560 字节".into(),
            ));
        }
        set_platform_credential(&target(name), secret)
    }

    pub fn get(&self, name: &str) -> Result<Option<String>, ShellError> {
        validate_name(name)?;
        get_platform_credential(&target(name))
    }

    pub fn delete(&self, name: &str) -> Result<(), ShellError> {
        validate_name(name)?;
        delete_platform_credential(&target(name))
    }
}

fn target(name: &str) -> String {
    format!("{TARGET_PREFIX}{name}")
}

fn validate_name(name: &str) -> Result<(), ShellError> {
    if name.is_empty()
        || name.len() > 64
        || !name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
    {
        return Err(ShellError::Credential(
            "凭据名称只允许 1 到 64 个字母、数字、点、下划线或连字符".into(),
        ));
    }
    Ok(())
}

#[cfg(windows)]
fn set_platform_credential(target: &str, secret: &str) -> Result<(), ShellError> {
    use std::{mem::zeroed, os::windows::ffi::OsStrExt, ptr};
    use windows_sys::Win32::{
        Foundation::GetLastError,
        Security::Credentials::{
            CredWriteW, CREDENTIALW, CRED_PERSIST_LOCAL_MACHINE, CRED_TYPE_GENERIC,
        },
    };

    let mut target: Vec<u16> = std::ffi::OsStr::new(target)
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut username: Vec<u16> = "HQAgent-Hub".encode_utf16().chain(Some(0)).collect();
    let mut blob = secret.as_bytes().to_vec();
    let mut credential: CREDENTIALW = unsafe { zeroed() };
    credential.Type = CRED_TYPE_GENERIC;
    credential.TargetName = target.as_mut_ptr();
    credential.CredentialBlobSize = blob.len() as u32;
    credential.CredentialBlob = blob.as_mut_ptr();
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE;
    credential.UserName = username.as_mut_ptr();
    credential.Comment = ptr::null_mut();
    credential.TargetAlias = ptr::null_mut();

    if unsafe { CredWriteW(&credential, 0) } == 0 {
        return Err(ShellError::Credential(format!(
            "CredWriteW 失败，Windows 错误码 {}",
            unsafe { GetLastError() }
        )));
    }
    Ok(())
}

#[cfg(windows)]
fn get_platform_credential(target: &str) -> Result<Option<String>, ShellError> {
    use std::{os::windows::ffi::OsStrExt, ptr};
    use windows_sys::Win32::{
        Foundation::{GetLastError, ERROR_NOT_FOUND},
        Security::Credentials::{CredFree, CredReadW, CREDENTIALW, CRED_TYPE_GENERIC},
    };

    let target: Vec<u16> = std::ffi::OsStr::new(target)
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut credential: *mut CREDENTIALW = ptr::null_mut();
    if unsafe { CredReadW(target.as_ptr(), CRED_TYPE_GENERIC, 0, &mut credential) } == 0 {
        let error = unsafe { GetLastError() };
        if error == ERROR_NOT_FOUND {
            return Ok(None);
        }
        return Err(ShellError::Credential(format!(
            "CredReadW 失败，Windows 错误码 {error}"
        )));
    }
    if credential.is_null() {
        return Err(ShellError::Credential(
            "Credential Manager 返回了空凭据".into(),
        ));
    }
    let value = unsafe {
        let credential_ref = &*credential;
        let bytes = std::slice::from_raw_parts(
            credential_ref.CredentialBlob,
            credential_ref.CredentialBlobSize as usize,
        );
        String::from_utf8(bytes.to_vec())
    };
    unsafe { CredFree(credential.cast()) };
    value
        .map(Some)
        .map_err(|_| ShellError::Credential("Credential Manager 中的值不是 UTF-8".into()))
}

#[cfg(windows)]
fn delete_platform_credential(target: &str) -> Result<(), ShellError> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::{
        Foundation::{GetLastError, ERROR_NOT_FOUND},
        Security::Credentials::{CredDeleteW, CRED_TYPE_GENERIC},
    };

    let target: Vec<u16> = std::ffi::OsStr::new(target)
        .encode_wide()
        .chain(Some(0))
        .collect();
    if unsafe { CredDeleteW(target.as_ptr(), CRED_TYPE_GENERIC, 0) } == 0 {
        let error = unsafe { GetLastError() };
        if error != ERROR_NOT_FOUND {
            return Err(ShellError::Credential(format!(
                "CredDeleteW 失败，Windows 错误码 {error}"
            )));
        }
    }
    Ok(())
}

#[cfg(not(windows))]
fn set_platform_credential(_target: &str, _secret: &str) -> Result<(), ShellError> {
    Err(ShellError::Credential(
        "Phase 1 仅实现 Windows Credential Manager".into(),
    ))
}

#[cfg(not(windows))]
fn get_platform_credential(_target: &str) -> Result<Option<String>, ShellError> {
    Err(ShellError::Credential(
        "Phase 1 仅实现 Windows Credential Manager".into(),
    ))
}

#[cfg(not(windows))]
fn delete_platform_credential(_target: &str) -> Result<(), ShellError> {
    Err(ShellError::Credential(
        "Phase 1 仅实现 Windows Credential Manager".into(),
    ))
}

#[cfg(test)]
mod tests {
    use super::validate_name;

    #[test]
    fn credential_names_are_namespaced_and_restricted() {
        assert!(validate_name("openai.api-key").is_ok());
        assert!(validate_name("../Windows/Credential").is_err());
        assert!(validate_name("").is_err());
    }
}

