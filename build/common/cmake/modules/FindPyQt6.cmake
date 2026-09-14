# FindPyQt6.cmake - Detection helper for PyQt6
find_package(Python3 COMPONENTS Interpreter REQUIRED)

execute_process(
    COMMAND ${Python3_EXECUTABLE} -c "import PyQt6; print(PyQt6.__file__)"
    RESULT_VARIABLE PYQT6_FIND_RES
    OUTPUT_VARIABLE PYQT6_LOCATION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
)

if(PYQT6_FIND_RES EQUAL 0)
    set(PyQt6_FOUND TRUE)
    message(STATUS "Found PyQt6: ${PYQT6_LOCATION}")
else()
    set(PyQt6_FOUND FALSE)
    message(WARNING "PyQt6 was not found in Python environment (${Python3_EXECUTABLE})")
endif()
