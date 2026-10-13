use std::process::Command;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum CompletionAction {
    #[default]
    None,
    QuitBengal,
    Sleep,
    Hibernate,
    Shutdown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueueScheduleConfig {
    pub name: String,
    pub max_concurrent: usize,
    pub enabled: bool,
    pub start_time: Option<String>,
    pub stop_time: Option<String>,
    pub days: [bool; 7],
    pub on_completion: CompletionAction,
}

impl Default for QueueScheduleConfig {
    fn default() -> Self {
        Self {
            name: "Default".to_string(),
            max_concurrent: 4,
            enabled: true,
            start_time: None,
            stop_time: None,
            days: [true; 7],
            on_completion: CompletionAction::None,
        }
    }
}

pub struct PowerManager;

impl PowerManager {
    /// Executes the system action when a queue completes or scheduled shutdown triggers.
    pub fn execute_action(action: CompletionAction) -> anyhow::Result<()> {
        match action {
            CompletionAction::None => Ok(()),
            CompletionAction::QuitBengal => {
                tracing::info!("Queue completed: exiting application gracefully");
                std::process::exit(0);
            }
            CompletionAction::Sleep => Self::sleep_system(),
            CompletionAction::Hibernate => Self::hibernate_system(),
            CompletionAction::Shutdown => Self::shutdown_system(),
        }
    }

    #[cfg(target_os = "linux")]
    pub fn sleep_system() -> anyhow::Result<()> {
        tracing::info!("Putting Linux system to sleep via systemctl...");
        let _ = Command::new("systemctl").arg("suspend").status()
            .or_else(|_| Command::new("loginctl").arg("suspend").status())?;
        Ok(())
    }

    #[cfg(target_os = "freebsd")]
    pub fn sleep_system() -> anyhow::Result<()> {
        tracing::info!("Putting FreeBSD system to sleep via acpiconf...");
        let _ = Command::new("acpiconf").args(["-s", "3"]).status()?;
        Ok(())
    }

    #[cfg(target_os = "windows")]
    pub fn sleep_system() -> anyhow::Result<()> {
        tracing::info!("Putting Windows system to sleep...");
        let _ = Command::new("rundll32.exe")
            .args(["powrprof.dll,SetSuspendState", "0,1,0"])
            .status()?;
        Ok(())
    }

    #[cfg(target_os = "macos")]
    pub fn sleep_system() -> anyhow::Result<()> {
        tracing::info!("Putting macOS system to sleep via pmset...");
        let _ = Command::new("pmset").arg("sleepnow").status()?;
        Ok(())
    }

    #[cfg(not(any(target_os = "linux", target_os = "freebsd", target_os = "windows", target_os = "macos")))]
    pub fn sleep_system() -> anyhow::Result<()> {
        anyhow::bail!("Sleep not implemented on this operating system");
    }

    #[cfg(target_os = "linux")]
    pub fn hibernate_system() -> anyhow::Result<()> {
        tracing::info!("Hibernating Linux system via systemctl...");
        let _ = Command::new("systemctl").arg("hibernate").status()
            .or_else(|_| Command::new("loginctl").arg("hibernate").status())?;
        Ok(())
    }

    #[cfg(not(target_os = "linux"))]
    pub fn hibernate_system() -> anyhow::Result<()> {
        anyhow::bail!("Hibernate not supported on this operating system");
    }

    #[cfg(target_os = "linux")]
    pub fn shutdown_system() -> anyhow::Result<()> {
        tracing::info!("Shutting down Linux system...");
        let _ = Command::new("systemctl").arg("poweroff").status()
            .or_else(|_| Command::new("shutdown").args(["-h", "now"]).status())?;
        Ok(())
    }

    #[cfg(target_os = "freebsd")]
    pub fn shutdown_system() -> anyhow::Result<()> {
        tracing::info!("Shutting down FreeBSD system...");
        let _ = Command::new("shutdown").args(["-p", "now"]).status()?;
        Ok(())
    }

    #[cfg(target_os = "windows")]
    pub fn shutdown_system() -> anyhow::Result<()> {
        tracing::info!("Shutting down Windows system...");
        let _ = Command::new("shutdown.exe").args(["/s", "/t", "0"]).status()?;
        Ok(())
    }

    #[cfg(target_os = "macos")]
    pub fn shutdown_system() -> anyhow::Result<()> {
        tracing::info!("Shutting down macOS system...");
        let _ = Command::new("osascript")
            .args(["-e", "tell app \"System Events\" to shut down"])
            .status()?;
        Ok(())
    }

    #[cfg(not(any(target_os = "linux", target_os = "freebsd", target_os = "windows", target_os = "macos")))]
    pub fn shutdown_system() -> anyhow::Result<()> {
        anyhow::bail!("Shutdown not supported on this operating system");
    }
}
