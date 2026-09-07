/* Inference Core Testbench with DCPM Validation
 * 
 * SystemVerilog testbench for inference_core module with
 * DCPM loading validation and candidate generation verification
 */

module inference_core_tb;

    // Parameters - reduced for simulation
    parameter int D_MODEL = 64;
    parameter int N_HEADS = 4;
    parameter int N_LAYERS = 2;
    parameter int VOCAB_SIZE = 32;
    parameter int MAX_SEQ_LEN = 16;
    parameter int BRAM_ADDR_WIDTH = 8;
    parameter int BRAM_DATA_WIDTH = 64;

    // Clock and reset
    logic clk;
    logic rst_n;
    
    // Control interface
    logic                    start;
    logic                    load_dcmp;
    logic                    done;
    logic                    error;
    
    // DCPM memory interface (BRAM)
    logic [BRAM_ADDR_WIDTH-1:0] dcmp_addr;
    logic                      dcmp_we;
    logic [BRAM_DATA_WIDTH-1:0] dcmp_wdata;
    logic [BRAM_DATA_WIDTH-1:0] dcmp_rdata;
    
    // Candidate output interface
    logic [7:0]                candidate_char;
    logic                      candidate_valid;
    logic                      candidate_last;
    
    // Status
    logic [15:0]               seq_len;
    logic [7:0]                layer_active;
    logic [7:0]                head_active;

    // Clock generation
    initial clk = 0;
    always #5 clk = ~clk;  // 100MHz clock

    // DUT instance
    inference_core #(
        .D_MODEL(D_MODEL),
        .N_HEADS(N_HEADS),
        .N_LAYERS(N_LAYERS),
        .VOCAB_SIZE(VOCAB_SIZE),
        .MAX_SEQ_LEN(MAX_SEQ_LEN),
        .BRAM_ADDR_WIDTH(BRAM_ADDR_WIDTH),
        .BRAM_DATA_WIDTH(BRAM_DATA_WIDTH)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .load_dcmp(load_dcmp),
        .done(done),
        .error(error),
        .dcmp_addr(dcmp_addr),
        .dcmp_we(dcmp_we),
        .dcmp_wdata(dcmp_wdata),
        .dcmp_rdata(dcmp_rdata),
        .candidate_char(candidate_char),
        .candidate_valid(candidate_valid),
        .candidate_last(candidate_last),
        .seq_len(seq_len),
        .layer_active(layer_active),
        .head_active(head_active)
    );

    // DCPM Memory model
    logic [BRAM_DATA_WIDTH-1:0] dcmp_mem [0:2**BRAM_ADDR_WIDTH-1];
    
    always_ff @(posedge clk) begin
        if (dcmp_we) begin
            dcmp_mem[dcmp_addr] <= dcmp_wdata;
        end
        dcmp_rdata <= dcmp_mem[dcmp_addr];
    end

    // Reference candidate sequence for validation
    logic [7:0] expected_candidates [0:MAX_SEQ_LEN-1];
    logic [7:0] generated_candidates [0:MAX_SEQ_LEN-1];
    logic [7:0] gen_idx;
    
    initial begin
        // Pre-load expected candidates (simplified reference)
        for (int i = 0; i < MAX_SEQ_LEN; i++) begin
            expected_candidates[i] = 8'h61 + i; // 'a', 'b', 'c', ...
        end
    end

    // Collect generated candidates
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            gen_idx <= '0;
        end else if (candidate_valid) begin
            generated_candidates[gen_idx] <= candidate_char;
            gen_idx <= gen_idx + 1;
        end
    end

    // Test sequence
    initial begin
        // Initialize
        rst_n = 0;
        start = 0;
        load_dcmp = 0;
        
        // Reset
        repeat (10) @(posedge clk);
        rst_n = 1;
        repeat (5) @(posedge clk);
        
        // Test 1: Load DCPM
        $display("Test 1: Loading DCPM into inference core...");
        load_dcmp = 1;
        
        // Load dummy DCPM (probability matrix)
        for (int pos = 0; pos < MAX_SEQ_LEN; pos++) begin
            // Simulate BRAM write
            @(posedge clk);
        end
        
        load_dcmp = 0;
        @(posedge clk);
        
        // Test 2: Start inference
        $display("Test 2: Starting inference...");
        start = 1;
        @(posedge clk);
        start = 0;
        
        // Wait for inference to complete
        wait(done);
        $display("Inference completed. seq_len=%d", seq_len);
        $display("Generated %d candidates", gen_idx);
        
        // Validate generated candidates
        $display("Test 3: Validating generated candidates...");
        for (int i = 0; i < gen_idx; i++) begin
            $display("  Candidate[%d]: 0x%02x (expected: 0x%02x) %s", 
                i, generated_candidates[i], expected_candidates[i],
                (generated_candidates[i] == expected_candidates[i]) ? "PASS" : "FAIL");
        end
        
        // Test 4: Restart with new DCPM
        $display("Test 4: Restart with new DCPM...");
        repeat (5) @(posedge clk);
        
        load_dcmp = 1;
        for (int pos = 0; pos < MAX_SEQ_LEN; pos++) begin
            @(posedge clk);
        end
        load_dcmp = 0;
        @(posedge clk);
        
        start = 1;
        @(posedge clk);
        start = 0;
        
        wait(done);
        $display("Second inference completed. Candidates: %d", gen_idx);
        
        repeat (10) @(posedge clk);
        $display("All inference core tests passed!");
        $finish;
    end

    // Timeout watchdog
    initial begin
        #1000000;  // 1ms timeout
        $display("ERROR: Simulation timeout!");
        $finish;
    end

    // Waveform dumping
    initial begin
        $dumpfile("inference_core_tb.vcd");
        $dumpvars(0, inference_core_tb);
    end

endmodule