use std::path::PathBuf;

/// Centralized cross-platform application path resolver.
/// Strictly implements the FreeDesktop XDG Base Directory Specification on Linux & BSD,
/// Apple Library standards on macOS, and Known Folders on Windows.
pub struct AppPaths;

impl AppPaths {
    /// Returns the configuration directory for Bengal Download Manager.
    pub fn config_dir() -> PathBuf {
        #[cfg(target_os = "windows")]
        {
            dirs::config_dir()
                .map(|p| p.join("Bengal Download Manager").join("config"))
                .unwrap_or_else(|| PathBuf::from("config"))
        }
        #[cfg(target_os = "macos")]
        {
            dirs::data_dir()
                .map(|p| p.join("Bengal Download Manager").join("config"))
                .unwrap_or_else(|| PathBuf::from("config"))
        }
        #[cfg(not(any(target_os = "windows", target_os = "macos")))]
        {
            // Strictly adheres to XDG Base Directory Specification
            std::env::var_os("XDG_CONFIG_HOME")
                .map(PathBuf::from)
                .filter(|p| p.is_absolute())
                .or_else(|| dirs::home_dir().map(|h| h.join(".config")))
                .map(|p| p.join("bengal"))
                .unwrap_or_else(|| PathBuf::from(".config/bengal"))
        }
    }

    /// Returns the data storage directory (where downloads.db and state reside).
    pub fn data_dir() -> PathBuf {
        #[cfg(target_os = "windows")]
        {
            dirs::data_local_dir()
                .map(|p| p.join("Bengal Download Manager").join("data"))
                .unwrap_or_else(|| PathBuf::from("data"))
        }
        #[cfg(target_os = "macos")]
        {
            dirs::data_dir()
                .map(|p| p.join("Bengal Download Manager").join("data"))
                .unwrap_or_else(|| PathBuf::from("data"))
        }
        #[cfg(not(any(target_os = "windows", target_os = "macos")))]
        {
            std::env::var_os("XDG_DATA_HOME")
                .map(PathBuf::from)
                .filter(|p| p.is_absolute())
                .or_else(|| dirs::home_dir().map(|h| h.join(".local/share")))
                .map(|p| p.join("bengal"))
                .unwrap_or_else(|| PathBuf::from(".local/share/bengal"))
        }
    }

    /// Returns the cache directory for temporary chunk data and metadata.
    pub fn cache_dir() -> PathBuf {
        #[cfg(target_os = "windows")]
        {
            dirs::cache_dir()
                .map(|p| p.join("Bengal Download Manager").join("cache"))
                .unwrap_or_else(|| PathBuf::from("cache"))
        }
        #[cfg(target_os = "macos")]
        {
            dirs::cache_dir()
                .map(|p| p.join("Bengal Download Manager"))
                .unwrap_or_else(|| PathBuf::from("cache"))
        }
        #[cfg(not(any(target_os = "windows", target_os = "macos")))]
        {
            std::env::var_os("XDG_CACHE_HOME")
                .map(PathBuf::from)
                .filter(|p| p.is_absolute())
                .or_else(|| dirs::home_dir().map(|h| h.join(".cache")))
                .map(|p| p.join("bengal"))
                .unwrap_or_else(|| PathBuf::from(".cache/bengal"))
        }
    }

    /// Returns the runtime directory for ephemeral sockets and locks.
    pub fn runtime_dir() -> PathBuf {
        #[cfg(target_os = "windows")]
        {
            dirs::data_local_dir()
                .map(|p| p.join("Bengal Download Manager"))
                .unwrap_or_else(|| PathBuf::from("."))
        }
        #[cfg(not(target_os = "windows"))]
        {
            std::env::var_os("XDG_RUNTIME_DIR")
                .map(PathBuf::from)
                .filter(|p| p.is_absolute())
                .unwrap_or_else(std::env::temp_dir)
        }
    }

    /// Returns the path to the IPC domain socket.
    pub fn socket_path() -> PathBuf {
        #[cfg(target_os = "windows")]
        {
            PathBuf::from(r"\\.\pipe\bengal-ipc")
        }
        #[cfg(not(target_os = "windows"))]
        {
            Self::runtime_dir().join("bengal.sock")
        }
    }

    /// Returns the default user Downloads directory.
    pub fn default_download_dir() -> PathBuf {
        dirs::download_dir().unwrap_or_else(|| {
            dirs::home_dir()
                .map(|h| h.join("Downloads"))
                .unwrap_or_else(|| PathBuf::from("."))
        })
    }

    /// Returns the absolute path to the SQLite downloads database.
    pub fn database_path() -> PathBuf {
        Self::data_dir().join("downloads.db")
    }

    /// Ensures that all essential runtime directories exist on the filesystem.
    pub fn ensure_dirs() -> std::io::Result<()> {
        std::fs::create_dir_all(Self::config_dir())?;
        std::fs::create_dir_all(Self::data_dir())?;
        std::fs::create_dir_all(Self::cache_dir())?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_paths_not_empty() {
        assert!(!AppPaths::config_dir().as_os_str().is_empty());
        assert!(!AppPaths::data_dir().as_os_str().is_empty());
        assert!(!AppPaths::cache_dir().as_os_str().is_empty());
        assert!(!AppPaths::database_path().as_os_str().is_empty());
    }
}
