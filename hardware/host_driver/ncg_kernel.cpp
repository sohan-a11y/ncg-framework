/*
 * NCG XRT Kernel Driver
 * 
 * Host-side kernel for NCG accelerator on Alveo U50/U280
 * Interfaces with XRT (Xilinx Runtime) for FPGA management
 * 
 * Build: g++ -std=c++17 -I/opt/xilinx/xrt/include -L/opt/xilinx/xrt/lib -lxrt_coreutil -lOpenCL ncg_kernel.cpp -o ncg_kernel
 */

#include <xrt/xrt_device.h>
#include <xrt/xrt_kernel.h>
#include <xrt/xrt_bo.h>
#include <xrt/xrt_uuid.h>
#include <xrt/xrt_aie.h>

#include <iostream>
#include <vector>
#include <cstdint>
#include <chrono>
#include <thread>
#include <memory>
#include <stdexcept>
#include <cstring>
#include <fstream>
#include <iomanip>

#define NCG_VENDOR_ID 0x10EE  // Xilinx
#define NCG_DEVICE_ID 0x9038  // Alveo U50 (adjust for U280)
#define NCG_SUBSYSTEM_ID 0x0001

// NCG Control Register Offsets
namespace NCGRegs {
    constexpr uint32_t CTRL       = 0x00;
    constexpr uint32_t STATUS     = 0x04;
    constexpr uint32_t CMD        = 0x08;
    constexpr uint32_t TARGET_HASH_LO = 0x10;
    constexpr uint32_t TARGET_HASH_HI = 0x14;
    constexpr uint32_t DCPM_ADDR  = 0x20;
    constexpr uint32_t DCPM_WDATA = 0x24;
    constexpr uint32_t DCPM_RDATA = 0x28;
    constexpr uint32_t MATCH_HASH_LO = 0x30;
    constexpr uint32_t MATCH_HASH_HI = 0x34;
    constexpr uint32_t MATCH_CORE = 0x38;
    constexpr uint32_t CANDIDATE_CNT = 0x3C;
    constexpr uint32_t CYCLE_CNT  = 0x40;
    constexpr uint32_t MATCH_HASH_LO2 = 0x30;
    constexpr uint32_t MATCH_HASH_HI2 = 0x34;
    constexpr uint32_t MATCH_CORE_ID = 0x38;
    constexpr uint32_t CANDIDATES_GEN = 0x3C;
    constexpr uint32_t CYCLES_TOTAL = 0x40;
    constexpr uint32_t INF_CYCLES = 0x44;
    constexpr uint32_t HASH_CYCLES = 0x48;
}

// PCIe Command Codes
namespace NCGCmd {
    constexpr uint32_t LOAD_DCPM   = 0x00;
    constexpr uint32_t START_SEARCH = 0x01;
    constexpr uint32_t READ_RESULT = 0x02;
}

// Status Codes
namespace NCGStatus {
    constexpr uint32_t IDLE       = 0x0;
    constexpr uint32_t LOADING    = 0x1;
    constexpr uint32_t INFERENCE  = 0x2;
    constexpr uint32_t HASHING    = 0x3;
    constexpr uint32_t DONE       = 0x4;
    constexpr uint32_t ERROR      = 0xF;
}

class NCGKernel {
public:
    NCGKernel(uint32_t device_index = 0, const std::string& xclbin_path = "")
        : device_index_(device_index) {
        
        // Open device
        device_ = std::make_unique<xrt::device>(device_index);
        
        // Load xclbin if provided
        if (!xclbin_path.empty()) {
            load_xclbin(xclbin_path);
        }
        
        // Get kernel
        kernel_ = std::make_unique<xrt::kernel>(*device_, "ncg_top");
        
        // Allocate buffers
        init_buffers();
    }
    
    ~NCGKernel() {
        // Buffers automatically freed by xrt::bo destructor
    }
    
    void load_xclbin(const std::string& xclbin_path) {
        auto uuid = device_->load_xclbin(xclbin_path);
        std::cout << "Loaded xclbin: " << uuid.to_string() << std::endl;
    }
    
    void init_buffers() {
        // DCPM buffer (512-bit wide, 4096 entries = 256KB)
        dcmp_buffer_ = std::make_unique<xrt::bo>(
            *device_, 
            4096 * 64,  // 4096 entries * 64 bytes (512 bits)
            XRT_BO_FLAGS_HOST_ONLY,
            kernel_->group_id(0)
        );
        
        // Candidate buffer (output from inference)
        candidate_buffer_ = std::make_unique<xrt::bo>(
            *device_,
            1024 * 64,  // 1024 candidates * 64 bytes
            XRT_BO_FLAGS_HOST_ONLY,
            kernel_->group_id(1)
        );
        
        // Result buffer
        result_buffer_ = std::make_unique<xrt::bo>(
            *device_,
            256,  // 256 bytes for result
            XRT_BO_FLAGS_HOST_ONLY,
            kernel_->group_id(2)
        );
        
        // Map buffers to host
        dcmp_host_ = dcmp_buffer_->map<uint64_t*>();
        candidate_host_ = candidate_buffer_->map<uint64_t*>();
        result_host_ = result_buffer_->map<uint8_t*>();
    }
    
