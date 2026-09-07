/* Inference Core - Functional Implementation
 *
 * NCG Neuromorphic Inference Core
 *
 * Functional behavior: loads a DCPM (Dynamic Candidate Probability Matrix)
 * into internal rows, then streams candidates by walking the matrix:
 *   - Each row = one candidate position's character distribution (8 bytes)
 *   - A permutation state machine cycles through candidates by rotating
 *     which byte of each row is selected (deterministic walk of the
 *     probability matrix, mirroring the Permutation State Machine in the
 *     NCG architecture spec).
 *
 * In the full implementation the DCPM is produced by INT4 transformer
 * blocks; this core implements the matrix-walk + stream-out stage that
 * feeds the hashing array.
 */

module inference_core #(
    parameter int MAX_SEQ_LEN = 64,          // candidates per start pulse
    parameter int CANDIDATE_LEN = 16,         // characters per candidate
    parameter int BRAM_ADDR_WIDTH = 12,
    parameter int BRAM_DATA_WIDTH = 512
) (
    input  logic                    clk,
    input  logic                    rst_n,

    // Control interface
    input  logic                    start,
    input  logic                    load_dcmp,
    output logic                    done,
    output logic                    error,

    // DCPM memory interface (BRAM)
    output logic [BRAM_ADDR_WIDTH-1:0] dcmp_addr,
    output logic                      dcmp_we,
    output logic [BRAM_DATA_WIDTH-1:0] dcmp_wdata,
    input  logic [BRAM_DATA_WIDTH-1:0] dcmp_rdata,

    // Candidate output interface (stream of chars forming candidates)
    output logic [7:0]                candidate_char,
    output logic                      candidate_valid,
    output logic                      candidate_last,

    // Status
    output logic [15:0]               seq_len,
    output logic [7:0]                layer_active,
    output logic [7:0]                head_active
);

    localparam int POS_W = $clog2(CANDIDATE_LEN);

    // ------------------------------------------------------------------
    // State machine
    // ------------------------------------------------------------------
    typedef enum logic [2:0] {
        IDLE        = 3'b000,
        LOAD_DCPM   = 3'b001,
        GENERATE    = 3'b010,
        DONE_STATE  = 3'b011
    } state_t;

    state_t current_state, next_state;

    // Internal DCPM storage: one row per candidate position
    logic [BRAM_DATA_WIDTH-1:0] dcmp_rows [0:CANDIDATE_LEN-1];

    // Counters / indices (single-driver: only the main always_ff writes these)
    logic [POS_W-1:0]  pos_cnt;          // position within candidate
    logic [15:0]       cand_cnt;         // candidate index (rotation seed)
    logic [15:0]       candidates_out;   // total candidates streamed
    logic [POS_W:0]    load_cnt;         // row counter during LOAD_DCPM

    // ------------------------------------------------------------------
    // State transitions
    // ------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            current_state <= IDLE;
        else
            current_state <= next_state;
    end

    always_comb begin
        next_state = current_state;
        unique case (current_state)
            IDLE: begin
                if (load_dcmp)
                    next_state = LOAD_DCPM;
                else if (start)
                    next_state = GENERATE;
            end
            LOAD_DCPM: begin
                if (load_cnt == 5'(CANDIDATE_LEN))    // all rows captured
                    next_state = IDLE;
            end
            GENERATE: begin
                if (candidates_out == 16'(MAX_SEQ_LEN))
                    next_state = DONE_STATE;
            end
            DONE_STATE: begin
                next_state = IDLE;
            end
            default: next_state = IDLE;
        endcase
    end

    // ------------------------------------------------------------------
    // Byte permutation selection: candidate n, position p selects
    // byte (n + p) mod 8 of row p. Deterministic walk of the matrix so
    // successive candidates differ while staying in top-probability bytes.
    // Pure expression - no separate driver, used directly below.
    // ------------------------------------------------------------------

    // ------------------------------------------------------------------
    // Datapath (single driver for all registers)
    // ------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            done            <= 1'b0;
            error           <= 1'b0;
            seq_len         <= '0;
            layer_active    <= '0;
            head_active     <= '0;
            pos_cnt         <= '0;
            cand_cnt        <= '0;
            candidates_out  <= '0;
            load_cnt        <= '0;
            candidate_valid <= 1'b0;
            candidate_last  <= 1'b0;
            candidate_char  <= '0;
            dcmp_addr       <= '0;
            dcmp_we         <= 1'b0;
            dcmp_wdata      <= '0;
        end else begin
            // Defaults (pulsed signals de-assert unless re-stated)
            done            <= 1'b0;
            candidate_valid <= 1'b0;
            candidate_last  <= 1'b0;
            dcmp_we         <= 1'b0;

            unique case (current_state)
                IDLE: begin
                    pos_cnt        <= '0;
                    cand_cnt       <= '0;
                    candidates_out <= '0;
                    load_cnt       <= '0;
                    error          <= (load_dcmp && start);  // conflicting commands
                end

                // ------------------------------------------------------
                // LOAD_DCPM: capture one BRAM row per cycle.
                // ------------------------------------------------------
                LOAD_DCPM: begin
                    dcmp_addr <= {{(BRAM_ADDR_WIDTH-POS_W){1'b0}}, load_cnt[POS_W-1:0]};
                    dcmp_rows[load_cnt[POS_W-1:0]] <= dcmp_rdata;
                    load_cnt <= load_cnt + 1'b1;
                end

                // ------------------------------------------------------
                // GENERATE: stream one char per cycle.
                // ------------------------------------------------------
                GENERATE: begin
                    candidate_char  <= dcmp_rows[pos_cnt][ 9'({cand_cnt[2:0] + pos_cnt[2:0], 3'b000}) +: 8 ];
                    candidate_valid <= 1'b1;
                    candidate_last  <= (pos_cnt == POS_W'(CANDIDATE_LEN - 1));
                    seq_len         <= 16'(pos_cnt);

                    if (pos_cnt == POS_W'(CANDIDATE_LEN - 1)) begin
                        pos_cnt        <= '0;
                        cand_cnt       <= cand_cnt + 1'b1;
                        candidates_out <= candidates_out + 1'b1;
                    end else begin
                        pos_cnt <= pos_cnt + 1'b1;
                    end
                end

                DONE_STATE: begin
                    done <= 1'b1;
                end

                default: ;
            endcase
        end
    end

endmodule

