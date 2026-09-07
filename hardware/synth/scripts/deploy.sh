#!/bin/bash
# NCG FPGA Deployment Script
# 
# This script automates the deployment of NCG bitstream to Alveo U50/U280
# using XRT tools.
#
# Usage: ./deploy.sh <bitstream> [device_bdf] [options]
# 
# Options:
#   -h, --help          Show this help
#   -v, --verify        Verify deployment after programming
#   -f, --force         Force programming even if device busy
#   --dry-run           Show commands without executing

set -euo pipefail

# Default values
BITSTREAM=""
DEVICE_BDF=""
VERIFY=false
FORCE=false
DRY_RUN=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

usage() {
    cat << EOF
NCG FPGA Deployment Script

Usage: $0 <bitstream> [device_bdf] [options]

Arguments:
  bitstream     Path to .bit bitstream file
  device_bdf    PCIe BDF of target device (e.g., 0000:01:00.0)

Options:
  -h, --help      Show this help message
  -v, --verify    Verify deployment after programming
  -f, --force     Force programming even if device appears busy
  --dry-run       Show commands without executing

Examples:
  $0 ncg_top.bit                           # Auto-detect device
  $0 ncg_top.bit 0000:01:00.0 --verify    # Deploy to specific device and verify
  $0 ncg_top.bit --dry-run                # Show commands without executing

Environment Variables:
  XILINX_XRT       XRT installation path (default: /opt/xilinx/xrt)
  VIVADO_PATH      Vivado installation path (for hw_server)
EOF
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Required command '$1' not found in PATH"
        return 1
    fi
    return 0
}

# ============================================================================
# PARSE ARGUMENTS
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -v|--verify)
            VERIFY=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -*)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
        *)
            if [[ -z "$BITSTREAM" ]]; then
                BITSTREAM="$1"
            elif [[ -z "$DEVICE_BDF" ]]; then
                DEVICE_BDF="$1"
            else
                log_error "Too many positional arguments"
                usage
                exit 1
            fi
            shift
            ;;
    esac
done

# ============================================================================
# VALIDATION
# ============================================================================

if [[ -z "$BITSTREAM" ]]; then
    log_error "Bitstream file required"
    usage
    exit 1
fi

if [[ ! -f "$BITSTREAM" ]]; then
    log_error "Bitstream file not found: $BITSTREAM"
    exit 1
fi

# Check required commands
REQUIRED_CMDS=("xbutil" "xrt" "lspci")
for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! check_command "$cmd"; then
        log_error "Required command '$cmd' not found. Is XRT installed?"
        exit 1
    fi
done

# ============================================================================
# DEVICE DETECTION
# ============================================================================

if [[ -z "$DEVICE_BDF" ]]; then
    log_info "Auto-detecting Alveo device..."
    
    # Use xbutil to find Alveo devices
    DEVICES=$(xbutil examine -r | grep -E "xilinx.*alveo" | awk '{print $1}')
    
    if [[ -z "$DEVICES" ]]; then
        log_error "No Alveo devices found. Specify device BDF manually."
        exit 1
    fi
    
    DEVICE_COUNT=$(echo "$DEVICES" | wc -l)
    if [[ $DEVICE_COUNT -gt 1 ]]; then
        log_warn "Multiple Alveo devices found:"
        echo "$DEVICES" | while read -r dev; do
            echo "  $dev"
        done
        log_warn "Using first device. Specify BDF to select specific device."
    fi
    
    DEVICE_BDF=$(echo "$DEVICES" | head -1)
fi

log_info "Target device: $DEVICE_BDF"

# Verify device exists
if ! lspci -s "$DEVICE_BDF" &> /dev/null; then
    log_error "Device not found at BDF: $DEVICE_BDF"
    exit 1
fi

# ============================================================================
# DEPLOYMENT
# ============================================================================

BITSTREAM_ABS=$(realpath "$BITSTREAM")
log_info "Deploying bitstream: $BITSTREAM_ABS"
log_info "Target device: $DEVICE_BDF"

# Function to run or show command
run_cmd() {
    if [[ "$DRY_RUN" == true ]]; then
        echo "[DRY RUN] $*"
    else
        eval "$@"
    fi
}

# Step 1: Reset device (optional, but good practice)
log_info "Step 1: Resetting device..."
run_cmd "xbutil reset -d $DEVICE_BDF --force" || log_warn "Device reset failed (may be OK)"

# Step 2: Program bitstream
log_info "Step 2: Programming bitstream..."
run_cmd "xbutil program -p $BITSTREAM_ABS -d $DEVICE_BDF" || {
    log_error "Bitstream programming failed!"
    exit 1
}

# Step 3: Wait for device to come back
log_info "Step 3: Waiting for device to enumerate..."
sleep 3

# Step 4: Verify device is back
log_info "Step 4: Verifying device enumeration..."
if ! lspci -s "$DEVICE_BDF" &> /dev/null; then
    log_error "Device not found after programming!"
    exit 1
fi

log_info "Device enumerated successfully"

# Step 5: Load XCLBIN (if available)
XCLBIN="${BITSTREAM%.*}.xclbin"
if [[ -f "$XCLBIN" ]]; then
    log_info "Step 5: Loading XCLBIN..."
    run_cmd "xbutil load -p $XCLBIN -d $DEVICE_BDF" || {
        log_warn "XCLBIN load failed (may be loaded automatically)"
    }
else
    log_warn "XCLBIN not found at $XCLBIN (skipping)"
fi

# Step 6: Verify deployment
if [[ "$VERIFY" == true ]]; then
    log_info "Step 6: Verifying deployment..."
    
    # Check device status
    STATUS=$(xbutil examine -r -d "$DEVICE_BDF" 2>/dev/null | grep -i "status\|state" | head -1)
    log_info "Device status: $STATUS"
    
    # Check if kernel is loaded
    KERNELS=$(xbutil examine -k -d "$DEVICE_BDF" 2>/dev/null | grep -c "ncg_top" || echo "0")
    if [[ "$KERNELS" -gt 0 ]]; then
        log_info "NCG kernel detected: $KERNELS instance(s)"
    else
        log_warn "NCG kernel not detected in xbutil"
    fi
    
    log_info "Verification complete"
fi

# ============================================================================
# SUMMARY
# ============================================================================

log_info "======================================================================"
log_info "Deployment Summary"
log_info "======================================================================"
log_info "Bitstream: $BITSTREAM_ABS"
log_info "Device:    $DEVICE_BDF"
log_info "Status:    ${GREEN}SUCCESS${NC}"

if [[ "$VERIFY" == true ]]; then
    log_info "Verification: Performed"
fi

if [[ "$DRY_RUN" == true ]]; then
    log_warn "DRY RUN MODE - No actual commands executed"
fi

log_info "======================================================================"

exit 0