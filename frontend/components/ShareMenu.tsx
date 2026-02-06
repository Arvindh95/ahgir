import { useRef, useEffect, useState } from 'react'
import { Link, Share2 } from 'lucide-react'
import { useToast } from '@/hooks/useToast'

interface ShareMenuProps {
  imageId: string
  eventName: string
  onClose: () => void
}

export function ShareMenu({ imageId, eventName, onClose }: ShareMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [onClose])

  const getShareUrl = () => {
    const eventId = localStorage.getItem('event_id')
    return `${window.location.origin}/share/${eventId}/${imageId}`
  }

  const copyLink = async () => {
    await navigator.clipboard.writeText(getShareUrl())
    toast('Link copied!', 'success')
    onClose()
  }

  const shareToWhatsApp = () => {
    const url = getShareUrl()
    window.open(`https://wa.me/?text=${encodeURIComponent(`Check out this photo from ${eventName}! ${url}`)}`, '_blank')
    onClose()
  }

  const shareToFacebook = () => {
    const url = getShareUrl()
    window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`, '_blank')
    onClose()
  }

  const shareToX = () => {
    const url = getShareUrl()
    window.open(`https://twitter.com/intent/tweet?url=${encodeURIComponent(url)}&text=${encodeURIComponent(`Check out this photo from ${eventName}!`)}`, '_blank')
    onClose()
  }

  return (
    <div ref={menuRef} className="absolute bottom-full mb-2 right-0 glass-card rounded-xl p-2 min-w-[180px] z-30 border border-white/10 shadow-xl">
      <button onClick={copyLink} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <Link className="w-4 h-4" /> Copy Link
      </button>
      <button onClick={shareToWhatsApp} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <span className="w-4 h-4 text-center">W</span> WhatsApp
      </button>
      <button onClick={shareToFacebook} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <span className="w-4 h-4 text-center">f</span> Facebook
      </button>
      <button onClick={shareToX} className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 transition-colors text-sm">
        <span className="w-4 h-4 text-center">X</span> X / Twitter
      </button>
    </div>
  )
}

export function useShare(eventName: string) {
  const [shareMenuPhoto, setShareMenuPhoto] = useState<string | null>(null)

  const handleShare = async (imageId: string) => {
    const eventId = localStorage.getItem('event_id')
    const shareUrl = `${window.location.origin}/share/${eventId}/${imageId}`
    const shareText = `Check out this photo from ${eventName}!`

    if (navigator.share) {
      try {
        await navigator.share({ title: eventName, text: shareText, url: shareUrl })
        return
      } catch {
        // fall through to menu
      }
    }
    setShareMenuPhoto(imageId)
  }

  return { shareMenuPhoto, setShareMenuPhoto, handleShare }
}
