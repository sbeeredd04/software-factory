import assert from "node:assert/strict";
import test from "node:test";
import { greetingFor, submitGreeting } from "../dist/app.js";

test("normal name and blank name", () => {
  assert.equal(greetingFor(" Ada "), "Hello, Ada.");
  assert.throws(() => greetingFor("   "), /Enter a name/);
});

test("markup-shaped text is assigned as text content", () => {
  const view = { input: { value: "<b>Ada</b>" }, result: { textContent: null } };
  submitGreeting(view);
  assert.equal(view.result.textContent, "Hello, <b>Ada</b>.");
  view.input.value = "";
  submitGreeting(view);
  assert.equal(view.result.textContent, "Enter a name.");
});
