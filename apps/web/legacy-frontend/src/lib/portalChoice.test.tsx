/**
 * The remembered portal (B26 T6b-5 §6.2): a portal id only, read back only if
 * the server granted it, and every storage access silent on failure.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PORTAL_CHOICE_KEY,
  forgetRememberedPortal,
  readRememberedPortal,
  rememberPortal,
} from "./portalChoice";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("portalChoice", () => {
  it("reads back a remembered portal the server granted", () => {
    rememberPortal("speaker");
    expect(window.localStorage.getItem(PORTAL_CHOICE_KEY)).toBe("speaker");
    expect(readRememberedPortal(["volunteer", "speaker"])).toBe("speaker");
  });

  it("an ungranted or unknown value reads as null", () => {
    rememberPortal("speaker");
    expect(readRememberedPortal(["volunteer"])).toBeNull();
    window.localStorage.setItem(PORTAL_CHOICE_KEY, "coordinator-portal-admin");
    expect(readRememberedPortal(["volunteer", "speaker"])).toBeNull();
  });

  it("nothing stored reads as null", () => {
    expect(readRememberedPortal(["volunteer", "speaker"])).toBeNull();
  });

  it("forget removes the choice", () => {
    rememberPortal("volunteer");
    forgetRememberedPortal();
    expect(window.localStorage.getItem(PORTAL_CHOICE_KEY)).toBeNull();
  });

  it("a throwing getItem reads as null", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readRememberedPortal(["volunteer", "speaker"])).toBeNull();
  });

  it("a throwing setItem is silent", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => rememberPortal("speaker")).not.toThrow();
  });

  it("a throwing removeItem is silent", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => forgetRememberedPortal()).not.toThrow();
  });

  it("a throwing localStorage accessor is silent everywhere", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readRememberedPortal(["speaker"])).toBeNull();
    expect(() => rememberPortal("speaker")).not.toThrow();
    expect(() => forgetRememberedPortal()).not.toThrow();
  });
});
