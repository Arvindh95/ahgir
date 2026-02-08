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

// Global navigation script that monkey-patches History API for client-side routing
const NAV_SCRIPT = `<script>!function(){var t={'/':'PicUr','/admin/login':'Login - PicUr','/admin/register':'Register - PicUr','/admin/forgot-password':'Forgot Password - PicUr','/admin/verify':'Verify Email - PicUr','/admin/reset-password':'Reset Password - PicUr','/admin/superadmin':'Super Admin - PicUr','/admin/events':'Events - PicUr','/admin/events/create':'Create Event - PicUr'};var p=[[/^\\/admin\\/events\\/[^/]+\\/photos$/,'Photos - PicUr'],[/^\\/admin\\/events\\/[^/]+$/,'Event Details - PicUr'],[/^\\/e\\/[^/]+\\/gallery$/,'Gallery - PicUr'],[/^\\/e\\/[^/]+\\/results$/,'Results - PicUr'],[/^\\/e\\/[^/]+\\/scan$/,'Scan - PicUr'],[/^\\/e\\/[^/]+$/,'Event - PicUr']];function g(a){a=a.split('?')[0].split('#')[0];if(a.length>1&&a.endsWith('/'))a=a.slice(0,-1);if(t[a])return t[a];for(var i=0;i<p.length;i++){if(p[i][0].test(a))return p[i][1]}return'PicUr'}function u(){document.title=g(window.location.pathname)}var op=history.pushState;var or=history.replaceState;history.pushState=function(){op.apply(this,arguments);setTimeout(u,0)};history.replaceState=function(){or.apply(this,arguments);setTimeout(u,0)};window.addEventListener('popstate',function(){setTimeout(u,0)});u();setTimeout(u,50);setTimeout(u,200);setTimeout(u,500)}()</script>`

const pagesDir = path.join(__dirname, '..', '.next', 'server', 'pages')

function injectTitle(filePath, title) {
  if (!fs.existsSync(filePath)) return
  let html = fs.readFileSync(filePath, 'utf-8')
  const escapedTitle = title.replace(/'/g, "\\'")
  const titleScript = `<script>!function(){var t='${escapedTitle}';document.title=t;[0,50,150,300,600,1200].forEach(function(d){setTimeout(function(){document.title=t},d)})}()</script>`
  // Remove any existing title tag first
  html = html.replace(/<title>[^<]*<\/title>/, '')
  html = html.replace('<head>', `<head><title>${title}</title>${titleScript}`)
  // Inject navigation script before </body> if not already present
  if (!html.includes('history.pushState=function')) {
    html = html.replace('</body>', `${NAV_SCRIPT}</body>`)
  }
  fs.writeFileSync(filePath, html)
  console.log(`Injected title "${title}" into ${filePath}`)
}

for (const [file, title] of Object.entries(PAGE_TITLES)) {
  injectTitle(path.join(pagesDir, file), title)
}

console.log('Title injection complete.')
