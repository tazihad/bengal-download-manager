cmake_minimum_required(VERSION 3.20)
project(bengal-download-manager
    VERSION 0.3.0
    LANGUAGES C CXX
    DESCRIPTION "High-performance multi-platform download manager built with Rust, egui, and Tigris engine"
)

# 1. Enforce out-of-source builds
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_BINARY_DIR)
    message(FATAL_ERROR "In-source builds are forbidden. Run: cmake -B build && cmake --build build")
endif()

# 2. Locate Rust toolchain
find_program(CARGO_EXECUTABLE cargo REQUIRED)
find_program(RUSTC_EXECUTABLE rustc REQUIRED)

# 3. Target Architecture Configuration (x86_64, aarch64, riscv64)
set(RUST_TARGET "" CACHE STRING "Cross-compilation target triplet (e.g. x86_64-unknown-linux-gnu, aarch64-unknown-linux-gnu, riscv64gc-unknown-linux-gnu, x86_64-unknown-freebsd)")

# 4. Build Profile
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    set(CARGO_RELEASE_FLAG "")
    set(CARGO_SUBDIR "debug")
else()
    set(CARGO_RELEASE_FLAG "--release")
    set(CARGO_SUBDIR "release")
endif()

# 5. Out-of-source directories (strictly inside build directory)
set(CARGO_TARGET_DIR "${CMAKE_BINARY_DIR}/target")
set(BENGAL_BIN_OUTPUT_DIR "${CMAKE_BINARY_DIR}/bin")
file(MAKE_DIRECTORY "${BENGAL_BIN_OUTPUT_DIR}")

# 6. Target architecture arguments
if(RUST_TARGET)
    set(CARGO_TARGET_ARGS "--target" "${RUST_TARGET}")
    set(BINARY_SOURCE_DIR "${CARGO_TARGET_DIR}/${RUST_TARGET}/${CARGO_SUBDIR}")
    message(STATUS "Configured cross-compilation target: ${RUST_TARGET}")
else()
    set(CARGO_TARGET_ARGS "")
    set(BINARY_SOURCE_DIR "${CARGO_TARGET_DIR}/${CARGO_SUBDIR}")
    message(STATUS "Configured native compilation for host: ${CMAKE_SYSTEM_NAME}")
endif()

# 7. Executable extension
if(WIN32 OR (RUST_TARGET MATCHES "windows"))
    set(EXE_SUFFIX ".exe")
else()
    set(EXE_SUFFIX "")
endif()

# 8. Main Build Target: compiles all workspace crates
add_custom_target(bengal-workspace ALL
    COMMAND ${CMAKE_COMMAND} -E env CARGO_TARGET_DIR=${CARGO_TARGET_DIR}
        ${CARGO_EXECUTABLE} build ${CARGO_RELEASE_FLAG} --workspace ${CARGO_TARGET_ARGS}
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${BINARY_SOURCE_DIR}/bengal-download-manager${EXE_SUFFIX}"
        "${BENGAL_BIN_OUTPUT_DIR}/bengal-download-manager${EXE_SUFFIX}"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Compiling Bengal Download Manager (Rust workspace) into ${BENGAL_BIN_OUTPUT_DIR}"
)

# 9. Create bdm symlink on UNIX / copy on Windows
if(UNIX)
    add_custom_command(TARGET bengal-workspace POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E create_symlink
            "bengal-download-manager"
            "${BENGAL_BIN_OUTPUT_DIR}/bdm"
        COMMENT "Creating bdm symlink in ${BENGAL_BIN_OUTPUT_DIR}"
    )
elseif(WIN32)
    add_custom_command(TARGET bengal-workspace POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${BENGAL_BIN_OUTPUT_DIR}/bengal-download-manager.exe"
            "${BENGAL_BIN_OUTPUT_DIR}/bdm.exe"
        COMMENT "Creating bdm.exe in ${BENGAL_BIN_OUTPUT_DIR}"
    )
endif()

# 10. Automated Unit Test Target
add_custom_target(check
    COMMAND ${CMAKE_COMMAND} -E env CARGO_TARGET_DIR=${CARGO_TARGET_DIR}
        ${CARGO_EXECUTABLE} test --workspace ${CARGO_TARGET_ARGS}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Running automated test suite across all workspace crates"
)

# 11. Multiplatform Installation (Linux, BSD, Flatpak, Snap)
if(UNIX AND NOT APPLE)
    include(GNUInstallDirs)
    install(PROGRAMS "${BENGAL_BIN_OUTPUT_DIR}/bengal-download-manager" DESTINATION ${CMAKE_INSTALL_BINDIR})
    install(PROGRAMS "${BENGAL_BIN_OUTPUT_DIR}/bdm" DESTINATION ${CMAKE_INSTALL_BINDIR})
    install(FILES flatpak/bd.com.zihad.BengalDownloadManager.desktop DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/applications)
    install(FILES flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/metainfo)
    install(FILES assets/icons/app_icon.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/256x256/apps RENAME bd.com.zihad.BengalDownloadManager.png)
endif()