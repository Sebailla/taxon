/** RED contract tests for the dynamic ``Breadcrumb``.

The breadcrumb is the cascade's "click to drill in" surface: each
segment is a ``<button type="button">`` that calls ``onSelect(trail.slice(0, idx+1))``
when clicked. The deepest segment carries ``aria-current="page"``
so screen readers announce it as the current step. When
``onSelect`` is omitted the click is a no-op (the ``<nav>`` must
still render).

These tests pin the contract for tasks 3.1–3.3 in
``openspec/changes/breadcrumb-dinamico/tasks.md``.
*/

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Breadcrumb } from "../src/components/Breadcrumb";

describe("Breadcrumb — dynamic segments", () => {
  it("calls onSelect with the trail up to and including the clicked segment", async () => {
    // 3.1 — click on Chordata (second segment) calls onSelect(["Animalia", "Chordata"]).
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <Breadcrumb trail={["Animalia", "Chordata"]} onSelect={onSelect} />,
    );

    const chordata = screen.getByRole("button", { name: "Chordata" });
    await user.click(chordata);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(["Animalia", "Chordata"]);
  });

  it("calls onSelect with a single-segment trail when the first segment is clicked", async () => {
    // 3.2 — click on Animalia (first segment) calls onSelect(["Animalia"]);
    // the deepest segment (Chordata) carries aria-current="page".
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <Breadcrumb trail={["Animalia", "Chordata"]} onSelect={onSelect} />,
    );

    const animalia = screen.getByRole("button", { name: "Animalia" });
    await user.click(animalia);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(["Animalia"]);

    // The deepest segment carries the aria-current marker.
    const chordata = screen.getByRole("button", { name: "Chordata" });
    expect(chordata.getAttribute("aria-current")).toBe("page");
  });

  it("renders <nav> and does not throw when onSelect is omitted", async () => {
    // 3.3 — the component must still render when no handler is supplied;
    // clicking a segment is a no-op, not an exception.
    const user = userEvent.setup();
    render(<Breadcrumb trail={["Animalia", "Chordata"]} />);

    const nav = screen.getByRole("navigation", {
      name: /breadcrumb/i,
    });
    expect(nav).toBeInTheDocument();

    const chordata = screen.getByRole("button", { name: "Chordata" });
    await user.click(chordata); // must not throw
  });

  it("renders every segment as a button, including the deepest", () => {
    // Contract: ALL segments are buttons (so screen readers can find
    // them by role). The deepest still carries aria-current="page".
    render(
      <Breadcrumb
        trail={["Animalia", "Chordata", "Mammalia"]}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Animalia" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chordata" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mammalia" })).toBeInTheDocument();

    const deepest = screen.getByRole("button", { name: "Mammalia" });
    expect(deepest.getAttribute("aria-current")).toBe("page");
  });
});