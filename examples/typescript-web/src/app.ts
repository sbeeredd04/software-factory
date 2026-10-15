export function greetingFor(value: string): string {
  const name = value.trim();
  if (name.length === 0) throw new Error("Enter a name.");
  if (name.length > 80) throw new Error("Keep the name under 81 characters.");
  return `Hello, ${name}.`;
}

export interface GreetingView {
  input: { value: string };
  result: { textContent: string | null };
}

export function submitGreeting(view: GreetingView): void {
  try {
    view.result.textContent = greetingFor(view.input.value);
  } catch (error) {
    view.result.textContent = error instanceof Error ? error.message : "Unable to greet.";
  }
}

if (typeof document !== "undefined") {
  const form = document.querySelector<HTMLFormElement>("#greeting-form");
  const input = document.querySelector<HTMLInputElement>("#name");
  const result = document.querySelector<HTMLElement>("#result");
  if (form && input && result) {
    form.addEventListener("submit", (event: SubmitEvent) => {
      event.preventDefault();
      submitGreeting({ input, result });
    });
  }
}
