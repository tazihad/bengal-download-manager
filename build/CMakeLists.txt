cmake_minimum_required(VERSION 3.12)

# Multiplatform Subdirectory CMake Configuration for Bengal Download Manager
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_CURRENT_SOURCE_DIR}/common/cmake/modules")
include(VersionHelper)

# Resolve repository paths
set(ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/..")

# Set default output directories to CMAKE_BINARY_DIR so out-of-source builds work seamlessly
if(NOT DEFINED DIST_DIR)
    set(DIST_DIR "${CMAKE_BINARY_DIR}/dist")
endif()

extract_bdm_version("${ROOT_DIR}/VERSION" BDM_VERSION)

message(STATUS "==========================================================")
message(STATUS " Bengal Download Manager Build System v${BDM_VERSION}")
message(STATUS " Target Platform: ${CMAKE_SYSTEM_NAME}")
message(STATUS " Output Dist Dir: ${DIST_DIR}")
message(STATUS "==========================================================")

# ── Platform-Specific Inclusions ─────────────────────────────────────────────
if(WIN32)
    message(STATUS "Loading Windows platform configuration...")
    include("${CMAKE_CURRENT_SOURCE_DIR}/windows/cmake/options.cmake")
elseif(APPLE)
    message(STATUS "macOS platform build is reserved for future implementation.")
elseif(UNIX)
    message(STATUS "Loading Linux platform configuration...")
    include("${CMAKE_CURRENT_SOURCE_DIR}/linux/cmake/options.cmake")
else()
    message(WARNING "Unknown or unsupported platform: ${CMAKE_SYSTEM_NAME}")
endif()
