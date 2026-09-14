# PackagingHelper.cmake - Helper functions for multiplatform distribution packaging

function(bdm_create_archive TARGET_NAME SOURCE_DIR OUTPUT_FILE FORMAT)
    add_custom_target(${TARGET_NAME}
        COMMAND ${CMAKE_COMMAND} -E tar "cfv" "${OUTPUT_FILE}" --format=${FORMAT} "${SOURCE_DIR}"
        COMMENT "Packaging archive: ${OUTPUT_FILE}"
    )
endfunction()
