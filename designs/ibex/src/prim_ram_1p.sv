// sky130 implementation of lowRISC prim_ram_1p using OpenRAM SRAM macros.
//
// Any Width x Depth is built by tiling sky130_sram_1kbyte_1rw1r_32x256_8
// (32 bits x 256 words, byte write mask): ceil(Width/32) columns by
// ceil(Depth/256) rows. Unused bits/words are simply wasted; this favors
// simplicity over area. Only port 0 (read/write) is used; port 1 (read-only)
// is disabled.
//
// Write mask: the macro masks per byte, so a byte is written when all of its
// wmask_i bits are set (ibex always writes full words).

`include "prim_assert.sv"

module prim_ram_1p import prim_ram_1p_pkg::*; #(
  parameter  int Width           = 32,
  parameter  int Depth           = 128,
  parameter  int DataBitsPerMask = 1,   // unused: macro masks per byte
  parameter      MemInitFile     = "",  // unused: SRAM macros cannot be initialized

  localparam int Aw              = $clog2(Depth)
) (
  input  logic             clk_i,
  input  logic             rst_ni,

  input  logic             req_i,
  input  logic             write_i,
  input  logic [Aw-1:0]    addr_i,
  input  logic [Width-1:0] wdata_i,
  input  logic [Width-1:0] wmask_i,
  output logic [Width-1:0] rdata_o,  // returned one cycle after req_i
  input  ram_1p_cfg_req_t  cfg_i,
  output ram_1p_cfg_rsp_t  cfg_o
);

  localparam int MacroWidth = 32;
  localparam int MacroDepth = 256;
  localparam int MacroAw    = 8;

  localparam int Cols  = (Width + MacroWidth - 1) / MacroWidth;
  localparam int Rows  = (Depth + MacroDepth - 1) / MacroDepth;
  localparam int RowAw = (Rows > 1) ? $clog2(Rows) : 1;

  localparam int PadWidth = Cols * MacroWidth;

  logic unused_signals;
  assign unused_signals = ^{cfg_i};
  assign cfg_o          = RAM_1P_CFG_RSP_DEFAULT;

  // Zero-extend to whole macros.
  logic [PadWidth-1:0] wdata, wmask;
  assign wdata = PadWidth'(wdata_i);
  assign wmask = PadWidth'(wmask_i);

  // Split the address into macro word address and row select.
  logic [MacroAw-1:0] macro_addr;
  logic [RowAw-1:0]   row, row_q;
  if (Rows > 1) begin : gen_row_addr
    assign macro_addr = addr_i[MacroAw-1:0];
    assign row        = addr_i[Aw-1:MacroAw];
  end else begin : gen_no_row_addr
    assign macro_addr = MacroAw'(addr_i);
    assign row        = '0;
  end

  // Row of the pending read, to select the output one cycle later.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      row_q <= '0;
    end else if (req_i && !write_i) begin
      row_q <= row;
    end
  end

  logic [PadWidth-1:0] row_rdata [Rows];

  for (genvar r = 0; r < Rows; r++) begin : gen_row
    for (genvar c = 0; c < Cols; c++) begin : gen_col
      logic [3:0] byte_wmask;
      for (genvar b = 0; b < 4; b++) begin : gen_byte
        assign byte_wmask[b] = &wmask[c*MacroWidth + b*8 +: 8];
      end

      sky130_sram_1kbyte_1rw1r_32x256_8 u_sram (
        // Port 0: read/write (active-low chip select / write enable)
        .clk0   (clk_i),
        .csb0   (~(req_i && (row == RowAw'(r)))),
        .web0   (~write_i),
        .wmask0 (byte_wmask),
        .addr0  (macro_addr),
        .din0   (wdata[c*MacroWidth +: MacroWidth]),
        .dout0  (row_rdata[r][c*MacroWidth +: MacroWidth]),
        // Port 1: read-only, unused
        .clk1   (clk_i),
        .csb1   (1'b1),
        .addr1  ('0),
        .dout1  ()
      );
    end
  end

  assign rdata_o = row_rdata[row_q][Width-1:0];

endmodule
