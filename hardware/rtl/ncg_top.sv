/* NCG Top-Level Module
 * 
 * Integrates Inference Core + Hashing Array
 * Top-level for FPGA synthesis
 */

module ncg_top #(
    // Inference Core Parameters
    parameter int D_MODEL = 256,
    parameter int N_HEADS = 8,
    parameter int N_LAYERS = 6,
    parameter int VOCAB_SIZE = 96,
    parameter int MAX_SEQ_LEN = 64,
    
    // Hashing Array Parameters
    parameter int NUM_HASH_CORES = 1024,
    parameter int HASH_WIDTH = 256,
    
    // Memory Parameters
    parameter int BRAM_ADDR_WIDTH = 12,
    parameter int BRAM_DATA_WIDTH = 512,
    parameter int HBM_ADDR_WIDTH = 32,
    parameter int HBM_DATA_WIDTH = 256
) (
    // Global
    input  logic                    clk,
    input  logic                    rst_n,
    
    // PCIe Interface (simplified)
    input  logic                    pcie_valid,
    input  logic [255:0]            pcie_data,
    input  logic [1:0]              pcie_cmd,  // 00=load_dcmp, 01=start_search, 10=read_result
    output logic                    pcie_ready,
    output logic [255:0]            pcie_rdata,
    
    // HBM Interface (for bulk DCPM storage)
    output logic [HBM_ADDR_WIDTH-1:0] hbm_addr,
    output logic                      hbm_we,
    output logic [HBM_DATA_WIDTH-1:0] hbm_wdata,
    input  logic [HBM_DATA_WIDTH-1:0] hbm_rdata,
    output logic                      hbm_req,
    input  logic                      hbm_ack,
    
    // Status
    output logic [3:0]                status,
    output logic                      match_found,
    output logic [255:0]              match_hash,
    output logic [$clog2(NUM_HASH_CORES):0] match_core_id
);

    // PCIe command codes
    localparam logic [1:0] CMD_LOAD_DCPM   = 2'b00;
    localparam logic [1:0] CMD_START_SEARCH = 2'b01;
    localparam logic [1:0] CMD_READ_RESULT = 2'b10;
    
    // Status codes
    localparam logic [3:0] STAT_IDLE       = 4'h0;
    localparam logic [3:0] STAT_LOADING    = 4'h1;
    localparam logic [3:0] STAT_INFERENCE  = 4'h2;
    localparam logic [3:0] STAT_HASHING    = 4'h3;
    localparam logic [3:0] STAT_DONE       = 4'h4;
    localparam logic [3:0] STAT_ERROR      = 4'hF;

    // Internal signals
    logic inference_start, inference_done;
    logic hashing_start, hashing_done;
    logic [HASH_WIDTH-1:0] target_hash;
    logic dcmp_load_done;
    
    // Inference core interface
    logic                    inf_dcmp_we;
    logic [BRAM_ADDR_WIDTH-1:0] inf_dcmp_addr;
    logic [BRAM_DATA_WIDTH-1:0] inf_dcmp_wdata;
    logic [BRAM_DATA_WIDTH-1:0] inf_dcmp_rdata;
    logic [7:0]                candidate_char;
    logic                      candidate_valid;
    logic                      candidate_last;
    logic [15:0]               seq_len;
    
    // Hashing array interface
    logic [BRAM_DATA_WIDTH-1:0] candidates [0:NUM_HASH_CORES-1];
    logic [HASH_WIDTH-1:0]      match_hash_int;
    logic [$clog2(NUM_HASH_CORES):0] match_core_id_int;

    // PCIe command handler
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            status <= STAT_IDLE;
            pcie_ready <= 1'b1;
            inference_start <= 1'b0;
            hashing_start <= 1'b0;
            target_hash <= '0;
            dcmp_load_done <= 1'b0;
            hbm_req <= 1'b0;
            hbm_we <= 1'b0;
            hbm_addr <= '0;
            hbm_wdata <= '0;
        end else begin
            pcie_ready <= 1'b0;
            
            if (pcie_valid && pcie_ready) begin
                case (pcie_cmd)
                    CMD_LOAD_DCPM: begin
                        status <= STAT_LOADING;
                        hbm_req <= 1'b1;
                        hbm_we <= 1'b1;
                        hbm_addr <= pcie_data[HBM_ADDR_WIDTH-1:0];
                        hbm_wdata <= pcie_data[255:256-HBM_DATA_WIDTH];
                        dcmp_load_done <= 1'b0;
                    end
                    CMD_START_SEARCH: begin
                        status <= STAT_INFERENCE;
                        target_hash <= pcie_data[HASH_WIDTH-1:0];
                        inference_start <= 1'b1;
                        dcmp_load_done <= 1'b1;
                    end
                    CMD_READ_RESULT: begin
                        pcie_rdata <= {224'h0, match_found, 7'h0, match_core_id_int, 32'h0, match_hash_int[255:0]};
                        pcie_ready <= 1'b1;
                    end
                endcase
            end
            
            // Inference core handshake
            if (inference_start && inference_done) begin
                inference_start <= 1'b0;
                status <= STAT_HASHING;
                hashing_start <= 1'b1;
            end
            
            if (hashing_start && hashing_done) begin
                hashing_start <= 1'b0;
                status <= STAT_DONE;
            end
        end
    end

    // Inference Core Instance
    inference_core #(
        .D_MODEL(D_MODEL),
        .N_HEADS(N_HEADS),
        .N_LAYERS(N_LAYERS),
        .VOCAB_SIZE(VOCAB_SIZE),
        .MAX_SEQ_LEN(MAX_SEQ_LEN),
        .BRAM_ADDR_WIDTH(BRAM_ADDR_WIDTH),
        .BRAM_DATA_WIDTH(BRAM_DATA_WIDTH)
    ) inference_core_inst (
        .clk(clk),
        .rst_n(rst_n),
        .start(inference_start),
        .load_dcmp(!dcmp_load_done),
        .done(inference_done),
        .error(),
        .dcmp_addr(inf_dcmp_addr),
        .dcmp_we(inf_dcmp_we),
        .dcmp_wdata(inf_dcmp_wdata),
        .dcmp_rdata(inf_dcmp_rdata),
        .candidate_char(candidate_char),
        .candidate_valid(candidate_valid),
        .candidate_last(candidate_last),
        .seq_len(seq_len),
        .layer_active(),
        .head_active()
    );

    // Candidate buffer for hashing array
    logic [$clog2(NUM_HASH_CORES):0] candidate_cnt;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            candidate_cnt <= '0;
            for (int i = 0; i < NUM_HASH_CORES; i++) candidates[i] <= '0;
        end else if (candidate_valid && candidate_cnt < NUM_HASH_CORES) begin
            candidates[candidate_cnt] <= {{(BRAM_DATA_WIDTH-8){1'b0}}, candidate_char};
            candidate_cnt <= candidate_cnt + 1;
        end else if (hashing_start) begin
            candidate_cnt <= '0;
        end
    end

    // Hashing Array Instance
    sha256_array #(
        .NUM_CORES(NUM_HASH_CORES),
        .DATA_WIDTH(BRAM_DATA_WIDTH)
    ) hashing_array_inst (
        .clk(clk),
        .rst_n(rst_n),
        .start(hashing_start),
        .candidates(candidates),
        .target_hash(target_hash),
        .match_found(match_found),
        .match_index(match_core_id_int),
        .match_hash(match_hash_int),
        .done(hashing_done)
    );

    // Output assignments
    assign match_hash = match_hash_int;
    assign match_core_id = match_core_id_int;

endmodule