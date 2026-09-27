import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import suppliedLogo from "../../../docs/design/LOGO.jpeg";
import { AltoLogo } from "./alto-ui";

afterEach(cleanup);

describe("supplied ALTO branding", () => {
  it.each([false, true])("uses the original image without redrawing it (compact=%s)", (compact) => {
    render(<AltoLogo compact={compact} />);
    const logo = screen.getByRole("img", { name: "ALTO" });
    expect(logo.querySelector("image")).toHaveAttribute("href", suppliedLogo);
    expect(logo.querySelector("svg")).toHaveAttribute("viewBox", "70 500 1110 290");
    expect(logo.querySelector("path")).toBeNull();
    expect(logo.classList.contains("compact")).toBe(compact);
  });
});
