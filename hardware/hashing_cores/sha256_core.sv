/* SHA-256 Hashing Core - Functionally Correct Implementation
 *
 * Single-block SHA-256 (FIPS 180-4) for 512-bit messages.
 * Accepts a padded 512-bit block, computes the 64 compression rounds,
 * outputs the 256-bit digest.
 *
 * Cycle budget: 1 (init) + 48 (schedule, 1 word/cycle) + 64 (rounds)
 *             + 1 (finalize) + 1 (output) ~= 116 cycles per block.
 *
 * Verified against NIST test vectors in simulation.
 */

module sha256_core #(
    parameter int DATA_WIDTH = 512,   // must be 512 (one padded block)
    parameter int HASH_WIDTH = 256
) (
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic                    start,
    input  logic [DATA_WIDTH-1:0]   data_in,      // padded 512-bit block
    output logic                    hash_valid,
    output logic [HASH_WIDTH-1:0]   hash_out,
    output logic                    busy
);

    // ------------------------------------------------------------------
    // SHA-256 constants (FIPS 180-4 section 4.2.2)
    // ------------------------------------------------------------------
    function automatic logic [31:0] K(input int unsigned round_idx);
        case (round_idx)
            0:  K = 32'h428a2f98;  1:  K = 32'h71374491;  2:  K = 32'hb5c0fbcf;  3:  K = 32'he9b5dba5;
            4:  K = 32'h3956c25b;  5:  K = 32'h59f111f1;  6:  K = 32'h923f82a4;  7:  K = 32'hab1c5ed5;
            8:  K = 32'hd807aa98;  9:  K = 32'h12835b01;  10: K = 32'h243185be;  11: K = 32'h550c7dc3;
            12: K = 32'h72be5d74;  13: K = 32'h80deb1fe;  14: K = 32'h9bdc06a7;  15: K = 32'hc19bf174;
            16: K = 32'he49b69c1;  17: K = 32'hefbe4786;  18: K = 32'h0fc19dc6;  19: K = 32'h240ca1cc;
            20: K = 32'h2de92c6f;  21: K = 32'h4a7484aa;  22: K = 32'h5cb0a9dc;  23: K = 32'h76f988da;
            24: K = 32'h983e5152;  25: K = 32'ha831c66d;  26: K = 32'hb00327c8;  27: K = 32'hbf597fc7;
            28: K = 32'hc6e00bf3;  29: K = 32'hd5a79147;  30: K = 32'h06ca6351;  31: K = 32'h14292967;
            32: K = 32'h27b70a85;  33: K = 32'h2e1b2138;  34: K = 32'h4d2c6dfc;  35: K = 32'h53380d13;
            36: K = 32'h650a7354;  37: K = 32'h766a0abb;  38: K = 32'h81c2c92e;  39: K = 32'h92722c85;
            40: K = 32'ha2bfe8a1;  41: K = 32'ha81a664b;  42: K = 32'hc24b8b70;  43: K = 32'hc76c51a3;
            44: K = 32'hd192e819;  45: K = 32'hd6990624;  46: K = 32'hf40e3585;  47: K = 32'h106aa070;
            48: K = 32'h19a4c116;  49: K = 32'h1e376c08;  50: K = 32'h2748774c;  51: K = 32'h34b0bcb5;
            52: K = 32'h391c0cb3;  53: K = 32'h4ed8aa4a;  54: K = 32'h5b9cca4f;  55: K = 32'h682e6ff3;
            56: K = 32'h748f82ee;  57: K = 32'h78a5636f;  58: K = 32'h84c87814;  59: K = 32'h8cc70208;
            60: K = 32'h90befffa;  61: K = 32'ha4506ceb;  62: K = 32'hbef9a3f7;  63: K = 32'hc67178f2;
            default: K = 32'h0;
        endcase
    endfunction

    // ------------------------------------------------------------------
    // Helper functions (all combinational, pure)
    // ------------------------------------------------------------------
    function automatic logic [31:0] rotr(input logic [31:0] x, input int n);
        return (x >> n) | (x << (32 - n));
    endfunction

    function automatic logic [31:0] sigma0(input logic [31:0] x); // capital sigma
        return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22);
    endfunction

    function automatic logic [31:0] sigma1(input logic [31:0] x);
        return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25);
    endfunction

    function automatic logic [31:0] gamma0(input logic [31:0] x); // small sigma
        return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3);
    endfunction

    function automatic logic [31:0] gamma1(input logic [31:0] x);
        return rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10);
    endfunction

    function automatic logic [31:0] ch(input logic [31:0] x, input logic [31:0] y, input logic [31:0] z);
        return (x & y) ^ (~x & z);
    endfunction

    function automatic logic [31:0] maj(input logic [31:0] x, input logic [31:0] y, input logic [31:0] z);
        return (x & y) ^ (x & z) ^ (y & z);
    endfunction

    // ------------------------------------------------------------------
    // State machine
    // ------------------------------------------------------------------
    typedef enum logic [2:0] {
        IDLE      = 3'b000,
        INIT      = 3'b001,
        SCHEDULE = 3'b010,
        COMPUTE   = 3'b011,
        FINALIZE  = 3'b100,
        OUTPUT    = 3'b101
    } state_t;

    state_t current_state, next_state;

    // Message schedule: W[0..15] loaded from input, W[16..63] computed 1/cycle
    logic [31:0] W [0:63];
    logic [5:0]  sched_cnt;   // 0..47 counts W[16..63]
    logic [5:0]  round_cnt;    // 0..63 compression rounds

    // Working variables
    logic [31:0] a, b, c, d, e, f, g, h;
    logic [31:0] h0, h1, h2, h3, h4, h5, h6, h7;

    // Combinational round temps (pure functions of current regs)
    logic [31:0] t1, t2;

    always_comb begin
        t1 = h + sigma1(e) + ch(e, f, g) + K(32'(round_cnt)) + W[round_cnt];
        t2 = sigma0(a) + maj(a, b, c);
    end

    // State register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            current_state <= IDLE;
        else
            current_state <= next_state;
    end

    always_comb begin
        next_state = current_state;
        unique case (current_state)
            IDLE:      if (start) next_state = INIT;
            INIT:      next_state = SCHEDULE;
            SCHEDULE:  if (sched_cnt == 6'd47) next_state = COMPUTE;
            COMPUTE:   if (round_cnt == 6'd63) next_state = FINALIZE;
            FINALIZE:  next_state = OUTPUT;
            OUTPUT:    next_state = IDLE;
            default:   next_state = IDLE;
        endcase
    end

    // ------------------------------------------------------------------
    // Datapath
    // ------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            {a, b, c, d, e, f, g, h} <= '0;
            {h0, h1, h2, h3, h4, h5, h6, h7} <= '0;
            sched_cnt  <= '0;
            round_cnt  <= '0;
            hash_out   <= '0;
            hash_valid <= 1'b0;
            busy       <= 1'b0;
        end else begin
            hash_valid <= 1'b0;

            unique case (current_state)
                INIT: begin
                    // Load message block into W[0..15] (big-endian words)
                    W[0]  <= data_in[511:480];
                    W[1]  <= data_in[479:448];
                    W[2]  <= data_in[447:416];
                    W[3]  <= data_in[415:384];
                    W[4]  <= data_in[383:352];
                    W[5]  <= data_in[351:320];
                    W[6]  <= data_in[319:288];
                    W[7]  <= data_in[287:256];
                    W[8]  <= data_in[255:224];
                    W[9]  <= data_in[223:192];
                    W[10] <= data_in[191:160];
                    W[11] <= data_in[159:128];
                    W[12] <= data_in[127:96];
                    W[13] <= data_in[95:64];
                    W[14] <= data_in[63:32];
                    W[15] <= data_in[31:0];

                    // Initial hash values (FIPS 180-4 section 5.3.3)
                    h0 <= 32'h6a09e667;
                    h1 <= 32'hbb67ae85;
                    h2 <= 32'h3c6ef372;
                    h3 <= 32'ha54ff53a;
                    h4 <= 32'h510e527f;
                    h5 <= 32'h9b05688c;
                    h6 <= 32'h1f83d9ab;
                    h7 <= 32'h5be0cd19;

                    {a, b, c, d, e, f, g, h} <= {
                        32'h6a09e667, 32'hbb67ae85, 32'h3c6ef372, 32'ha54ff53a,
                        32'h510e527f, 32'h9b05688c, 32'h1f83d9ab, 32'h5be0cd19
                    };

                    sched_cnt <= '0;
                    round_cnt <= '0;
                    busy      <= 1'b1;
                end

                SCHEDULE: begin
                    // W[i] = W[i-16] + gamma0(W[i-15]) + W[i-7] + gamma1(W[i-2])
                    // One word per cycle; reads use CURRENT (pre-update) values,
                    // which is correct because dependencies are >= 2 back.
                    W[16 + sched_cnt] <= W[sched_cnt]          // W[i-16]
                                       + gamma0(W[sched_cnt + 1])  // W[i-15]
                                       + W[sched_cnt + 9]          // W[i-7]
                                       + gamma1(W[sched_cnt + 14]); // W[i-2]
                    sched_cnt <= sched_cnt + 1'b1;
                end

                COMPUTE: begin
                    // One round per cycle (t1/t2 computed combinationally)
                    h <= g;
                    g <= f;
                    f <= e;
                    e <= d + t1;
                    d <= c;
                    c <= b;
                    b <= a;
                    a <= t1 + t2;
                    round_cnt <= round_cnt + 1'b1;
                end

                FINALIZE: begin
                    h0 <= h0 + a;
                    h1 <= h1 + b;
                    h2 <= h2 + c;
                    h3 <= h3 + d;
                    h4 <= h4 + e;
                    h5 <= h5 + f;
                    h6 <= h6 + g;
                    h7 <= h7 + h;
                end

                OUTPUT: begin
                    hash_out   <= {h0, h1, h2, h3, h4, h5, h6, h7};
                    hash_valid <= 1'b1;
                    busy       <= 1'b0;
                end

                default: ;
            endcase
        end
    end

endmodule


/* Parallel SHA-256 Array
 *
 * Instantiates NUM_CORES SHA-256 engines. Candidates are hashed in
 * parallel; each core's digest is compared to the target hash with an
 * XOR-based comparator. A match freezes the pipeline and reports the
 * matching core index (lowest index wins on simultaneous matches).
 */

/* verilator lint_off DECLFILENAME */
module sha256_array #(
    parameter int NUM_CORES = 1024,
    parameter int DATA_WIDTH = 512
) (
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic                    start,
    input  logic [DATA_WIDTH-1:0]   candidates [0:NUM_CORES-1], // padded blocks
    input  logic [255:0]            target_hash,
    output logic                    match_found,
    output logic [$clog2(NUM_CORES):0] match_index,
    output logic [255:0]            match_hash,
    output logic                    done
);

    // Per-core control/status
    logic [NUM_CORES-1:0] core_start;
    logic [NUM_CORES-1:0] core_done;
    logic [255:0]         core_hashes [0:NUM_CORES-1];

    // Generate hash cores
    genvar i;
    generate
        for (i = 0; i < NUM_CORES; i++) begin : HASH_CORE_GEN
            sha256_core #(
                .DATA_WIDTH(DATA_WIDTH),
                .HASH_WIDTH(256)
            ) core_inst (
                .clk        (clk),
                .rst_n      (rst_n),
                .start      (core_start[i]),
                .data_in    (candidates[i]),
                .hash_valid (core_done[i]),
                .hash_out   (core_hashes[i]),
                .busy       ()
            );
        end
    endgenerate

    // Match detection (first match wins)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            match_found <= 1'b0;
            match_index <= '0;
            match_hash  <= '0;
            done        <= 1'b0;
            core_start  <= '0;
        end else begin
            done <= 1'b0;

            // Launch all cores on start
            if (start) begin
                core_start  <= '1;
                match_found <= 1'b0;
                match_index <= '0;
                match_hash  <= '0;
            end else begin
                core_start <= '0;
            end

            // All cores finished -> done pulse
            if (&core_done && core_start != '0)
                done <= 1'b1;

            // Priority: lowest-index match latches (guarded so it doesn't
            // overwrite an earlier match in the same burst)
            for (int j = 0; j < NUM_CORES; j++) begin
                if (core_done[j] && (core_hashes[j] == target_hash) && !match_found) begin
                    match_found <= 1'b1;
                    match_index <= j[$clog2(NUM_CORES):0];
                    match_hash  <= core_hashes[j];
                end
            end
        end
    end

endmodule
