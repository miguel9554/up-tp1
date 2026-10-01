// sky130 implementation of lowRISC prim_clock_gating.
// Replaces the generic latch+AND model with the library's integrated
// clock-gating cell, so STA sees a proper ICG instead of a latch.
module prim_clock_gating #(
  parameter bit NoFpgaGate    = 1'b0,  // unused (FPGA only)
  parameter bit FpgaBufGlobal = 1'b1   // unused (FPGA only)
) (
  input  logic clk_i,
  input  logic en_i,
  input  logic test_en_i,
  output logic clk_o
);

  // ICG cell of the selected std cell library. LibreLane defines
  // SCL_<STD_CELL_LIBRARY> (set in variants/*.json) for lint and synthesis.
`ifdef SCL_sky130_fd_sc_hs
  sky130_fd_sc_hs__dlclkp_1 u_icg (
`else
  sky130_fd_sc_hd__dlclkp_1 u_icg (
`endif
    .CLK  (clk_i),
    .GATE (en_i | test_en_i),
    .GCLK (clk_o)
  );

endmodule
