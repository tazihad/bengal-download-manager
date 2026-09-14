# CMake Toolchain for Windows MSVC (x64)
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR AMD64)

set(CMAKE_CXX_COMPILER "cl.exe")
set(CMAKE_C_COMPILER "cl.exe")

# Ensure UTF-8 execution and MSVC runtime flags
add_compile_options("/utf-8" "/MP")

message(STATUS "[Toolchain] Configured for Windows MSVC x64")
