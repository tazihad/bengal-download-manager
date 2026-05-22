cmake_minimum_required(VERSION 3.12)

# We use LANGUAGES NONE because this is a Python project, not C/C++
project(BengalDownloadManager LANGUAGES NONE)

# Find the Python3 interpreter
find_package(Python3 COMPONENTS Interpreter REQUIRED)

# Verify that PyInstaller is installed in the current Python environment
execute_process(
    COMMAND ${Python3_EXECUTABLE} -m PyInstaller --version
    RESULT_VARIABLE PYINSTALLER_RESULT
    OUTPUT_QUIET
    ERROR_QUIET
)

if(NOT PYINSTALLER_RESULT EQUAL 0)
    message(FATAL_ERROR "PyInstaller is not installed. Please run: ${Python3_EXECUTABLE} -m pip install pyinstaller")
endif()

# Configuration variables
set(APP_NAME "bengal-download-manager")
set(MAIN_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/src/main.py")

# Determine the correct executable suffix and path separator based on the OS
if(WIN32)
    set(EXECUTABLE_NAME "${APP_NAME}.exe")
    set(SEP ";")
else()
    set(EXECUTABLE_NAME "${APP_NAME}")
    set(SEP ":")
endif()

# Define output directories strictly inside the CMake binary dir (keeps source tree clean)
set(DIST_DIR "${CMAKE_CURRENT_BINARY_DIR}/dist")
set(BUILD_DIR "${CMAKE_CURRENT_BINARY_DIR}/build")
set(SPEC_DIR "${CMAKE_CURRENT_BINARY_DIR}")

# Define the custom command that actually runs PyInstaller
add_custom_command(
    OUTPUT "${DIST_DIR}/${EXECUTABLE_NAME}"
    COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/src"
            ${Python3_EXECUTABLE} -m PyInstaller
            --name "${APP_NAME}"
            --onefile
            --paths "${CMAKE_CURRENT_SOURCE_DIR}/src"
            --collect-all core
            --collect-all ui
            --add-data "${CMAKE_CURRENT_SOURCE_DIR}/assets${SEP}assets"
            # Optional: Add --windowed here if you want to hide the console window on Windows/macOS
            --distpath "${DIST_DIR}"
            --workpath "${BUILD_DIR}"
            --specpath "${SPEC_DIR}"
            --noconfirm
            "${MAIN_SCRIPT}"
    # Depend on all source files so CMake knows when to rebuild
    DEPENDS "${MAIN_SCRIPT}"
    COMMENT "Building standalone executable with PyInstaller (with PYTHONPATH=src)..."
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

# Create a target that triggers the custom command
add_custom_target(
    ${APP_NAME} ALL
    DEPENDS "${DIST_DIR}/${EXECUTABLE_NAME}"
)

# Optional: Add an install step (e.g., when you run `cmake --install .`)
install(PROGRAMS "${DIST_DIR}/${EXECUTABLE_NAME}" DESTINATION bin)