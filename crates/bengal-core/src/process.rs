/// Configures process identity in system task monitors (htop, btop, top, GNOME System Monitor).
pub fn setup_process_identity(name: &str) {
    #[cfg(target_os = "linux")]
    unsafe {
        // Set /proc/self/comm (max 15 characters + null byte)
        let mut comm = [0u8; 16];
        let bytes = name.as_bytes();
        let len = bytes.len().min(15);
        comm[..len].copy_from_slice(&bytes[..len]);
        libc::prctl(libc::PR_SET_NAME, comm.as_ptr());
    }

    #[cfg(any(target_os = "freebsd", target_os = "openbsd", target_os = "netbsd"))]
    unsafe {
        use std::ffi::CString;
        if let Ok(c_name) = CString::new(name) {
            libc::setproctitle(b"%s\0".as_ptr() as *const libc::c_char, c_name.as_ptr());
        }
    }
}

/// Sets the name of the current thread (e.g. "bengal-worker")
pub fn set_thread_name(name: &str) {
    #[cfg(target_os = "linux")]
    unsafe {
        let mut comm = [0u8; 16];
        let bytes = name.as_bytes();
        let len = bytes.len().min(15);
        comm[..len].copy_from_slice(&bytes[..len]);
        libc::prctl(libc::PR_SET_NAME, comm.as_ptr());
    }

    #[cfg(any(target_os = "freebsd", target_os = "openbsd"))]
    unsafe {
        use std::ffi::CString;
        if let Ok(c_name) = CString::new(name) {
            libc::pthread_set_name_np(libc::pthread_self(), c_name.as_ptr());
        }
    }
}
