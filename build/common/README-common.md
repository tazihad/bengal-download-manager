# Bengal Download Manager — Common Build Infrastructure

This directory contains shared cross-platform build infrastructure, CMake helper modules, shared patches, and common packaging utilities.

## Directory Structure

* `cmake/modules/`: Shared CMake modules (`VersionHelper.cmake`, `FindPyQt6.cmake`, `PackagingHelper.cmake`).
* `cmake/toolchains/`: Shared cross-platform toolchains.
* `patches/`: Cross-platform patches applied during multiplatform builds.
* `fixes/`: Platform-neutral runtime fixes.
