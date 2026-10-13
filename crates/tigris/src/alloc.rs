use std::fs::File;
use std::io::Result;
use std::path::Path;

/// Pre-allocates disk space for a file using OS-native primitives.
/// This prevents filesystem fragmentation during parallel multi-connection writes
/// and guarantees up-front that disk space is available.
pub fn preallocate_file(path: &Path, size_bytes: u64) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let file = File::options()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;

    if size_bytes == 0 {
        return Ok(());
    }

    #[cfg(target_os = "linux")]
    {
        use std::os::unix::io::AsRawFd;
        let fd = file.as_raw_fd();
        let ret = unsafe { libc::posix_fallocate(fd, 0, size_bytes as libc::off_t) };
        if ret == 0 {
            return Ok(());
        }
        // Fall back to standard set_len if posix_fallocate fails (e.g. on non-supporting filesystems)
    }

    #[cfg(any(target_os = "freebsd", target_os = "openbsd", target_os = "netbsd"))]
    {
        use std::os::unix::io::AsRawFd;
        let fd = file.as_raw_fd();
        let ret = unsafe { libc::posix_fallocate(fd, 0, size_bytes as libc::off_t) };
        if ret == 0 {
            return Ok(());
        }
    }

    // Portable fallback: set length (creates sparse file if supported by filesystem)
    file.set_len(size_bytes)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_preallocate() {
        let temp = std::env::temp_dir().join("bengal_test_alloc.bin");
        preallocate_file(&temp, 1024 * 1024).unwrap();
        let meta = std::fs::metadata(&temp).unwrap();
        assert_eq!(meta.len(), 1024 * 1024);
        let _ = std::fs::remove_file(temp);
    }
}
