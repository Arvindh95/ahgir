# Frontend Security Audit Exceptions

`npm audit --omit=dev` reports advisories against `next@14.2.35` and the
`face-api.js → @tensorflow/tfjs-core → node-fetch` chain. This document
records why each is not currently applicable to PicUr's deployed
configuration and what would change that.

The `next-14` dist-tag is pinned at `14.2.35` — the 14.x line is EOL for
security patches. Every fix for the advisories below is on the 15.x
backport line or later. We accept the audit warnings because none of the
vulnerable code paths are reachable in PicUr's actual configuration.

## Next.js advisories

| Advisory | Applies | Reason |
| --- | --- | --- |
| GHSA-9g9p-9gw9-jx7f (Image Optimizer DoS via remotePatterns) | No | `next.config.js` sets `images.unoptimized: true`. The Next image optimization API is disabled at runtime. |
| GHSA-3x4c-7xq6-9pq8 (next/image disk cache exhaustion) | No | Same — optimizer disabled. |
| GHSA-h64f-5h5j-jqjh (Image Optimization API DoS) | No | Same — optimizer disabled. |
| GHSA-h25m-26qc-wcjf (HTTP request deserialization via RSC) | No | App uses Pages Router. No React Server Components. |
| GHSA-q4gf-8mx6-v5v3 (RSC DoS) | No | No RSC. |
| GHSA-8h8q-6873-q5fj (RSC DoS) | No | No RSC. |
| GHSA-vfv6-92ff-j949 (RSC cache poisoning) | No | No RSC. |
| GHSA-ffhc-5mcf-pf4q (App Router CSP nonce XSS) | No | Pages Router only; no App Router routes. |
| GHSA-gx5p-jg67-6x7h (beforeInteractive Script XSS with untrusted input) | No | App has no `<Script strategy="beforeInteractive">` usage. |
| GHSA-ggv3-7p47-pfv8 (HTTP request smuggling in rewrites) | No | `next.config.js` defines no `rewrites`. |

If any of those preconditions change (enabling `next/image` optimization,
migrating to the App Router, adding rewrites, or introducing
`beforeInteractive` scripts with untrusted input), the corresponding row
becomes applicable and the upgrade to `next@15.5.x` or newer must happen
before that change ships.

## face-api.js → tfjs-core → node-fetch

`face-api.js@0.22.2` pulls `@tensorflow/tfjs-core` versions 1.1.0–2.4.0,
which in turn depends on a vulnerable `node-fetch`. The reported npm
advisory only applies to server-side fetches. In PicUr, face-api.js is
imported dynamically and runs in the browser to draw face landmarks
during the guest scan flow. The `tfjs-core` Node code path is never
executed at runtime, only bundled. The build host is not exposed to
untrusted input via this dependency chain.

The maintainer-recommended fix is to pin `face-api.js` back to 0.20.0,
which predates the affected TensorFlow versions but loses features we
rely on. The accepted alternative would be to switch to a maintained
fork (e.g. `@vladmandic/face-api`) and remove the original package. We
already load the recognition models from `@vladmandic/face-api`'s CDN
distribution at runtime, but the npm dependency still points at the
upstream package. A future cleanup is to drop the npm dependency
entirely and rely only on the browser-loaded CDN bundle.

## When to revisit

- A new advisory appears that does match our configuration (most likely:
  re-enabling `next/image` optimization, or any move toward the App
  Router / RSC).
- We migrate to Next 15.x.
- We replace `face-api.js` with `@vladmandic/face-api` in `package.json`.

Last reviewed: 2026-05-14.
