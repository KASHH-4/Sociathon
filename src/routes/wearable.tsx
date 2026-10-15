import { createFileRoute } from "@tanstack/react-router";
import { TransitApp } from "@/components/transit-app";
export const Route = createFileRoute("/wearable")({
  head: () => ({
    meta: [
      { title: "Haptics & Wearable | TransitHear" },
      {
        name: "description",
        content:
          "TransitHear haptics & wearable interactive prototype for Deaf and Hard-of-Hearing commuters, with clear visual transit updates and accessible journey tools.",
      },
      { property: "og:title", content: "Haptics & Wearable | TransitHear" },
      {
        property: "og:description",
        content:
          "TransitHear haptics & wearable interactive prototype for Deaf and Hard-of-Hearing commuters, with clear visual transit updates and accessible journey tools.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => <TransitApp view="wearable" />,
});
