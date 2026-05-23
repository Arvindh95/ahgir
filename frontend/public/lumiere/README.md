# Lumière image slots

Drop real photos here with the exact filenames below. If a slot is missing, the
component automatically falls back to a dark cinematic gradient — so the
site never shows a broken-image icon.

## Slots

| File       | Used on              | Aspect | Notes                                                |
| ---------- | -------------------- | ------ | ---------------------------------------------------- |
| `hero.jpg` | `/` cinematic hero   | wide / any | Full-bleed backdrop behind the headline. Will be darkened by an overlay; original tones should be relatively dark or warm for best read |

## Constraints

- **No GPS / EXIF.** Strip metadata before committing — this folder is served publicly.
- **Compressed.** Aim for under 400KB. Larger is wasted bandwidth on a cover image.
- **Permission cleared.** Anyone visible should have agreed to appear on the landing page.

## Adding more slots

`<Scene src="/lumiere/your-file.jpg" />` and `<Photo src="/lumiere/your-file.jpg" />`
both gracefully fall back to gradient placeholders if the file is missing.
