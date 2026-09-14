# Platform-specific CMake Options and Targets for Windows
message(STATUS "[Options] Loading Windows build configuration...")

option(WINDOWS_BUNDLE_TOOLS "Auto-download Windows third-party binaries (aria2, yt-dlp, ffmpeg)" ON)
option(WINDOWS_BUILD_INSTALLER "Compile Inno Setup Windows installer (requires ISCC)" ON)
option(WINDOWS_BUILD_PORTABLE_ZIP "Create portable ZIP archive of standalone build" ON)

set(WINDOWS_CONFIG_DIR "${CMAKE_CURRENT_LIST_DIR}/../config")
set(WINDOWS_FIXES_DIR "${CMAKE_CURRENT_LIST_DIR}/../fixes")
set(WINDOWS_SCRIPTS_DIR "${CMAKE_CURRENT_LIST_DIR}/../build-scripts")
set(WINDOWS_BIN_DIR "${CMAKE_CURRENT_LIST_DIR}/../bin")

file(MAKE_DIRECTORY "${WINDOWS_BIN_DIR}")
file(MAKE_DIRECTORY "${DIST_DIR}/windows")

# ── Target: Download Windows Tools ──────────────────────────────────────────
add_custom_target(download_windows_tools
    COMMENT "Ensuring Windows helper binaries exist in ${WINDOWS_BIN_DIR}..."
    COMMAND ${CMAKE_COMMAND} -E echo "Checking third-party Windows binaries in ${WINDOWS_BIN_DIR}..."
)

# ── Target: Build Windows Executable via PyInstaller ────────────────────────
find_program(UV_EXECUTABLE uv)
find_program(PYINSTALLER_EXECUTABLE pyinstaller)

if(UV_EXECUTABLE)
    set(BUILD_CMD ${UV_EXECUTABLE} run pyinstaller --noconfirm --distpath "${DIST_DIR}" --workpath "${ROOT_DIR}/.pyinstaller-build" "${WINDOWS_CONFIG_DIR}/bengal-download-manager.spec")
elseif(PYINSTALLER_EXECUTABLE)
    set(BUILD_CMD ${PYINSTALLER_EXECUTABLE} --noconfirm --distpath "${DIST_DIR}" --workpath "${ROOT_DIR}/.pyinstaller-build" "${WINDOWS_CONFIG_DIR}/bengal-download-manager.spec")
else()
    set(BUILD_CMD python -m PyInstaller --noconfirm --distpath "${DIST_DIR}" --workpath "${ROOT_DIR}/.pyinstaller-build" "${WINDOWS_CONFIG_DIR}/bengal-download-manager.spec")
endif()

add_custom_target(build_windows
    COMMAND ${BUILD_CMD}
    WORKING_DIRECTORY "${ROOT_DIR}"
    COMMENT "Building Windows standalone executable using PyInstaller with native DWM theme fixes..."
)

# ── Target: Inno Setup Installer ─────────────────────────────────────────────
find_program(ISCC_EXECUTABLE iscc
    PATHS
    "C:/Program Files (x86)/Inno Setup 6"
    "C:/Program Files/Inno Setup 6"
)

if(ISCC_EXECUTABLE)
    add_custom_target(package_installer
        COMMAND ${ISCC_EXECUTABLE} /DAppVersion=${PROJECT_VERSION} "${WINDOWS_CONFIG_DIR}/installer.iss"
        DEPENDS build_windows
        WORKING_DIRECTORY "${WINDOWS_CONFIG_DIR}"
        COMMENT "Compiling Inno Setup Windows installer (BengalSetup-${PROJECT_VERSION}.exe)..."
    )
else()
    add_custom_target(package_installer
        COMMAND ${CMAKE_COMMAND} -E echo "ISCC (Inno Setup Compiler) not found on PATH. Skipping installer compilation."
    )
endif()

# ── Target: Portable Zip Archive ─────────────────────────────────────────────
add_custom_target(package_portable
    COMMAND ${CMAKE_COMMAND} -E tar "cfv" "${DIST_DIR}/windows/bengal-download-manager-${PROJECT_VERSION}-windows-x64.zip" --format=zip "${DIST_DIR}/bengal-download-manager"
    DEPENDS build_windows
    WORKING_DIRECTORY "${ROOT_DIR}"
    COMMENT "Generating portable Windows zip archive..."
)

add_custom_target(windows_release
    DEPENDS build_windows package_installer package_portable
    COMMENT "Windows release packaging pipeline complete."
)
