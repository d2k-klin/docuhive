import { expect, test } from "@playwright/test";

test("inputs, date fields and buttons share the control height and baseline", async ({
  page,
}) => {
  await page.goto("/dev/ui");
  const controls = page.getByTestId("control-row").locator("input, button");
  const boxes = await controls.evaluateAll((elements) =>
    elements.map((element) => {
      const { height, y } = element.getBoundingClientRect();
      return { height, y };
    }),
  );
  expect(boxes.length).toBe(4);
  for (const box of boxes) {
    expect(Math.abs(box.height - 36)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(box.y - boxes[0].y)).toBeLessThanOrEqual(0.5);
  }
});
