import { createFileRoute } from '@tanstack/react-router';
import { TransitApp } from '@/components/transit-app';
export const Route = createFileRoute('/map')({
 head: () => ({ meta: [
 { title: 'Accessibility Map | TransitHear' },
 { name: 'description', content: 'TransitHear accessibility map interactive prototype for Deaf and Hard-of-Hearing commuters, with clear visual transit updates and accessible journey tools.' },
 { property: 'og:title', content: 'Accessibility Map | TransitHear' },
 { property: 'og:description', content: 'TransitHear accessibility map interactive prototype for Deaf and Hard-of-Hearing commuters, with clear visual transit updates and accessible journey tools.' },
 { property: 'og:type', content: 'website' },
 { name: 'twitter:card', content: 'summary_large_image' },
 ] }),
 component: () => <TransitApp view="map" />,
});
