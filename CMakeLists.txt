cmake_minimum_required(VERSION 3.12)

# Multiplatform Root CMake Entry Point for Bengal Download Manager
project(BengalDownloadManager LANGUAGES NONE)

# Find the Python3 interpreter
find_package(Python3 COMPONENTS Interpreter REQUIRED)

# Delegate to the modular multiplatform build system in build/
add_subdirectory(build)