# CMake Toolchain for Linux Clang / LLVM
set(CMAKE_SYSTEM_NAME Linux)

set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)

add_compile_options(-Wall -Wextra -O2)

message(STATUS "[Toolchain] Configured for Linux Clang")
