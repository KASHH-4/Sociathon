import { createFileRoute } from "@tanstack/react-router";
import { TransitApp } from "@/components/transit-app";
export const Route = createFileRoute("/recovery")({
  head: () => ({
    meta: [
      { title: "Journey Recovery | TransitHear" },
      {
        name: "description",
        content:
          "TransitHear journey recovery interactive prototype for Deaf and Hard-of-Hearing commuters, with clear visual transit updates and accessible journey tools.",
      },
      { property: "og:title", content: "Journey Recovery | TransitHear" },
      {
        property: "og:description",
        content:
          "TransitHear journey recovery interactive prototype for Deaf and Hard-of-Hearing commuters, with clear visual transit updates and accessible journey tools.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => <TransitApp view="recovery" />,
});
