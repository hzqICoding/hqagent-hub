use std::path::Path;

use crate::error::ShellError;

#[cfg(windows)]
pub fn verify_private_file_acl(path: &Path) -> Result<(), ShellError> {
    use std::{ffi::c_void, os::windows::ffi::OsStrExt, ptr};
    use windows_sys::Win32::{
        // windows-sys 0.59：LocalFree 在 Foundation，不在 System::Memory；
        // ACCESS_ALLOWED_ACE_TYPE 在 System::SystemServices，不在 Security。
        Foundation::{CloseHandle, LocalFree, ERROR_SUCCESS, HANDLE},
        Security::{
            Authorization::{GetNamedSecurityInfoW, SE_FILE_OBJECT},
            EqualSid, GetAce, GetAclInformation, GetTokenInformation, AclSizeInformation,
            TokenUser, ACCESS_ALLOWED_ACE, ACE_HEADER,
            ACL_SIZE_INFORMATION, DACL_SECURITY_INFORMATION, INHERITED_ACE, OWNER_SECURITY_INFORMATION,
            TOKEN_QUERY, TOKEN_USER,
        },
        System::{
            SystemServices::ACCESS_ALLOWED_ACE_TYPE,
            Threading::{GetCurrentProcess, OpenProcessToken},
        },
    };

    struct HandleGuard(HANDLE);
    impl Drop for HandleGuard {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe { CloseHandle(self.0) };
            }
        }
    }

    struct LocalGuard(*mut c_void);
    impl Drop for LocalGuard {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe { LocalFree(self.0) };
            }
        }
    }

    let mut token: HANDLE = ptr::null_mut();
    if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) } == 0 {
        return Err(ShellError::InsecureDescriptorAcl(
            "无法读取当前用户访问令牌".into(),
        ));
    }
    let _token_guard = HandleGuard(token);

    let mut required = 0_u32;
    unsafe {
        GetTokenInformation(token, TokenUser, ptr::null_mut(), 0, &mut required);
    }
    if required == 0 {
        return Err(ShellError::InsecureDescriptorAcl(
            "无法读取当前用户 SID 长度".into(),
        ));
    }
    let mut token_info = vec![0_u8; required as usize];
    if unsafe {
        GetTokenInformation(
            token,
            TokenUser,
            token_info.as_mut_ptr().cast(),
            required,
            &mut required,
        )
    } == 0
    {
        return Err(ShellError::InsecureDescriptorAcl(
            "无法读取当前用户 SID".into(),
        ));
    }
    let current_user_sid = unsafe { (*(token_info.as_ptr().cast::<TOKEN_USER>())).User.Sid };

    let wide_path: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut owner_sid = ptr::null_mut();
    let mut dacl = ptr::null_mut();
    let mut security_descriptor = ptr::null_mut();
    let status = unsafe {
        GetNamedSecurityInfoW(
            wide_path.as_ptr(),
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
            &mut owner_sid,
            ptr::null_mut(),
            &mut dacl,
            ptr::null_mut(),
            &mut security_descriptor,
        )
    };
    if status != ERROR_SUCCESS {
        return Err(ShellError::InsecureDescriptorAcl(format!(
            "读取 DACL 失败，Windows 错误码 {status}"
        )));
    }
    let _descriptor_guard = LocalGuard(security_descriptor);

    if owner_sid.is_null() || unsafe { EqualSid(owner_sid, current_user_sid) } == 0 {
        return Err(ShellError::InsecureDescriptorAcl(
            "文件所有者不是当前用户".into(),
        ));
    }
    if dacl.is_null() {
        return Err(ShellError::InsecureDescriptorAcl(
            "文件存在允许所有人的空 DACL".into(),
        ));
    }

    let mut info = ACL_SIZE_INFORMATION {
        AceCount: 0,
        AclBytesInUse: 0,
        AclBytesFree: 0,
    };
    if unsafe {
        GetAclInformation(
            dacl,
            (&mut info as *mut ACL_SIZE_INFORMATION).cast(),
            std::mem::size_of::<ACL_SIZE_INFORMATION>() as u32,
            AclSizeInformation,
        )
    } == 0
    {
        return Err(ShellError::InsecureDescriptorAcl(
            "无法枚举 Descriptor DACL".into(),
        ));
    }

    let mut current_user_allow_count = 0_u32;
    for index in 0..info.AceCount {
        let mut ace = ptr::null_mut();
        if unsafe { GetAce(dacl, index, &mut ace) } == 0 || ace.is_null() {
            return Err(ShellError::InsecureDescriptorAcl(
                "无法读取 Descriptor ACE".into(),
            ));
        }
        let header = unsafe { &*(ace.cast::<ACE_HEADER>()) };
        // AceFlags 是 u8，windows-sys 把 INHERITED_ACE 定义成 u32，需显式窄化。
        // INHERITED_ACE == 0x10，在 u8 范围内，语义不变。
        if header.AceFlags & INHERITED_ACE as u8 != 0 {
            return Err(ShellError::InsecureDescriptorAcl(
                "Descriptor DACL 仍包含继承权限".into(),
            ));
        }
        // AceType 是 u8，ACCESS_ALLOWED_ACE_TYPE 定义为 u32(0)，需窄化比较。
        if header.AceType == ACCESS_ALLOWED_ACE_TYPE as u8 {
            let allowed = unsafe { &*(ace.cast::<ACCESS_ALLOWED_ACE>()) };
            // PSID 在 windows-sys 里是 *mut c_void；EqualSid 只读不写，
            // 这里的 const→mut 转换仅为满足签名。
            let sid = (&allowed.SidStart as *const u32).cast::<c_void>() as *mut c_void;
            if unsafe { EqualSid(sid, current_user_sid) } == 0 {
                return Err(ShellError::InsecureDescriptorAcl(
                    "Descriptor 向当前用户之外的主体授予了访问权限".into(),
                ));
            }
            current_user_allow_count += 1;
        }
    }

    if current_user_allow_count == 0 {
        return Err(ShellError::InsecureDescriptorAcl(
            "Descriptor 未向当前用户授予读取权限".into(),
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
pub fn verify_private_file_acl(path: &Path) -> Result<(), ShellError> {
    use std::os::unix::fs::PermissionsExt;
    let mode = std::fs::metadata(path)
        .map_err(|error| ShellError::InsecureDescriptorAcl(error.to_string()))?
        .permissions()
        .mode();
    if mode & 0o077 != 0 {
        return Err(ShellError::InsecureDescriptorAcl(
            "Descriptor 对组或其他用户可读".into(),
        ));
    }
    Ok(())
}

#[cfg(windows)]
pub fn process_matches_executable(pid: u32, expected: &Path) -> bool {
    use std::{os::windows::ffi::OsStringExt, ptr};
    use windows_sys::Win32::{
        Foundation::{CloseHandle, STILL_ACTIVE},
        System::Threading::{
            GetExitCodeProcess, OpenProcess, QueryFullProcessImageNameW,
            PROCESS_QUERY_LIMITED_INFORMATION,
        },
    };

    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if handle.is_null() {
        return false;
    }
    let mut exit_code = 0_u32;
    // STILL_ACTIVE 在 windows-sys 里是 i32（259），退出码是 u32。
    let active = unsafe { GetExitCodeProcess(handle, &mut exit_code) } != 0
        && exit_code == STILL_ACTIVE as u32;
    let mut buffer = vec![0_u16; 32_768];
    let mut length = buffer.len() as u32;
    let queried = unsafe {
        QueryFullProcessImageNameW(handle, 0, buffer.as_mut_ptr(), &mut length)
    } != 0;
    unsafe { CloseHandle(handle) };
    if !active || !queried {
        return false;
    }
    buffer.truncate(length as usize);
    let actual = std::ffi::OsString::from_wide(&buffer);
    paths_equal_case_insensitive(Path::new(&actual), expected)
}

#[cfg(windows)]
fn paths_equal_case_insensitive(left: &Path, right: &Path) -> bool {
    let left = left.canonicalize().unwrap_or_else(|_| left.to_path_buf());
    let right = right.canonicalize().unwrap_or_else(|_| right.to_path_buf());
    left.as_os_str()
        .to_string_lossy()
        .eq_ignore_ascii_case(&right.as_os_str().to_string_lossy())
}

#[cfg(not(windows))]
pub fn process_matches_executable(pid: u32, expected: &Path) -> bool {
    let executable = std::fs::read_link(format!("/proc/{pid}/exe"));
    executable
        .ok()
        .and_then(|path| path.canonicalize().ok())
        == expected.canonicalize().ok()
}


#[cfg(all(test, windows))]
mod tests {
    use std::process::Command;

    use super::verify_private_file_acl;

    /// 当前用户的 `域\用户名`，与 icacls 接受的主体格式一致。
    fn current_principal() -> String {
        let domain = std::env::var("USERDOMAIN").expect("USERDOMAIN");
        let user = std::env::var("USERNAME").expect("USERNAME");
        format!("{domain}\\{user}")
    }

    fn icacls(args: &[&str]) {
        let output = Command::new("icacls.exe")
            .args(args)
            .output()
            .expect("运行 icacls");
        assert!(
            output.status.success(),
            "icacls {:?} 失败: {}",
            args,
            String::from_utf8_lossy(&output.stderr)
        );
    }

    /// 造一个符合 FZ-1 契约的描述符文件：去继承、只授当前用户。
    fn locked_down_file() -> (tempfile::TempDir, std::path::PathBuf) {
        let dir = tempfile::tempdir().expect("临时目录");
        let path = dir.path().join("hub.json");
        std::fs::write(&path, b"{}").expect("写文件");
        let path_str = path.to_string_lossy().to_string();
        icacls(&[&path_str, "/inheritance:r"]);
        icacls(&[
            &path_str,
            "/grant:r",
            &format!("{}:(F)", current_principal()),
        ]);
        (dir, path)
    }

    #[test]
    fn accepts_current_user_only_acl() {
        let (_dir, path) = locked_down_file();
        verify_private_file_acl(&path).expect("仅授当前用户的 ACL 必须通过");
    }

    #[test]
    fn rejects_inherited_acl() {
        // 不做 /inheritance:r，文件从临时目录继承 ACE。
        let dir = tempfile::tempdir().expect("临时目录");
        let path = dir.path().join("hub.json");
        std::fs::write(&path, b"{}").expect("写文件");

        let error = verify_private_file_acl(&path)
            .expect_err("带继承权限的描述符必须被拒绝");
        assert!(
            error.to_string().contains("继承"),
            "拒绝原因应指明继承权限，实际: {error}"
        );
    }

    #[test]
    fn rejects_additional_principal() {
        let (_dir, path) = locked_down_file();
        let path_str = path.to_string_lossy().to_string();
        // *S-1-1-0 是 Everyone 的知名 SID，用 SID 而非本地化名称，避免中文系统上匹配不到。
        icacls(&[&path_str, "/grant", "*S-1-1-0:(R)"]);

        let error = verify_private_file_acl(&path)
            .expect_err("向 Everyone 授权后必须被拒绝");
        assert!(
            error.to_string().contains("当前用户之外"),
            "拒绝原因应指明存在其他主体，实际: {error}"
        );
    }
}
