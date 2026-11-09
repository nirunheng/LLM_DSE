project(noc)

# parser
file(GLOB parser parser/*.a)
# sub-modules
file(GLOB sub_modules allocators arbiters focus monitor networks power routers)
# cpp files
file(GLOB_RECURSE cpp_files *.cpp)

add_library(${PROJECT_NAME} ${cpp_files})

# SPATIAL: enables the interface, SpatialTrafficManager, to interact with Spatial Cores
target_compile_options(${PROJECT_NAME} PUBLIC -g -DSPATIAL)

# Include directory for booksim2 headers
target_include_directories(${PROJECT_NAME} PUBLIC ${PROJECT_SOURCE_DIR})
target_include_directories(${PROJECT_NAME} PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_include_directories(${PROJECT_NAME} PUBLIC ${PROJECT_SOURCE_DIR}/networks)
target_include_directories(${PROJECT_NAME} PUBLIC ${PROJECT_SOURCE_DIR}/power)
target_include_directories(${PROJECT_NAME} PUBLIC ${PROJECT_SOURCE_DIR}/routers)
# Include directory for common headers (src/common)
get_filename_component(SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../.. ABSOLUTE)
target_include_directories(${PROJECT_NAME} PUBLIC ${SRC_DIR}/common)
target_include_directories(${PROJECT_NAME} PUBLIC ${sub_modules})

target_link_libraries(${PROJECT_NAME} ${parser})