    void load_dcmp(const std::vector<uint64_t>& dcmp_data) {
        if (dcmp_data.size() > 4096) {
            throw std::runtime_error("DCPM data too large for buffer");
        }
        
        // Copy DCPM data to host buffer
        std::memcpy(dcmp_host_, dcmp_data.data(), dcmp_data.size() * sizeof(uint64_t));
        
        // Sync to device
        dcmp_buffer_->sync(XCL_BO_SYNC_BO_TO_DEVICE);
        
        // Write DCPM load command via control register
        write_register(NCGRegs::CMD, NCGCmd::LOAD_DCPM);
        wait_for_status(NCGStatus::LOADING);
    }
    
    void start_search(const std::array<uint8_t, 32>& target_hash) {
        // Write target hash (split into two 64-bit registers)
        uint64_t hash_lo = 0, hash_hi = 0;
        for (int i = 0; i < 16; ++i) {
            hash_lo |= (static_cast<uint64_t>(target_hash[i]) << (i * 8));
        }
        for (int i = 0; i < 16; ++i) {
            hash_hi |= (static_cast<uint64_t>(target_hash[16 + i]) << (i * 8));
        }
        
        write_register(NCGRegs::TARGET_HASH_LO, hash_lo);
        write_register(NCGRegs::TARGET_HASH_HI, hash_hi);
        
        // Start search
        write_register(NCGRegs::CMD, NCGCmd::START_SEARCH);
        
        // Wait for completion
        wait_for_status(NCGStatus::DONE);
    }
    
    struct SearchResult {
        bool match_found;
        uint32_t match_core_id;
        std::array<uint8_t, 32> match_hash;
        uint64_t candidates_generated;
        uint64_t total_cycles;
        uint64_t inference_cycles;
        uint64_t hashing_cycles;
    };
    
    SearchResult read_result() {
        SearchResult result;
        
        // Read result buffer
        write_register(NCGRegs::CMD, NCGCmd::READ_RESULT);
        
        // Wait for result ready (small delay)
        std::this_thread::sleep_for(std::chrono::microseconds(10));
        
        // Read result buffer
        result_buffer_->sync(XCL_BO_SYNC_BO_FROM_DEVICE);
        
        // Parse result (256 bytes)
        uint8_t* data = result_host_;
        result.match_found = data[0] != 0;
        result.match_core_id = *reinterpret_cast<uint32_t*>(data + 4);
        
        // Extract hash (32 bytes at offset 32)
        std::memcpy(result.match_hash.data(), data + 32, 32);
        
        result.candidates_generated = *reinterpret_cast<uint64_t*>(data + 64);
        result.total_cycles = *reinterpret_cast<uint64_t*>(data + 72);
        result.inference_cycles = *reinterpret_cast<uint64_t*>(data + 80);
        result.hashing_cycles = *reinterpret_cast<uint64_t*>(data + 88);
        
        return result;
    }
    
    // Full search pipeline
    SearchResult search(const std::vector<uint64_t>& dcmp_data, 
                       const std::array<uint8_t, 32>& target_hash) {
        load_dcmp(dcmp_data);
        start_search(target_hash);
        return read_result();
    }
    
    // Performance counters
    uint64_t get_cycle_count() {
        return read_register(NCGRegs::CYCLE_CNT);
    }
    
    uint64_t get_candidates_generated() {
        return read_register(NCGRegs::CANDIDATE_CNT);
    }

private:
    void write_register(uint32_t offset, uint64_t value) {
        // Write via control buffer (first BO)
        // This assumes control registers are mapped in first buffer
        // In practice, you'd have a dedicated control buffer
        uint64_t* ctrl = reinterpret_cast<uint64_t*>(dcmp_host_);
        ctrl[offset / 8] = value;
        dcmp_buffer_->sync(XCL_BO_SYNC_BO_TO_DEVICE, 8, offset);
    }
    
    uint64_t read_register(uint32_t offset) {
        dcmp_buffer_->sync(XCL_BO_SYNC_BO_FROM_DEVICE, 8, offset);
        uint64_t* ctrl = reinterpret_cast<uint64_t*>(dcmp_host_);
        return ctrl[offset / 8];
    }
    
