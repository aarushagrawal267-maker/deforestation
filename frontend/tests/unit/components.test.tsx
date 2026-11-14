import { fireEvent, render, screen } from "@testing-library/react";
import { ConfusionMatrix } from "../../src/components/charts";
import { LegendRow, ProbabilityRamp } from "../../src/components/map/Legend";
import { SpectralStrip } from "../../src/components/SpectralStrip";
import { Stat, Tabs } from "../../src/components/ui";

describe("components", () => {
  it("renders a stat with unit", () => {
    render(<Stat label="Potential forest loss" value="12.5" unit="ha" tone="loss" />);
    expect(screen.getByText("Potential forest loss")).toBeInTheDocument();
    expect(screen.getByText("ha")).toBeInTheDocument();
  });

  it("spectral strip toggles bands and marks 20 m bands", () => {
    const toggled: string[] = [];
    render(<SpectralStrip selected={["B4"]} onToggle={(b) => toggled.push(b)} multi />);
    fireEvent.click(screen.getByTitle(/B11 · SWIR 1/));
    expect(toggled).toEqual(["B11"]);
    expect(screen.getByTitle(/B5 · Red edge 1 · 705 nm · native 20 m/)).toBeInTheDocument();
  });

  it("confusion matrix is row-normalised", () => {
    render(<ConfusionMatrix cm={[[90, 10], [25, 75]]} names={["A", "B"]} />);
    expect(screen.getByText("90.0%")).toBeInTheDocument();
    expect(screen.getByText("25.0%")).toBeInTheDocument();
  });

  it("tabs switch value", () => {
    let v = "a";
    render(<Tabs value="a" onChange={(x) => (v = x)} items={[{ value: "a", label: "A" }, { value: "b", label: "B" }]} />);
    fireEvent.click(screen.getByText("B"));
    expect(v).toBe("b");
  });

  it("legend components render labels", () => {
    render(
      <>
        <LegendRow swatch="bg-loss" label="Potential forest loss" value="3 ha" />
        <ProbabilityRamp />
      </>,
    );
    expect(screen.getByText("Potential forest loss")).toBeInTheDocument();
    expect(screen.getByText("P(tree cover)")).toBeInTheDocument();
  });
});
