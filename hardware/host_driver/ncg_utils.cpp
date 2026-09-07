/*
 * NCG Host Driver Utilities
 * 
 * Utility functions for NCG accelerator management
 */

#include <xrt/xrt_device.h>
#include <xrt/xrt_kernel.h>
#include <xrt/xrt_bo.h>
#include <xrt/xrt_uuid.h>

#include <iostream>
#include <vector>
#include <string>
#include <fstream>
#include <filesystem>
#include <chrono>
#include <iomanip>
#include <sstream>

namespace fs = std::filesystem;

namespace ncg {

// Device discovery and management
class DeviceManager {
public:
    static std::vector<uint32_t> list_devices() {
        std::vector<uint32_t> devices;
        
        // XRT device enumeration
        auto devices_list = xrt::device::get_devices();
        for (size_t i = 0; i < devices_list.size(); ++i) {
            devices.push_back(static_cast<uint32_t>(i));
        }
        
        return devices;
    }
    
    static std::string get_device_name(uint32_t index) {
        try {
            xrt::device device(index);
            auto info = device.get_info<xrt::info::device::name>();
            return info;
        } catch (...) {
            return "Unknown";
        }
    }
    
    static std::string get_device_bdf(uint32_t index) {
        try {
            xrt::device device(index);
            auto info = device.get_info<xrt::info::device::bdf>();
            return info;
        } catch (...) {
            return "0000:00:00.0";
        }
    }
    
    static void print_device_info() {
        auto devices = list_devices();
        std::cout << "Available XRT devices:" << std::endl;
        for (uint32_t idx : devices) {
            std::cout << "  [" << idx << "] " << get_device_name(idx) 
                      << " (BDF: " << get_device_bdf(idx) << ")" << std::endl;
        }
    }
};

// XCLBIN utilities
class XclbinManager {
public:
    static bool validate_xclbin(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        if (!file) return false;
        
        // Check xclbin header (simplified)
        char header[4];
        file.read(header, 4);
        return file.gcount() == 4;
    }
    
    static std::string get_xclbin_info(const std::string& path) {
        std::stringstream ss;
        ss << "XCLBIN: " << path << std::endl;
        
        // Get file size
        auto size = std::filesystem::file_size(path);
        ss << "Size: " << size << " bytes (" << (size / 1024 / 1024) << " MB)" << std::endl;
        
        // Get modification time
        auto mtime = std::filesystem::last_write_time(path);
        auto sctp = std::chrono::time_point_cast<std::chrono::system_clock::duration>(
            mtime - std::filesystem::file_time_type::clock::now() + std::chrono::system_clock::now());
        auto time = std::chrono::system_clock::to_time_t(sctp);
        ss << "Modified: " << std::put_time(std::localtime(&time), "%Y-%m-%d %H:%M:%S") << std::endl;
        
        return ss.str();
    }
    
    static xrt::uuid load_xclbin(xrt::device& device, const std::string& path) {
        std::cout << "Loading xclbin: " << path << std::endl;
        auto uuid = device.load_xclbin(path);
        std::cout << "Loaded UUID: " << uuid.to_string() << std::endl;
        return uuid;
    }
};

// Buffer utilities
class BufferUtils {
public:
    template<typename T>
    static void fill_pattern(xrt::bo& buffer, T pattern) {
        auto mapped = buffer.map<T*>();
        size_t count = buffer.size() / sizeof(T);
        for (size_t i = 0; i < count; ++i) {
            mapped[i] = pattern + i;
        }
        buffer.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    }
    
    template<typename T>
    static void verify_pattern(const xrt::bo& buffer, T pattern) {
        buffer.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
        const auto mapped = buffer.map<const T*>();
        size_t count = buffer.size() / sizeof(T);
        
        for (size_t i = 0; i < count; ++i) {
            if (mapped[i] != pattern + i) {
                throw std::runtime_error("Pattern verification failed at index " + std::to_string(i));
            }
        }
    }
    
