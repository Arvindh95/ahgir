# Atelier image slots

Drop real photos here with the exact filenames below. If a slot is missing, the
component automatically falls back to an abstract gradient placeholder — so the
site never shows a broken-image icon.

## Slots

| File          | Used on   | Aspect | Suggested min size | Notes                                                     |
| ------------- | --------- | ------ | ------------------ | --------------------------------------------------------- |
| `hero-1.jpg`  | `/` hero  | 3:4    | 800 × 1067         | Large editorial portrait, sits behind phone on the right  |
| `hero-2.jpg`  | `/` hero  | 3:4    | 500 × 667          | Small accent photo, rotated -6°                           |
| `step-01.jpg` | `/` Method | 4:5   | 800 × 1000         | Step 01 — "You upload"                                    |
| `step-02.jpg` | `/` Method | 4:5   | 800 × 1000         | Step 02 — "Guests scan"                                   |
| `step-03.jpg` | `/` Method | 4:5   | 800 × 1000         | Step 03 — "Photos arrive"                                 |

## Constraints

- **No GPS / EXIF.** PicUr strips EXIF from uploaded event photos, but these
  marketing images sit in the public folder — anything you drop here ships as-is.
  Strip metadata before committing.
- **Compressed.** Aim for under 250KB each. The Photo component renders
  `object-fit: cover` so cropping is forgiving; large bytes are not.
- **Permission cleared.** Anyone visible in these images should have agreed to
  appear on the landing page. The site is public.

## Replacing a slot

1. Save the new JPEG with the exact filename above (case-sensitive).
2. Drop it in this folder.
3. Commit. The component picks it up automatically — no code changes.

## Adding a new slot

If you want a new image slot somewhere in the redesign, the components support it
out of the box: pass `src="/atelier/your-name.jpg"` to `<Photo />` or `<Scene />`.
If the file is missing the gradient placeholder renders instead.