    void wait_for_status(uint32_t expected_status, int timeout_ms = 5000) {
        auto start = std::chrono::steady_clock::now();
        while (true) {
            uint32_t status = static_cast<uint32_t>(read_register(NCGRegs::STATUS));
            if (status == expected_status) {
                return;
            }
            if (status == NCGStatus::ERROR) {
                throw std::runtime_error("NCG hardware error");
            }
            
            auto elapsed = std::chrono::steady_clock::now() - start;
            if (std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count() > timeout_ms) {
                throw std::runtime_error("Timeout waiting for status");
            }
            
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
    
    uint32_t device_index_;
    std::unique_ptr<xrt::device> device_;
    std::unique_ptr<xrt::kernel> kernel_;
    std::unique_ptr<xrt::bo> dcmp_buffer_;
    std::unique_ptr<xrt::bo> candidate_buffer_;
    std::unique_ptr<xrt::bo> result_buffer_;
    uint64_t* dcmp_host_;
    uint64_t* candidate_host_;
    uint8_t* result_host_;
};

// High-level NCG API
class NCGAccelerator {
public:
    NCGAccelerator(const std::string& xclbin_path, uint32_t device_index = 0)
        : kernel_(device_index, xclbin_path) {}
    
    // Search for password hash
    NCGKernel::SearchResult search_password(
        const std::string& target_hash_hex,
        const std::string& context_org = "",
        int context_year = 2024,
        const std::vector<std::string>& known_leaks = {}
    ) {
        // Convert hex hash to bytes
        std::array<uint8_t, 32> target_hash;
        if (target_hash_hex.size() != 64) {
            throw std::invalid_argument("Hash must be 64 hex characters (32 bytes)");
        }
        for (size_t i = 0; i < 32; ++i) {
            std::string byte_str = target_hash_hex.substr(i * 2, 2);
            target_hash[i] = static_cast<uint8_t>(std::stoul(byte_str, nullptr, 16));
        }
        
        // Generate DCPM from context (using software reference for now)
        // In production, this would be done on FPGA
        std::vector<uint64_t> dcmp_data = generate_dcmp_placeholder();
        
        return kernel_.search(dcmp_data, target_hash);
    }
    
    // Get performance statistics
    struct PerfStats {
        uint64_t total_cycles;
        uint64_t candidates_generated;
        double cycles_per_candidate;
        double hash_rate_mhps;  // Mega hashes per second
    };
    
    PerfStats get_performance() {
        PerfStats stats;
        stats.total_cycles = kernel_.get_cycle_count();
        stats.candidates_generated = kernel_.get_candidates_generated();
        stats.cycles_per_candidate = stats.candidates_generated > 0 ? 
            static_cast<double>(stats.total_cycles) / stats.candidates_generated : 0;
        // Assuming 250 MHz clock
        stats.hash_rate_mhps = 250.0 / stats.cycles_per_candidate;
        return stats;
    }

private:
    NCGKernel kernel_;
    
    std::vector<uint64_t> generate_dcmp_placeholder() {
        // Placeholder - in production this would come from the inference core
        std::vector<uint64_t> dcmp(4096, 0);
        for (size_t i = 0; i < dcmp.size(); ++i) {
            dcmp[i] = static_cast<uint64_t>(i * 0x9E3779B97F4A7C15);
        }
        return dcmp;
    }
};

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <xclbin_path> <target_hash_hex>" << std::endl;
        std::cerr << "Example: " << argv[0] << " ncg.xclbin ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" << std::endl;
        return 1;
    }
    
    std::string xclbin_path = argv[1];
    std::string target_hash = argv[2];
    
    try {
        NCGAccelerator accel(xclbin_path);
        
        std::cout << "Starting NCG search for hash: " << target_hash << std::endl;
        
        auto start = std::chrono::high_resolution_clock::now();
        auto result = accel.search_password(target_hash);
        auto end = std::chrono::high_resolution_clock::now();
        
        auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
        
        std::cout << "Search completed in " << duration.count() << " ms" << std::endl;
        std::cout << "Match found: " << (result.match_found ? "YES" : "NO") << std::endl;
        
        if (result.match_found) {
            std::cout << "Match core ID: " << result.match_core_id << std::endl;
            std::cout << "Match hash: ";
            for (uint8_t b : result.match_hash) {
                std::cout << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(b);
            }
            std::cout << std::dec << std::endl;
        }
        
        std::cout << "Candidates generated: " << result.candidates_generated << std::endl;
        std::cout << "Total cycles: " << result.total_cycles << std::endl;
        std::cout << "Inference cycles: " << result.inference_cycles << std::endl;
        std::cout << "Hashing cycles: " << result.hashing_cycles << std::endl;
        
        // Performance stats
        auto perf = accel.get_performance();
        std::cout << "\nPerformance:" << std::endl;
        std::cout << "  Cycles per candidate: " << perf.cycles_per_candidate << std::endl;
        std::cout << "  Hash rate: " << perf.hash_rate_mhps << " MH/s" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}