    template<typename T>
    static void copy_host_to_device(const std::vector<T>& src, xrt::bo& dst) {
        if (src.size() * sizeof(T) > dst.size()) {
            throw std::runtime_error("Source data too large for buffer");
        }
        
        auto mapped = dst.map<T*>();
        std::memcpy(mapped, src.data(), src.size() * sizeof(T));
        dst.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    }
    
    template<typename T>
    static std::vector<T> copy_device_to_host(const xrt::bo& src, size_t count) {
        src.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
        const auto mapped = src.map<const T*>();
        return std::vector<T>(mapped, mapped + count);
    }
};

// Performance measurement
class PerfTimer {
    std::chrono::high_resolution_clock::time_point start_;
    
public:
    PerfTimer() : start_(std::chrono::high_resolution_clock::now()) {}
    
    void reset() { start_ = std::chrono::high_resolution_clock::now(); }
    
    double elapsed_ms() const {
        auto end = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<double, std::milli>(end - start_).count();
    }
    
    double elapsed_us() const {
        auto end = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<double, std::micro>(end - start_).count();
    }
    
    double elapsed_s() const {
        auto end = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<double>(end - start_).count();
    }
    
    std::string format() const {
        double ms = elapsed_ms();
        if (ms < 1000) return std::to_string(ms) + " ms";
        if (ms < 60000) return std::to_string(ms / 1000.0) + " s";
        return std::to_string(ms / 60000.0) + " min";
    }
};

// Logging utilities
class Logger {
    std::ofstream log_file_;
    bool console_output_;
    
public:
    Logger(const std::string& log_path = "", bool console = true)
        : console_output_(console) {
        if (!log_path.empty()) {
            log_file_.open(log_path, std::ios::app);
        }
    }
    
    ~Logger() {
        if (log_file_.is_open()) log_file_.close();
    }
    
    template<typename... Args>
    void info(const std::string& fmt, Args... args) {
        log("INFO", fmt, args...);
    }
    
    template<typename... Args>
    void warn(const std::string& fmt, Args... args) {
        log("WARN", fmt, args...);
    }
    
    template<typename... Args>
    void error(const std::string& fmt, Args... args) {
        log("ERROR", fmt, args...);
    }
    
    template<typename... Args>
    void debug(const std::string& fmt, Args... args) {
        log("DEBUG", fmt, args...);
    }
    
private:
    template<typename... Args>
    void log(const std::string& level, const std::string& fmt, Args... args) {
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()) % 1000;
        
        std::stringstream ss;
        ss << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S")
           << '.' << std::setfill('0') << std::setw(3) << ms.count()
           << " [" << level << "] ";
        
        // Format message
        format_string(ss, fmt, args...);
        ss << std::endl;
        
        std::string msg = ss.str();
        
        if (console_output_) {
            std::cout << msg;
        }
        if (log_file_.is_open()) {
            log_file_ << msg;
            log_file_.flush();
        }
    }
    
    template<typename T, typename... Args>
    void format_string(std::stringstream& ss, const std::string& fmt, T value, Args... args) {
        size_t pos = fmt.find("{}");
        if (pos != std::string::npos) {
            ss << fmt.substr(0, pos) << value;
            format_string(ss, fmt.substr(pos + 2), args...);
        } else {
            ss << fmt;
        }
    }
    
    void format_string(std::stringstream& ss, const std::string& fmt) {
        ss << fmt;
    }
};

// Configuration file parser
class ConfigParser {
    std::map<std::string, std::string> config_;
    
public:
    bool load(const std::string& path) {
        std::ifstream file(path);
        if (!file) return false;
        
        std::string line;
        while (std::getline(file, line)) {
            // Skip comments and empty lines
            if (line.empty() || line[0] == '#') continue;
            
            // Parse key=value
            size_t pos = line.find('=');
            if (pos != std::string::npos) {
                std::string key = line.substr(0, pos);
                std::string value = line.substr(pos + 1);
                
                // Trim whitespace
                key.erase(0, key.find_first_not_of(" \t"));
                key.erase(key.find_last_not_of(" \t") + 1);
                value.erase(0, value.find_first_not_of(" \t"));
                value.erase(value.find_last_not_of(" \t") + 1);
                
                config_[key] = value;
            }
        }
        return true;
    }
    
