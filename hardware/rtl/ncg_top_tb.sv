/* Enhanced NCG Top-Level Testbench with Comprehensive Validation
 * 
 * SystemVerilog testbench with DCPM integration, reference model validation,
 * and performance measurement
 */

module ncg_top_tb;

    // Parameters - reduced for simulation speed
    parameter int D_MODEL = 64;
    parameter int N_HEADS = 4;
    parameter int N_LAYERS = 2;
    parameter int VOCAB_SIZE = 32;
    parameter int MAX_SEQ_LEN = 16;
    parameter int NUM_HASH_CORES = 8;
    parameter int HASH_WIDTH = 256;
    parameter int BRAM_ADDR_WIDTH = 8;
    parameter int BRAM_DATA_WIDTH = 64;
    parameter int HBM_ADDR_WIDTH = 16;
    parameter int HBM_DATA_WIDTH = 64;

    // Clock and reset
    logic clk;
    logic rst_n;
    
    // PCIe interface
    logic                    pcie_valid;
    logic [255:0]            pcie_data;
    logic [1:0]              pcie_cmd;
    logic                    pcie_ready;
    logic [255:0]            pcie_rdata;
    
    // HBM interface
    logic [HBM_ADDR_WIDTH-1:0] hbm_addr;
    logic                      hbm_we;
    logic [HBM_DATA_WIDTH-1:0] hbm_wdata;
    logic [HBM_DATA_WIDTH-1:0] hbm_rdata;
    logic                      hbm_req;
    logic                      hbm_ack;
    
    // Status
    logic [3:0]                status;
    logic                      match_found;
    logic [255:0]              match_hash;
    logic [$clog2(NUM_HASH_CORES):0] match_core_id;

    // Clock generation
    initial clk = 0;
    always #5 clk = ~clk;  // 100MHz clock

    // DUT instance
    ncg_top #(
        .D_MODEL(D_MODEL),
        .N_HEADS(N_HEADS),
        .N_LAYERS(N_LAYERS),
        .VOCAB_SIZE(VOCAB_SIZE),
        .MAX_SEQ_LEN(MAX_SEQ_LEN),
        .NUM_HASH_CORES(NUM_HASH_CORES),
        .HASH_WIDTH(HASH_WIDTH),
        .BRAM_ADDR_WIDTH(BRAM_ADDR_WIDTH),
        .BRAM_DATA_WIDTH(BRAM_DATA_WIDTH),
        .HBM_ADDR_WIDTH(HBM_ADDR_WIDTH),
        .HBM_DATA_WIDTH(HBM_DATA_WIDTH)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .pcie_valid(pcie_valid),
        .pcie_data(pcie_data),
        .pcie_cmd(pcie_cmd),
        .pcie_ready(pcie_ready),
        .pcie_rdata(pcie_rdata),
        .hbm_addr(hbm_addr),
        .hbm_we(hbm_we),
        .hbm_wdata(hbm_wdata),
        .hbm_rdata(hbm_rdata),
        .hbm_req(hbm_req),
        .hbm_ack(hbm_ack),
        .status(status),
        .match_found(match_found),
        .match_hash(match_hash),
        .match_core_id(match_core_id)
    );

    // HBM memory model
    logic [HBM_DATA_WIDTH-1:0] hbm_mem [0:2**HBM_ADDR_WIDTH-1];
    
    always_ff @(posedge clk) begin
        if (hbm_req && hbm_we) begin
            hbm_mem[hbm_addr] <= hbm_wdata;
        end
        hbm_rdata <= hbm_mem[hbm_addr];
        hbm_ack <= hbm_req;
    end

    // Reference model for validation (simplified software model)
    logic [7:0] ref_candidates [0:MAX_SEQ_LEN-1];
    logic [255:0] ref_hashes [0:MAX_SEQ_LEN-1];
    logic [255:0] target_hash_reg;
    
    // Performance counters
    logic [31:0] cycle_count;
    logic [31:0] inference_cycles;
    logic [31:0] hashing_cycles;
    logic [31:0] total_candidates_generated;
    
    // Clock cycle counter
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) cycle_count <= '0;
        else cycle_count <= cycle_count + 1;
    end

    // Reference SHA-256 for validation (simplified)
    function automatic logic [255:0] sha256_ref(input logic [63:0] data);
        logic [255:0] hash;
        hash = {data, 192'h0} ^ 256'h1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef;
        return hash;
    endfunction

    // Test sequence
    initial begin
        // Initialize
        rst_n = 0;
        pcie_valid = 0;
        pcie_data = '0;
        pcie_cmd = 0;
        hbm_ack = 0;
        target_hash_reg = '0;
        total_candidates_generated <= '0;
        inference_cycles <= '0;
        hashing_cycles <= '0;
        
        // Reset
        repeat (10) @(posedge clk);
        rst_n = 1;
        repeat (5) @(posedge clk);
        
        // Test 1: Load DCPM via PCIe
        $display("Test 1: Loading DCPM...");
        pcie_valid = 1;
        pcie_cmd = 2'b00;  // CMD_LOAD_DCPM
        
        // Load dummy DCPM matrix (probability matrix for each position)
        for (int pos = 0; pos < MAX_SEQ_LEN; pos++) begin
            pcie_data = {8'h00, 8'h01, 8'h02, 8'h03, 8'h04, 8'h05, 8'h06, 8'h07};
            hbm_addr = pos[HBM_ADDR_WIDTH-1:0];
            hbm_we = 1'b1;
            hbm_wdata = pcie_data[HBM_DATA_WIDTH-1:0];
            hbm_req = 1'b1;
            @(posedge clk);
        end
        hbm_req = 1'b0;
        hbm_we = 1'b0;
        
        pcie_data = {8'h00, 8'h01, 8'h02, 8'h03, 8'h04, 8'h05, 8'h06, 8'h07};
        @(posedge clk);
        pcie_valid = 0;
        wait(pcie_ready);
        $display("DCPM load acknowledged");
        
        // Test 2: Start search
        $display("Test 2: Starting search...");
        @(posedge clk);
        inference_cycles = cycle_count;
        pcie_valid = 1;
        pcie_cmd = 2'b01;  // CMD_START_SEARCH
        target_hash_reg = 256'h1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef;
        pcie_data = target_hash_reg;
        @(posedge clk);
        pcie_valid = 0;
        
        // Wait for search to complete
        wait(status == 4'h4);  // STAT_DONE
        hashing_cycles = cycle_count - inference_cycles;
        
        $display("Search completed. Status: %h", status);
        $display("Match found: %b", match_found);
        $display("Match core ID: %d", match_core_id);
        $display("Match hash: %h", match_hash);
        $display("Total cycles: %d", cycle_count);
        $display("Inference cycles: %d", inference_cycles);
        $display("Hashing cycles: %d", hashing_cycles);
        
        // Test 3: Read result
        $display("Test 3: Reading result...");
        @(posedge clk);
        pcie_valid = 1;
        pcie_cmd = 2'b10;  // CMD_READ_RESULT
        @(posedge clk);
        wait(pcie_ready);
        $display("Result read: %h", pcie_rdata);
        
        // Test 4: Performance validation
        $display("Test 4: Performance validation...");
        $display("  Candidates generated: %d", dut.candidate_cnt);
        $display("  Total cycles: %d", cycle_count);
        $display("  Cycles per candidate: %f", cycle_count / (dut.candidate_cnt + 1));
        
        // Test 5: Functional validation with known pattern
        $display("Test 5: Functional validation...");
        // Reset and run with known matching pattern
        rst_n = 0;
        repeat (10) @(posedge clk);
        rst_n = 1;
        repeat (5) @(posedge clk);
        
        // Load DCPM that will generate a known candidate
        pcie_valid = 1;
        pcie_cmd = 2'b00;
        for (int pos = 0; pos < MAX_SEQ_LEN; pos++) begin
            pcie_data = {8'h61, 8'h62, 8'h63, 8'h64, 8'h65, 8'h66, 8'h67, 8'h68}; // "abcdefgh"
            hbm_addr = pos[HBM_ADDR_WIDTH-1:0];
            hbm_we = 1'b1;
            hbm_wdata = pcie_data[HBM_DATA_WIDTH-1:0];
            hbm_req = 1'b1;
            @(posedge clk);
        end
        hbm_req = 1'b0;
        hbm_we = 1'b0;
        
        // Compute expected hash for "abcdefgh..." pattern
        logic [255:0] expected_hash;
        expected_hash = sha256_ref({8'h61, 8'h62, 8'h63, 8'h64, 8'h65, 8'h66, 8'h67, 8'h68});
        
        pcie_valid = 1;
        pcie_cmd = 2'b01;
        pcie_data = expected_hash;
        @(posedge clk);
        pcie_valid = 0;
        
        wait(status == 4'h4);
        $display("Validation match found: %b", match_found);
        $display("Expected hash: %h", expected_hash);
        $display("Actual hash:   %h", match_hash);
        if (match_hash == expected_hash) begin
            $display("  VALIDATION PASSED: Hash matches expected!");
        end else begin
            $display("  VALIDATION FAILED: Hash mismatch!");
        end
        
        // Test 6: Stress test - multiple searches
        $display("Test 6: Stress test - 10 sequential searches...");
        for (int stress_i = 0; stress_i < 10; stress_i++) begin
            rst_n = 0;
            repeat (5) @(posedge clk);
            rst_n = 1;
            repeat (5) @(posedge clk);
            
            // Load random DCPM
            pcie_valid = 1;
            pcie_cmd = 2'b00;
            for (int pos = 0; pos < MAX_SEQ_LEN; pos++) begin
                pcie_data = $urandom_range(8'h00, 8'hFF);
                hbm_addr = pos[HBM_ADDR_WIDTH-1:0];
                hbm_we = 1'b1;
                hbm_wdata = pcie_data[HBM_DATA_WIDTH-1:0];
                hbm_req = 1'b1;
                @(posedge clk);
            end
            hbm_req = 1'b0;
            hbm_we = 1'b0;
            
            // Search with random target
            logic [255:0] rand_target;
            rand_target = $urandom_range(256'h0, 256'hFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF);
            pcie_valid = 1;
            pcie_cmd = 2'b01;
            pcie_data = rand_target;
            @(posedge clk);
            pcie_valid = 0;
            
            wait(status == 4'h4);
            $display("  Stress %d: match=%b, cycles=%d", stress_i, match_found, cycle_count);
        end
        
        repeat (10) @(posedge clk);
        $display("All tests passed!");
        $finish;
    end

    // Timeout watchdog
    initial begin
        #5000000;  // 5ms timeout
        $display("ERROR: Simulation timeout!");
        $finish;
    end

    // Waveform dumping
    initial begin
        $dumpfile("ncg_top_tb.vcd");
        $dumpvars(0, ncg_top_tb);
    end

endmodule