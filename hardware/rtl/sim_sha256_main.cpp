// Verilator C++ testbench: validates sha256_core against NIST FIPS 180-4 vectors.

#include <verilated.h>
#include "Vsha256_core.h"
#include <cstdio>
#include <cstdint>
#include <cstring>

// ------------------------------------------------------------------
// NIST expected digests
// ------------------------------------------------------------------

// SHA-256("abc")
static const uint8_t EXPECTED_ABC[32] = {
    0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,
    0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad
};

// SHA-256("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq")
static const uint8_t EXPECTED_LONG[32] = {
    0x24,0x8d,0x6a,0x61,0xd2,0x06,0x38,0xb8,0xe5,0xc0,0x26,0x93,0x0c,0x3e,0x60,0x39,
    0xa3,0x3c,0xe4,0x59,0x64,0xff,0x21,0x67,0xf6,0xec,0xdd,0x41,0x9d,0xb0,0x6c,0x01
};

// ------------------------------------------------------------------
// Testbench driver
// ------------------------------------------------------------------

static vluint64_t main_time = 0;

// Required by Verilator's verilated.o on some builds
double sc_time_stamp() {
    return static_cast<double>(main_time);
}

static void tick(Vsha256_core* dut) {
    dut->clk = 1;
    dut->eval();
    main_time++;
    dut->clk = 0;
    dut->eval();
    main_time++;
}

// Load a 64-byte big-endian block into the 512-bit data_in port.
// Verilator exposes a 512-bit input as IData[16], word w = bits[32w+31:32w],
// and bits[511:480] correspond to block bytes 0..3.
static void load_block(Vsha256_core* dut, const uint8_t block[64]) {
    for (int w = 0; w < 16; w++) {
        int byte_hi = 63 - 4 * w;
        uint32_t word = ((uint32_t)block[byte_hi]     << 24)
                      | ((uint32_t)block[byte_hi - 1] << 16)
                      | ((uint32_t)block[byte_hi - 2] << 8)
                      |  (uint32_t)block[byte_hi - 3];
        dut->data_in[w] = word;
    }
}

static bool run_hash(Vsha256_core* dut, const uint8_t block[64],
                     const uint8_t expected[32], const char* name) {
    // Reset
    dut->rst_n = 0;
    dut->start = 0;
    tick(dut); tick(dut);
    dut->rst_n = 1;
    tick(dut);

    load_block(dut, block);

    // Start
    dut->start = 1;
    tick(dut);
    dut->start = 0;

    // Wait for hash_valid
    int cycles = 0;
    while (!dut->hash_valid && cycles < 1000) {
        tick(dut);
        cycles++;
    }
    if (!dut->hash_valid) {
        printf("[FAIL] %s: hash_valid never asserted after %d cycles\n", name, cycles);
        return false;
    }

    // Read digest: hash_out word w = bits[32w+31:32w]; digest byte 31-4w..28-4w
    uint8_t digest[32];
    for (int w = 0; w < 8; w++) {
        uint32_t word = dut->hash_out[w];
        digest[31 - 4 * w]     = (word >> 24) & 0xFF;
        digest[31 - 4 * w - 1] = (word >> 16) & 0xFF;
        digest[31 - 4 * w - 2] = (word >> 8) & 0xFF;
        digest[31 - 4 * w - 3] = word & 0xFF;
    }

    bool pass = memcmp(digest, expected, 32) == 0;
    printf("%s: %s (%d cycles)\n", name, pass ? "PASS" : "FAIL", cycles);
    if (!pass) {
        printf("  Expected: ");
        for (int i = 0; i < 32; i++) printf("%02x", expected[i]);
        printf("\n  Got:      ");
        for (int i = 0; i < 32; i++) printf("%02x", digest[i]);
        printf("\n");
    }
    return pass;
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vsha256_core* dut = new Vsha256_core;

    printf("=== SHA-256 Core NIST Validation ===\n\n");

    bool all_pass = true;

    // Test 1: "abc" (3 bytes -> pad 0x80, length = 24 bits = 0x18)
    {
        uint8_t block[64];
        memset(block, 0, 64);
        block[0] = 'a'; block[1] = 'b'; block[2] = 'c';
        block[3] = 0x80;
        block[63] = 0x18;
        all_pass &= run_hash(dut, block, EXPECTED_ABC, "Test 1 (\"abc\")");
    }

    // Test 2: 56-char message (length = 448 bits = 0x1C0)
    {
        const char* msg = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
        uint8_t block[64];
        memset(block, 0, 64);
        memcpy(block, msg, 56);
        block[56] = 0x80;
        block[62] = 0x01; block[63] = 0xC0;
        all_pass &= run_hash(dut, block, EXPECTED_LONG, "Test 2 (56-char)");
    }

    printf("\n%s\n", all_pass ? "ALL NIST TESTS PASSED!" : "SOME TESTS FAILED");
    delete dut;
    return all_pass ? 0 : 1;
}