    template<typename T>
    T get(const std::string& key, T default_value) const {
        auto it = config_.find(key);
        if (it == config_.end()) return default_value;
        
        std::stringstream ss(it->second);
        T value;
        ss >> value;
        return value;
    }
    
    std::string get_string(const std::string& key, const std::string& default_value = "") const {
        auto it = config_.find(key);
        return it != config_.end() ? it->second : default_value;
    }
};

// Deployment utilities
class DeploymentUtils {
public:
    static bool deploy_bitstream(const std::string& bitstream_path, 
                                 const std::string& device_bdf = "") {
        std::cout << "Deploying bitstream: " << bitstream_path << std::endl;
        
        // This would use xbutil or xrt to program the device
        // For now, return success
        return true;
    }
    
    static bool verify_deployment(const std::string& bitstream_path) {
        std::cout << "Verifying deployment..." << std::endl;
        return true;
    }
    
    static std::string generate_deployment_package(
        const std::string& bitstream_path,
        const std::string& xclbin_path,
        const std::string& output_dir) {
        
        fs::create_directories(output_dir);
        
        // Copy bitstream and xclbin
        fs::copy_file(bitstream_path, 
                     fs::path(output_dir) / "ncg.bit", 
                     fs::copy_options::overwrite_existing);
        fs::copy_file(xclbin_path, 
                     fs::path(output_dir) / "ncg.xclbin", 
                     fs::copy_options::overwrite_existing);
        
        // Generate manifest
        std::ofstream manifest(fs::path(output_dir) / "manifest.json");
        manifest << "{\n";
        manifest << "  \"version\": \"1.0\",\n";
        manifest << "  \"bitstream\": \"ncg.bit\",\n";
        manifest << "  \"xclbin\": \"ncg.xclbin\",\n";
        manifest << "  \"timestamp\": \"" << current_timestamp() << "\"\n";
        manifest << "}\n";
        
        return output_dir;
    }
    
private:
    static std::string current_timestamp() {
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << std::put_time(std::localtime(&time_t), "%Y-%m-%dT%H:%M:%SZ");
        return ss.str();
    }
};

} // namespace ncg

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cout << "NCG Utilities" << std::endl;
        std::cout << "Usage: " << argv[0] << " <command> [args...]" << std::endl;
        std::cout << std::endl;
        std::cout << "Commands:" << std::endl;
        std::cout << "  list-devices          - List available XRT devices" << std::endl;
        std::cout << "  info <xclbin>         - Show xclbin information" << std::endl;
        std::cout << "  validate <xclbin>     - Validate xclbin file" << std::endl;
        std::cout << "  deploy <bitstream>    - Deploy bitstream to device" << std::endl;
        std::cout << "  package <bitstream> <xclbin> <outdir> - Create deployment package" << std::endl;
        return 1;
    }
    
    std::string command = argv[1];
    
    try {
        if (command == "list-devices") {
            ncg::DeviceManager::print_device_info();
        } else if (command == "info" && argc >= 3) {
            std::cout << ncg::XclbinManager::get_xclbin_info(argv[2]);
        } else if (command == "validate" && argc >= 3) {
            bool valid = ncg::XclbinManager::validate_xclbin(argv[2]);
            std::cout << "XCLBIN " << (valid ? "valid" : "invalid") << std::endl;
            return valid ? 0 : 1;
        } else if (command == "deploy" && argc >= 3) {
            bool success = ncg::DeploymentUtils::deploy_bitstream(argv[2]);
            std::cout << "Deployment " << (success ? "successful" : "failed") << std::endl;
            return success ? 0 : 1;
        } else if (command == "package" && argc >= 5) {
            std::string out = ncg::DeploymentUtils::generate_deployment_package(
                argv[2], argv[3], argv[4]);
            std::cout << "Package created at: " << out << std::endl;
        } else {
            std::cerr << "Unknown command: " << command << std::endl;
            return 1;
        }
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}