#!/bin/bash
# NCG Deployment Package Creator
# 
# Creates a complete deployment package with bitstream, xclbin,
# host driver, and installation scripts.

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
PACKAGE_NAME="ncg-framework"
VERSION="1.0.0"
OUTPUT_DIR="deploy"

usage() {
    cat << EOF
NCG Deployment Package Creator

Usage: $0 [options]

Options:
  -b, --bitstream <path>    Path to bitstream (.bit)
  -x, --xclbin <path>       Path to xclbin (.xclbin)
  -o, --output <dir>        Output directory (default: deploy)
  -n, --name <name>         Package name (default: ncg-framework)
  -v, --version <ver>       Version string (default: 1.0.0)
  -h, --help                Show this help

Example:
  $0 -b ncg_top.bit -x ncg_top.xclbin -o deploy_package
EOF
}

# Defaults
BITSTREAM=""
XCLBIN=""
OUTPUT_DIR="deploy"
PACKAGE_NAME="ncg-framework"
VERSION="1.0.0"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--bitstream) BITSTREAM="$2"; shift 2 ;;
        -x|--xclbin) XCLBIN="$2"; shift 2 ;;
        -o|--output) OUTPUT_DIR="$2"; shift 2 ;;
        -n|--name) PACKAGE_NAME="$2"; shift 2 ;;
        -v|--version) VERSION="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# Validate inputs
if [[ -z "$BITSTREAM" || ! -f "$BITSTREAM" ]]; then
    echo -e "${RED}Error: Bitstream file required (-b)${NC}"
    exit 1
fi

if [[ -n "$XCLBIN" && ! -f "$XCLBIN" ]]; then
    echo -e "${RED}Error: XCLBIN file not found: $XCLBIN${NC}"
    exit 1
fi

# Create output directory
PACKAGE_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}"
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"/{bitstream,xclbin,driver,scripts,docs}

echo -e "${GREEN}Creating deployment package: ${PACKAGE_NAME}-${VERSION}${NC}"

# Copy bitstream
echo "Copying bitstream..."
cp "$BITSTREAM" "$PACKAGE_DIR/bitstream/ncg.bit"

# Copy xclbin if provided
if [[ -n "$XCLBIN" ]]; then
    echo "Copying xclbin..."
    cp "$XCLBIN" "$PACKAGE_DIR/xclbin/ncg.xclbin"
fi

