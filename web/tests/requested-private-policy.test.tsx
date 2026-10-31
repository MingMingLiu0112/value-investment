import React from "react";
import { expect, it, vi } from "vitest";
import type { ValuePolicyTransport } from "../src/services/valuePolicy";
const { renderToStaticMarkup } = require("react-dom/server");
const mounted = vi.hoisted(() => vi.fn());
vi.mock("../src/components/PrivateValueDecision", () => ({
  PrivateValueDecision: (props: unknown) => {
    mounted(props);
    return <p>private policy mounted</p>;
  },
}));
import { RequestedPrivatePolicy } from "../src/components/ValuePolicyReview";

it("keeps the private reader unmounted until authorization is explicitly requested", () => {
  mounted.mockClear();
  const transport = {
    status: vi.fn(),
    preview: vi.fn(),
    confirm: vi.fn(),
  } as unknown as ValuePolicyTransport;
  const props = { symbol: "600887", transport, revision: 3 };
  let requested = false;
  // SSR cannot execute effects: verify the reader's mount boundary using the
  // real button callback and controlled hook state, without a DOM dependency.
  const dispatcher = (React as any)
    .__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher;
  const renderGate = () => {
    const previous = dispatcher.current;
    dispatcher.current = {
      useState: () => [
        requested,
        (value: boolean) => {
          requested = value;
        },
      ],
    };
    try {
      return RequestedPrivatePolicy(props);
    } finally {
      dispatcher.current = previous;
    }
  };
  const initial = renderGate();
  expect(renderToStaticMarkup(initial)).toContain(
    "读取本人价格政策（需要授权）",
  );
  expect(renderToStaticMarkup(renderGate())).not.toContain(
    "private policy mounted",
  );
  expect(mounted).not.toHaveBeenCalled();
  expect(transport.status).not.toHaveBeenCalled();
  initial.props.onClick();
  expect(requested).toBe(true);
  const activated = renderToStaticMarkup(renderGate());
  expect(activated).toContain("private policy mounted");
  expect(activated).not.toContain("读取本人价格政策（需要授权）");
  expect(mounted).toHaveBeenCalledTimes(1);
  expect(mounted).toHaveBeenCalledWith(props);
  expect(transport.preview).not.toHaveBeenCalled();
  expect(transport.confirm).not.toHaveBeenCalled();
});
