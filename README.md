# Bengal Download Manager

Bengal Download Manager is a powerful and efficient download management tool designed to simplify and accelerate your downloading experience.

## Screenshots
<img width="800" alt="Screenshot_20260427_193142" src="https://github.com/user-attachments/assets/e9346302-548c-4898-8122-b5dd1507a2f2" />


## Features

- **Multi-threaded Downloads:** Download files in multiple parts simultaneously, significantly increasing download speeds.
- **Pause and Resume:** Conveniently pause and resume downloads at any time, even after system restarts.
- **Scheduled Downloads:** Plan your downloads to start at a specific time, optimizing your bandwidth usage.
- **Bandwidth Limiting:** Control your download and upload speeds to prevent network congestion.
- **Categorization:** Organize your downloads into different categories for easy management.
- **Browser Integration:** Seamlessly integrate with popular web browsers to capture download links automatically.
- **Error Recovery:** Automatically retry failed downloads due to network issues or other interruptions.
- **User-friendly Interface:** An intuitive and clean interface makes managing your downloads a breeze.

## Installation

### Windows

1. Download the latest installer from the [releases page](https://github.com/tazihad/bengal-download-manager/releases).
2. Run the installer and follow the on-screen instructions.

### macOS

1. Download the `.dmg` file from the [releases page](https://github.com/tazihad/bengal-download-manager/releases).
2. Open the `.dmg` file and drag the Bengal Download Manager application to your Applications folder.

### Linux

1. Download the `.deb` or `.rpm` package from the [releases page](https://github.com/tazihad/bengal-download-manager/releases).
2. Install the package using your distribution's package manager:
   - For Debian/Ubuntu: `sudo dpkg -i bengal-download-manager.deb`
   - For Fedora/RHEL: `sudo rpm -i bengal-download-manager.rpm`
3. Alternatively, you can build from source:
   ```bash
   git clone https://github.com/tazihad/bengal-download-manager.git
   cd bengal-download-manager
   # Follow build instructions in CONTRIBUTING.md
   ```
   
   ```sh
   pip install -r requirements.txt
   cmake -S . -B build
   cmake --build build
   ```
   After it finishes, your executable will be located in `build/dist/`
   
