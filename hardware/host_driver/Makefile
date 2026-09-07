# NCG Host Driver Build System
# 
# Builds the NCG XRT kernel driver and utilities
# 
# Requirements:
# - XRT (Xilinx Runtime) installed at /opt/xilinx/xrt
# - g++ with C++17 support
# - OpenCL headers (from XRT)

CXX = g++
CXXFLAGS = -std=c++17 -O3 -Wall -Wextra -fPIC
INCLUDES = -I/opt/xilinx/xrt/include -I/opt/xilinx/xrt/include/xrt
LIBS = -L/opt/xilinx/xrt/lib -lxrt_coreutil -lOpenCL -lpthread -ldl

# Build targets
TARGET = ncg_kernel
TEST_TARGET = ncg_test
UTILS_TARGET = ncg_utils

# Source files
SRC = ncg_kernel.cpp
TEST_SRC = test_ncg.cpp
UTILS_SRC = ncg_utils.cpp

# Build directory
BUILD_DIR = build

# Default target
all: $(BUILD_DIR)/$(TARGET)

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Main kernel driver
$(BUILD_DIR)/$(TARGET): $(SRC) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ $< $(LIBS)

# Test program
$(BUILD_DIR)/$(TEST_TARGET): $(TEST_SRC) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ $< $(LIBS)

# Utilities
$(BUILD_DIR)/$(UTILS_TARGET): $(UTILS_SRC) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ $< $(LIBS)

# Install to system
install: $(BUILD_DIR)/$(TARGET)
	sudo cp $(BUILD_DIR)/$(TARGET) /usr/local/bin/ncg_kernel
	sudo ldconfig

# Uninstall
uninstall:
	sudo rm -f /usr/local/bin/ncg_kernel
	sudo ldconfig

# Run tests
test: $(BUILD_DIR)/$(TEST_TARGET)
	$(BUILD_DIR)/$(TEST_TARGET)

# Clean
clean:
	rm -rf $(BUILD_DIR)

# Help
help:
	@echo "NCG Host Driver Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  all          - Build ncg_kernel"
	@echo "  test         - Build and run tests"
	@echo "  install      - Install to /usr/local/bin"
	@echo "  uninstall    - Remove from /usr/local/bin"
	@echo "  clean        - Remove build artifacts"
	@echo "  help         - Show this help"
	@echo ""
	@echo "Requirements:"
	@echo "  - XRT installed at /opt/xilinx/xrt"
	@echo "  - g++ with C++17 support"
	@echo "  - OpenCL headers from XRT"

.PHONY: all install uninstall test clean help