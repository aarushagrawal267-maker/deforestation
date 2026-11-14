import { fmtCoord, fmtHa, fmtPct, signed } from "../../src/lib/format";

describe("format helpers", () => {
  it("formats hectares and switches to km² for large areas", () => {
    expect(fmtHa(0.53)).toBe("0.53 ha");
    expect(fmtHa(1500)).toMatch(/15.*km²/);
    expect(fmtHa(null)).toBe("—");
  });
  it("formats percentages and signed values", () => {
    expect(fmtPct(0.1234)).toBe("12.3%");
    expect(signed(0.25, 2)).toBe("+0.25");
    expect(signed(-0.1, 2)).toBe("-0.10");
  });
  it("formats coordinates with hemispheres", () => {
    expect(fmtCoord(-55.38, -7.05)).toBe("7.05000°S  55.38000°W");
  });
});
