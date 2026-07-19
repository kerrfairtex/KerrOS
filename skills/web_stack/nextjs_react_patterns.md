# Next.js + React Patterns
App Router (Next.js 13+) uses file-based routing under app/: page.tsx for routes, layout.tsx for shared shells, route.ts for API endpoints.
Server Components are default — fetch data directly in the component, no useEffect needed. Mark client-interactive components explicitly with "use client" at the top of the file.
Common structure: app/(routes)/page.tsx for pages, components/ for shared UI, lib/ for utilities and API clients, app/api/ for backend routes.
State management: prefer React's built-in useState/useContext for simple state; reach for a library (Zustand, Redux) only when state is genuinely complex/shared across many unrelated components.
