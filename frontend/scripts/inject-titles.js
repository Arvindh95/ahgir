const fs = require('fs')
const path = require('path')

const PAGE_TITLES = {
  'admin/login.html': 'Login - PicUr',
  'admin/register.html': 'Register - PicUr',
  'admin/forgot-password.html': 'Forgot Password - PicUr',
  'admin/verify.html': 'Verify Email - PicUr',
  'admin/reset-password.html': 'Reset Password - PicUr',
  'admin/superadmin.html': 'Super Admin - PicUr',
  'admin/events.html': 'Events - PicUr',
  'admin/events/create.html': 'Create Event - PicUr',
  'admin/events/[id].html': 'Event Details - PicUr',
  'admin/events/[id]/photos.html': 'Photos - PicUr',
  'e/[slug].html': 'Event - PicUr',
  'e/[slug]/gallery.html': 'Gallery - PicUr',
  'e/[slug]/results.html': 'Results - PicUr',
  'e/[slug]/scan.html': 'Scan - PicUr',
  'index.html': 'PicUr',
  '404.html': 'PicUr',
}

const pagesDir = path.join(__dirname, '..', '.next', 'server', 'pages')

function injectTitle(filePath, title) {
  if (!fs.existsSync(filePath)) return
  let html = fs.readFileSync(filePath, 'utf-8')
  const escapedTitle = title.replace(/'/g, "\\'")
  const titleScript = `<script>!function(){var t='${escapedTitle}';document.title=t;[0,50,150,300,600,1200].forEach(function(d){setTimeout(function(){document.title=t},d)})}()</script>`
  // Remove any existing title tag first
  html = html.replace(/<title>[^<]*<\/title>/, '')
  html = html.replace('<head>', `<head><title>${title}</title>${titleScript}`)
  fs.writeFileSync(filePath, html)
  console.log(`Injected title "${title}" into ${filePath}`)
}

for (const [file, title] of Object.entries(PAGE_TITLES)) {
  injectTitle(path.join(pagesDir, file), title)
}

console.log('Title injection complete.')
