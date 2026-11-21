# Platform-specific CMake Options and Targets for Linux
message(STATUS "[Linux] Configuring Linux build targets...")

option(LINUX_BUILD_STANDALONE "Build standalone Linux binary using PyInstaller" ON)
option(LINUX_BUILD_APPIMAGE "Package as AppImage" OFF)
option(LINUX_BUILD_FLATPAK "Build Flatpak bundle" OFF)
option(LINUX_BUILD_SNAP "Build Snap package" OFF)

set(APP_NAME "bengal-download-manager")
set(MAIN_SCRIPT "${ROOT_DIR}/src/main.py")
set(EXECUTABLE_NAME "${APP_NAME}")
set(SEP ":")

# Verify PyInstaller is installed in the current Python environment
execute_process(
    COMMAND ${Python3_EXECUTABLE} -m PyInstaller --version
    RESULT_VARIABLE PYINSTALLER_RESULT
    OUTPUT_QUIET
    ERROR_QUIET
)

if(NOT PYINSTALLER_RESULT EQUAL 0)
    message(FATAL_ERROR "PyInstaller is not installed in ${Python3_EXECUTABLE}. Run: ${Python3_EXECUTABLE} -m pip install pyinstaller")
endif()

set(WORK_BUILD_DIR "${CMAKE_BINARY_DIR}/build_pyinstaller")
set(SPEC_DIR "${CMAKE_BINARY_DIR}")
set(RUNTIME_ASSETS_DIR "${CMAKE_BINARY_DIR}/runtime_assets")

# Onedir bundle output: <dist>/<app>/ containing the executable + _internal/
set(ONEDIR_OUTPUT "${DIST_DIR}/${EXECUTABLE_NAME}/${EXECUTABLE_NAME}")

# Custom command that runs PyInstaller in --onedir mode
add_custom_command(
    OUTPUT "${ONEDIR_OUTPUT}"
    COMMAND bash "${ROOT_DIR}/scripts/prepare_runtime_assets.sh" "${RUNTIME_ASSETS_DIR}" "${CMAKE_SYSTEM_PROCESSOR}"
    COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${ROOT_DIR}/src"
            ${Python3_EXECUTABLE} -m PyInstaller
            --name "${APP_NAME}"
            --onedir
            --paths "${ROOT_DIR}/src"
            --collect-all core
            --collect-all ui
            --collect-all python_socks
            --add-data "${RUNTIME_ASSETS_DIR}${SEP}assets"
            --add-data "${ROOT_DIR}/VERSION${SEP}."
            --distpath "${DIST_DIR}"
            --workpath "${WORK_BUILD_DIR}"
            --specpath "${SPEC_DIR}"
            --noconfirm
            "${MAIN_SCRIPT}"
    DEPENDS "${MAIN_SCRIPT}"
    COMMENT "Building onedir bundle with PyInstaller (with clean runtime assets)..."
    WORKING_DIRECTORY "${ROOT_DIR}"
)

# Default ALL target: bengal-download-manager (for cmake --build .)
add_custom_target(
    ${APP_NAME} ALL
    DEPENDS "${ONEDIR_OUTPUT}"
)

# Target alias
add_custom_target(
    build_linux_binary
    DEPENDS "${ONEDIR_OUTPUT}"
)

# Install onedir bundle under lib/ and expose a launcher in bin/
install(DIRECTORY "${DIST_DIR}/${EXECUTABLE_NAME}/"
        DESTINATION "lib/${APP_NAME}"
        USE_SOURCE_PERMISSIONS)
install(CODE "
    file(WRITE \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/bin/${EXECUTABLE_NAME}\"
        \"#!/bin/sh\\nexec \\\"\${CMAKE_INSTALL_PREFIX}/lib/${APP_NAME}/${EXECUTABLE_NAME}\\\" \\\"\\\$@\\\"\\n\")
    file(CHMOD \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/bin/${EXECUTABLE_NAME}\"
        PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
                    GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
")

# Install VERSION file into share/bengal-download-manager
if(EXISTS "${ROOT_DIR}/VERSION")
    install(FILES "${ROOT_DIR}/VERSION"
            DESTINATION share/bengal-download-manager)
endif()

# Standard App ID for desktop and metainfo assets
set(FLATPAK_ID "bd.com.zihad.BengalDownloadManager")

# Install desktop entry
if(EXISTS "${ROOT_DIR}/flatpak/${FLATPAK_ID}.desktop")
    install(FILES "${ROOT_DIR}/flatpak/${FLATPAK_ID}.desktop"
            DESTINATION share/applications)
endif()

# Install AppStream metadata
if(EXISTS "${ROOT_DIR}/flatpak/${FLATPAK_ID}.metainfo.xml")
    install(FILES "${ROOT_DIR}/flatpak/${FLATPAK_ID}.metainfo.xml"
            DESTINATION share/metainfo)
endif()

# Install hicolor icons
foreach(s 16 32 48 64 128 256 512)
    if(EXISTS "${ROOT_DIR}/assets/icons/${s}x${s}.png")
        install(FILES "${ROOT_DIR}/assets/icons/${s}x${s}.png"
                DESTINATION "share/icons/hicolor/${s}x${s}/apps"
                RENAME "${FLATPAK_ID}.png")
    endif()
endforeach()

if(EXISTS "${ROOT_DIR}/assets/logo.svg")
    install(FILES "${ROOT_DIR}/assets/logo.svg"
            DESTINATION share/icons/hicolor/scalable/apps
            RENAME "${FLATPAK_ID}.svg")
endif()

# Optional packaging targets
add_custom_target(build_linux_appimage
    COMMAND bash "${ROOT_DIR}/scripts/build_appimage.sh"
    WORKING_DIRECTORY "${ROOT_DIR}"
    COMMENT "Building Linux AppImage package..."
)

add_custom_target(build_linux_flatpak
    COMMAND bash "${ROOT_DIR}/scripts/build_flatpak.sh"
    WORKING_DIRECTORY "${ROOT_DIR}"
    COMMENT "Building Flatpak package..."
)

add_custom_target(build_linux_snap
    COMMAND bash "${ROOT_DIR}/scripts/build_snap.sh"
    WORKING_DIRECTORY "${ROOT_DIR}"
    COMMENT "Building Snap package..."
)

add_custom_target(build_linux_deb_rpm
    COMMAND bash "${ROOT_DIR}/scripts/build_deb_rpm.sh"
    WORKING_DIRECTORY "${ROOT_DIR}"
    COMMENT "Building DEB and RPM packages..."
)

add_custom_target(build_linux_tarball
    COMMAND bash "${ROOT_DIR}/scripts/build_tarball.sh"
    WORKING_DIRECTORY "${ROOT_DIR}"
    COMMENT "Building portable tarball..."
)
