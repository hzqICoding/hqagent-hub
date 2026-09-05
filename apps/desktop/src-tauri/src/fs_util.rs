use std::{
    fs::{self, File},
    io::{self, Write},
    path::Path,
};

pub fn atomic_write(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "path has no parent"))?;
    fs::create_dir_all(parent)?;

    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "invalid file name"))?;
    let tmp = parent.join(format!(".{file_name}.tmp-{}", std::process::id()));

    let mut file = File::create(&tmp)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);

    replace_file(&tmp, path)
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::{
        Foundation::GetLastError,
        Storage::FileSystem::{MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH},
    };

    let source: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination: Vec<u16> = destination.as_os_str().encode_wide().chain(Some(0)).collect();
    let result = unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        return Err(io::Error::from_raw_os_error(unsafe { GetLastError() } as i32));
    }
    Ok(())
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> io::Result<()> {
    fs::rename(source, destination)
}

#[cfg(test)]
mod tests {
    use super::atomic_write;

    #[test]
    fn atomic_write_replaces_existing_content() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("state.json");
        atomic_write(&path, b"first").expect("first write");
        atomic_write(&path, b"second").expect("second write");
        assert_eq!(std::fs::read(path).expect("read"), b"second");
    }
}

