import { expect, test } from "@playwright/test";

const PAGES: [string, RegExp][] = [
  ["/", /Forest intelligence overview/i],
  ["/map", /Layers/],
  ["/explorer", /Sentinel-2 observations/],
  ["/segmentation", /U-Net tree-cover segmentation/],
  ["/change", /Multi-date forest change/],
  ["/investigate", /Detected regions/],
  ["/datasets", /Data sources, labels and provenance/],
  ["/lab", /Train and compare U-Net experiments/],
  ["/evaluation", /Held-out geographic evaluation/],
  ["/history", /Everything Sylva has processed/],
  ["/docs", /Methodology, data and limitations/],
];

for (const [path, heading] of PAGES) {
  test(`page ${path} renders without errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(m.text()));
    await page.goto(path);
    await expect(page.getByText(heading).first()).toBeVisible();
    await page.waitForTimeout(1500);
    expect(errors, errors.join("\n")).toEqual([]);
  });
}

test("API health via the frontend proxy", async ({ request }) => {
  const r = await request.get("/api/health");
  expect(r.ok()).toBeTruthy();
  expect(await r.json()).toEqual({ status: "ok" });
});

test("map renders real Sentinel-2 tiles on the explorer", async ({ page }) => {
  const tiles: number[] = [];
  page.on("response", (r) => r.url().includes("/api/tiles/product/") && tiles.push(r.status()));
  await page.goto("/explorer");
  await expect(page.locator(".maplibregl-canvas").first()).toBeVisible();
  await page.waitForTimeout(4000);
  expect(tiles.length).toBeGreaterThan(0);
  expect(tiles.every((s) => s === 200)).toBeTruthy();
});

test("docs page lists methodology documents", async ({ page }) => {
  await page.goto("/docs");
  // Scope to the docs list: the sidebar also has a "Change detection" link.
  const docsNav = page.getByRole("navigation", { name: "Documentation" });
  await expect(docsNav.getByRole("link", { name: "Change detection" })).toBeVisible();
  await docsNav.getByRole("link", { name: "Limitations" }).click();
  await expect(page.locator("article h1", { hasText: "Limitations" })).toBeVisible();
});
