import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Keep in sync with the --text-* font-size tokens in styles.css @theme.
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ["caption", "meta", "body", "title", "heading", "display"] } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
