import { useRouter } from 'next/router'
import { useEffect } from 'react'

const PAGE_TITLES: Record<string, string> = {
  '/admin/login': 'Login - PicUr',
  '/admin/register': 'Register - PicUr',
  '/admin/forgot-password': 'Forgot Password - PicUr',
  '/admin/verify': 'Verify Email - PicUr',
  '/admin/reset-password': 'Reset Password - PicUr',
  '/admin/superadmin': 'Super Admin - PicUr',
  '/admin/events': 'Events - PicUr',
  '/admin/events/create': 'Create Event - PicUr',
  '/admin/events/[id]': 'Event Details - PicUr',
  '/admin/events/[id]/photos': 'Photos - PicUr',
  '/e/[slug]': 'Event - PicUr',
  '/e/[slug]/gallery': 'Gallery - PicUr',
  '/e/[slug]/results': 'Results - PicUr',
  '/e/[slug]/scan': 'Scan - PicUr',
}

export default function PageTitle() {
  const router = useRouter()

  useEffect(() => {
    document.title = PAGE_TITLES[router.pathname] || 'PicUr'
  }, [router.pathname])

  return null
}
