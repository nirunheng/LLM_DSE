#### Prompt the build type ####
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE "Release" CACHE STRING "" FORCE)
endif()
message("Configuring ${CMAKE_PROJECT_NAME} ${CMAKE_PROJECT_Version}...")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -DRAMULATOR_DEBUG")
# set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE}")
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
###############################

set(CMAKE_EXPORT_COMPILE_COMMANDS ON CACHE INTERNAL "")

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_EXTENSIONS OFF)

#### External libraries ####
include(FetchContent)
set(FETCHCONTENT_UPDATES_DISCONNECTED ON CACHE BOOL "Skip updating the external dependencies after populating them for the first time")

include_directories(${yaml-cpp_SOURCE_DIR}/include)

message("Configuring spdlog...")
FetchContent_Declare(
  spdlog                             
  GIT_REPOSITORY https://github.com/gabime/spdlog.git
  GIT_TAG        v1.11.0     
  SOURCE_DIR     ${CMAKE_CURRENT_SOURCE_DIR}/ext/spdlog
)
FetchContent_MakeAvailable(spdlog)
include_directories(${spdlog_SOURCE_DIR}/include)
message("Done configuring spdlog.")

message("Configuring argparse...")
FetchContent_Declare(
    argparse
    GIT_REPOSITORY https://github.com/p-ranav/argparse.git
    GIT_TAG        v2.9     
    SOURCE_DIR     ${CMAKE_CURRENT_SOURCE_DIR}/ext/argparse
)
FetchContent_MakeAvailable(argparse)
include_directories(${argparse_SOURCE_DIR}/include)
message("Done configuring argparse.")
##################################

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)

add_library(ramulator SHARED)
target_link_libraries(
  ramulator 
  PUBLIC yaml-cpp
  PUBLIC spdlog
)
target_include_directories(
  ramulator
  PUBLIC src
  PUBLIC ${spdlog_SOURCE_DIR}/include
  PUBLIC ${yaml-cpp_SOURCE_DIR}/include
  PUBLIC ${argparse_SOURCE_DIR}/include
)

add_executable(ramulator-exe)
target_link_libraries(
  ramulator-exe 
  # PRIVATE -Wl,--whole-archive ramulator -Wl,--no-whole-archive 
  PRIVATE ramulator
  PRIVATE argparse
)

set_target_properties(
  ramulator-exe
  PROPERTIES 
  OUTPUT_NAME ramulator2
)

add_subdirectory(src)