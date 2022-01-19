cmake_minimum_required(VERSION 3.16)

project(serialplotting-gui)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 COMPONENTS Widgets REQUIRED)

add_executable(serialplotting-gui
    main.cpp
    mainwidget.cpp
)

target_link_libraries(serialplotting-gui PRIVATE Qt6::Widgets)