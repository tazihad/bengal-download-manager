# CMake Toolchain for Linux GCC (x86_64 / aarch64)
set(CMAKE_SYSTEM_NAME Linux)

if(NOT DEFINED CMAKE_C_COMPILER)
    set(CMAKE_C_COMPILER gcc)
endif()

if(NOT DEFINED CMAKE_CXX_COMPILER)
    set(CMAKE_CXX_COMPILER g++)
endif()

add_compile_options(-Wall -Wextra -O2)

message(STATUS "[Toolchain] Configured for Linux GCC")