# Copy host driver source
echo "Copying host driver..."
cp -r ../host_driver/* "$PACKAGE_DIR/driver/" 2>/dev/null || true

# Copy scripts
echo "Copying scripts..."
cp ../../synth/scripts/deploy.sh "$PACKAGE_DIR/scripts/"
cp ../../synth/scripts/validate.py "$PACKAGE_DIR/scripts/" 2>/dev/null || true

# Create documentation
cat > "$PACKAGE_DIR/docs/README.md" << EOF
# NCG Framework Deployment Package

Version: $VERSION
Date: $(date -u +"%Y-%m-%d")

## Contents

- \`bitstream/ncg.bit\` - FPGA bitstream for Alveo U50/U280
- \`xclbin/ncg.xclbin\` - XRT kernel binary (if available)
- \`driver/\` - Host driver source code (XRT kernel)
- \`scripts/\` - Deployment and validation scripts
- \`docs/\` - Documentation

## Requirements

- AMD Alveo U50 or U280 Data Center Accelerator
- Xilinx Runtime (XRT) 2022.2+
- Linux kernel 5.4+
- PCIe Gen4/Gen5 slot

## Quick Start

\`\`\`bash
# 1. Install XRT (if not installed)
# See: https://www.xilinx.com/products/design-tools/vitis/vitis-platform.html

# 2. Deploy bitstream
sudo ./scripts/deploy.sh bitstream/ncg.bit

# 3. Build and install host driver
cd driver && make install

# 4. Run NCG application
ncg_kernel /opt/xilinx/xrt/amdzcu102/ncg.xclbin <target_hash>
\`\`\`

## Hardware Support

- AMD Alveo U50 (xcu50-fsvh2104-2-e)
- AMD Alveo U280 (xcu280-fsvh2892-2-e)

## License

Apache 2.0 - See LICENSE file
EOF

# Create install script
cat > "$PACKAGE_DIR/install.sh" << 'EOF'
#!/bin/bash
# NCG Framework Installer

set -euo pipefail

echo "NCG Framework Installer"
echo "======================="

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (sudo)"
    exit 1
fi

# Install XRT if not present
if ! command -v xbutil &> /dev/null; then
    echo "XRT not found. Please install XRT first."
    echo "See: https://www.xilinx.com/products/design-tools/vitis/vitis-platform.html"
    exit 1
fi

# Deploy bitstream
echo "Deploying bitstream..."
./scripts/deploy.sh bitstream/ncg.bit --verify

# Build and install host driver
if [[ -d "driver" ]]; then
    echo "Building host driver..."
    cd driver && make install
    cd ..
fi

echo "Installation complete!"
echo "Run 'ncg_kernel' to test the installation."
EOF
chmod +x "$PACKAGE_DIR/install.sh"

# Create uninstall script
cat > "$PACKAGE_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
# NCG Framework Uninstaller

set -euo pipefail

echo "NCG Framework Uninstaller"
echo "========================"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (sudo)"
    exit 1
fi

# Uninstall host driver
if command -v ncg_kernel &> /dev/null; then
    echo "Uninstalling host driver..."
    make -C /usr/local/src/ncg-driver uninstall 2>/dev/null || true
    rm -f /usr/local/bin/ncg_kernel
fi

# Reset FPGA (optional)
if command -v xbutil &> /dev/null; then
    echo "Resetting FPGA..."
    xbutil reset --all --force 2>/dev/null || true
fi

echo "Uninstallation complete!"
EOF
chmod +x "$PACKAGE_DIR/uninstall.sh"

# Create manifest
cat > "$PACKAGE_DIR/manifest.json" << EOF
{
  "package": "$PACKAGE_NAME",
  "version": "$VERSION",
  "date": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "components": {
    "bitstream": "bitstream/ncg.bit",
    "xclbin": "xclbin/ncg.xclbin",
    "driver": "driver/",
    "scripts": "scripts/",
    "docs": "docs/"
  },
  "requirements": {
    "xrt": ">= 2022.2",
    "kernel": ">= 5.4",
    "hardware": ["Alveo U50", "Alveo U280"]
  },
  "supported_hardware": ["Alveo U50", "Alveo U280"]
}
EOF

# Create tarball
echo "Creating tarball..."
cd "$OUTPUT_DIR"
tar -czf "${PACKAGE_NAME}-${VERSION}.tar.gz" "${PACKAGE_NAME}-${VERSION}"
cd ..

# Checksums
echo "Generating checksums..."
cd "$OUTPUT_DIR"
sha256sum "${PACKAGE_NAME}-${VERSION}.tar.gz" > "${PACKAGE_NAME}-${VERSION}.tar.gz.sha256"
sha256sum "${PACKAGE_NAME}-${VERSION}/bitstream/ncg.bit" > "${PACKAGE_NAME}-${VERSION}.bitstream.sha256"
if [[ -f "${PACKAGE_NAME}-${VERSION}/xclbin/ncg.xclbin" ]]; then
    sha256sum "${PACKAGE_NAME}-${VERSION}/xclbin/ncg.xclbin" > "${PACKAGE_NAME}-${VERSION}.xclbin.sha256"
fi
cd ..

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment package created successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Package: ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.tar.gz"
echo "Checksum: $(cat ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.tar.gz.sha256)"
echo ""
echo "To deploy:"
echo "  tar -xzf ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.tar.gz"
echo "  cd ${PACKAGE_NAME}-${VERSION}"
echo "  sudo ./install.sh"
EOF
chmod +x ncg-framework/hardware/synth/scripts/create_package.sh