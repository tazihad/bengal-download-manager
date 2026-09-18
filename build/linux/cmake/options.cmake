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

# Custom command that runs PyInstaller to build dist/bengal-download-manager
add_custom_command(
    OUTPUT "${DIST_DIR}/${EXECUTABLE_NAME}"
    COMMAND bash "${ROOT_DIR}/scripts/prepare_runtime_assets.sh" "${RUNTIME_ASSETS_DIR}" "${CMAKE_SYSTEM_PROCESSOR}"
    COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${ROOT_DIR}/src"
            ${Python3_EXECUTABLE} -m PyInstaller
            --name "${APP_NAME}"
            --onefile
            --paths "${ROOT_DIR}/src"
            --collect-all core
            --collect-all ui
            --collect-all python_socks
            --add-data "${RUNTIME_ASSETS_DIR}${SEP}assets"
            --distpath "${DIST_DIR}"
            --workpath "${WORK_BUILD_DIR}"
            --specpath "${SPEC_DIR}"
            --noconfirm
            "${MAIN_SCRIPT}"
    DEPENDS "${MAIN_SCRIPT}"
    COMMENT "Building standalone executable with PyInstaller (with clean runtime assets)..."
    WORKING_DIRECTORY "${ROOT_DIR}"
)

# Default ALL target: bengal-download-manager (for cmake --build .)
add_custom_target(
    ${APP_NAME} ALL
    DEPENDS "${DIST_DIR}/${EXECUTABLE_NAME}"
)

# Target alias
add_custom_target(
    build_linux_binary
    DEPENDS "${DIST_DIR}/${EXECUTABLE_NAME}"
)

# Install target
install(PROGRAMS "${DIST_DIR}/${EXECUTABLE_NAME}" DESTINATION bin)

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
